"""
FastAPI server that exposes the orchestrator loop.

Input/output contracts are defined in `computer_use_agent.orchestrator.data_types`.
The endpoint performs dataclass validation and returns JSON payloads that
mirror those structures.

Authentication: All endpoints require a valid Supabase JWT token in the
Authorization header. User ID is extracted from the token (sub claim).
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import json
import logging
import os
import time
from dataclasses import asdict
from typing import Any, Dict, Optional

from fastapi import Body, Depends, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from computer_use_agent.orchestrator.data_types import (
    DEFAULT_CONTROLLER_CONFIG,
    DEFAULT_GROUNDING_CONFIG,
    DEFAULT_WORKER_CONFIG,
    OrchestrateRequest,
    WorkerConfig,
    GroundingConfig,
    ControllerConfig,
)
from shared.latency_logger import LATENCY_LOGGER
from shared import agent_signal
from shared.streaming import (
    StreamEmitter,
    get_current_emitter,
    reset_current_emitter,
    set_current_emitter,
)

# Import auth dependency
from server.api.auth import get_current_user, CurrentUser

try:
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover
    load_dotenv = None

if load_dotenv:
    load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.info("Starting Orchestrator API")


@contextlib.asynccontextmanager
async def app_lifespan(app: FastAPI):  # pragma: no cover - startup/shutdown utility
    # Startup: warm MCP (registry is now DB-backed, minimal warmup needed)
    try:
        from mcp_agent.user_identity import normalize_user_id  # type: ignore
        user_env = os.getenv("TB_USER_ID")
        if not user_env:
            logger.info("Skipping MCP warmup: TB_USER_ID not set.")
        else:
            try:
                user_id = normalize_user_id(user_env)
                logger.info(f"MCP warmup for user: {user_id}")
            except ValueError:
                logger.warning("Skipping MCP warmup: invalid TB_USER_ID.")
    except Exception:
        # Never block startup due to warmup issues
        pass

    yield


app = FastAPI(title="TakeBridge Orchestrator API", version="0.1.0", lifespan=app_lifespan)
try:
    # Trust X-Forwarded-* headers when deployed behind a reverse proxy.
    from starlette.middleware.proxy_headers import ProxyHeadersMiddleware  # type: ignore
    app.add_middleware(ProxyHeadersMiddleware)
except Exception:
    # Optional dependency; safe to ignore in local dev
    pass

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://localhost:3000",
        "*",  # Allow all origins for auth flow
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
logger.info("API initialized")

# Treat the API server as non-interactive so Ctrl+C exits immediately.
agent_signal.set_interactive_mode(False)

# Mount MCP OAuth routes
try:
    from server.api.routes_mcp_auth import router as mcp_oauth_router  # type: ignore
    app.include_router(mcp_oauth_router)
    logger.info("Mounted MCP OAuth routes")
except Exception as _e:  # pragma: no cover
    logger.warning("Failed to mount MCP OAuth routes: %s", _e)

# Mount white-label passthrough redirect route
try:
    from server.api.route_composio_redirect import router as composio_redirect_router  # type: ignore
    app.include_router(composio_redirect_router)
    logger.info("Mounted Composio redirect passthrough route")
except Exception as _e:  # pragma: no cover
    logger.warning("Failed to mount Composio redirect route: %s", _e)

# Mount TEST-ONLY MCP tools routes
try:
    from server.api.routes_mcp_tools import router as mcp_tools_router  # type: ignore
    app.include_router(mcp_tools_router)
    logger.info("Mounted MCP tools (TEST-ONLY) routes")
except Exception as _e:  # pragma: no cover
    logger.warning("Failed to mount MCP tools routes: %s", _e)

# Mount App routes (run_task)
try:
    from server.api.routes_app import router as app_router  # type: ignore
    app.include_router(app_router)
    logger.info("Mounted App routes")
except Exception as _e:  # pragma: no cover
    logger.warning("Failed to mount App routes: %s", _e)

# Mount Workspace routes
try:
    from server.api.routes_workspace import router as workspace_router  # type: ignore
    app.include_router(workspace_router)
    logger.info("Mounted Workspace routes")
except Exception as _e:  # pragma: no cover
    logger.warning("Failed to mount Workspace routes: %s", _e)


# Health check endpoint (no auth required)
@app.get("/health")
async def health():
    return {"status": "ok"}


# Debug auth endpoint (no auth required, for troubleshooting)
@app.get("/debug/auth")
async def debug_auth():
    """
    Debug endpoint to check auth configuration (without sensitive data).
    Helps verify JWT secret is configured correctly.
    """
    from server.api.config import settings
    return {
        "jwt_secret_configured": bool(settings.SUPABASE_JWT_SECRET),
        "jwt_secret_length": len(settings.SUPABASE_JWT_SECRET) if settings.SUPABASE_JWT_SECRET else 0,
        "jwt_algorithm": settings.SUPABASE_JWT_ALG,
    }


def _parse_orchestrate_request(payload: Dict[str, Any]) -> OrchestrateRequest:
    try:
        return OrchestrateRequest.from_dict(payload)
    except Exception as exc:  # pragma: no cover - validation guard
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def _execute_orchestrator(
    request: "OrchestratorRequest", emitter: Optional[StreamEmitter] = None
):
    """Execute the orchestrator agent with optional stream emission."""
    from orchestrator_agent.runtime import OrchestratorRuntime

    token = None
    if emitter:
        token = set_current_emitter(emitter)

    try:
        with LATENCY_LOGGER.measure("server", "orchestrate"):
            runtime = OrchestratorRuntime()
            return await runtime.run_task(request)
    except BaseException as exc:  # pragma: no cover - runtime guard
        logger.exception("Orchestration failed: %s", exc)
        raise
    finally:
        if token:
            reset_current_emitter(token)


def _format_sse_event(event: str, data: Optional[Any] = None) -> bytes:
    parts = [f"event: {event}"]
    if data is not None:
        try:
            serialized = json.dumps(data, separators=(",", ":"))
        except (TypeError, ValueError):
            serialized = json.dumps({"fallback": str(data)}, separators=(",", ":"))
        parts.append(f"data: {serialized}")
    parts.append("")
    return ("\n".join(parts)).encode("utf-8")

def _create_streaming_response(
    request: OrchestrateRequest,
    user_id: Optional[str] = None,
    tool_constraints: Optional[Dict[str, Any]] = None,
    auto_resolve_workspace: bool = True,
) -> StreamingResponse:
    """Create streaming response using orchestrator agent.

    Args:
        request: OrchestrateRequest format
        user_id: User ID from JWT token
        tool_constraints: Optional tool constraints dict
        auto_resolve_workspace: If True, automatically get/create workspace and use its controller_base_url

    Returns:
        StreamingResponse with SSE events
    """
    queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    queue.put_nowait(_format_sse_event("response.created", {"status": "accepted"}))
    queue.put_nowait(_format_sse_event("response.in_progress", {"status": "running"}))

    def _publish(event: str, data: Optional[Any] = None) -> None:
        chunk = _format_sse_event(event, data)
        try:
            loop.call_soon_threadsafe(queue.put_nowait, chunk)
        except RuntimeError as exc:
            if "closed" not in str(exc).lower():
                raise

    emitter = StreamEmitter(_publish)

    async def _emit_keepalive(interval: float = 15.0) -> None:
        """Emit periodic keepalive events so clients do not time out."""
        try:
            while True:
                await asyncio.sleep(interval)
                if agent_signal.exit_requested():
                    return
                _publish(
                    "server.keepalive",
                    {"ts": time.time()},
                )
        except asyncio.CancelledError:
            if not agent_signal.exit_requested():
                _publish("server.keepalive.stopped", {"ts": time.time()})
            raise

    async def _drain_queue():
        try:
            while True:
                chunk = await queue.get()
                if chunk is None:
                    break
                yield chunk
                await asyncio.sleep(0.01)
        finally:
            while not queue.empty():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

    async def _run_and_stream() -> None:
        heartbeat = None
        try:
            heartbeat = asyncio.create_task(_emit_keepalive())

            from server.api.orchestrator_adapter import orchestrate_to_orchestrator
            from server.core.workspace_service import ensure_workspace

            # Auto-resolve workspace if enabled and user_id is provided
            if auto_resolve_workspace and user_id:
                try:
                    ws = ensure_workspace(user_id)
                    # Override controller base_url with workspace's controller_base_url
                    # unless it's already explicitly set in the request
                    if ws.controller_base_url and not request.controller.base_url:
                        request.controller.base_url = ws.controller_base_url
                        logger.info(f"Using workspace controller_base_url: {ws.controller_base_url}")
                except Exception as e:
                    logger.warning(f"Failed to resolve workspace for user {user_id}: {e}")
                    # Continue without workspace - controller might be set manually

            orch_request = orchestrate_to_orchestrator(
                request,
                user_id=user_id,
                tool_constraints=tool_constraints,
            )
            logger.info("Executing orchestrator_agent request")
            result = await _execute_orchestrator(orch_request, emitter)

            # Convert RunState to dict for response
            result_dict = {
                "task": orch_request.task,
                "status": "success" if all(r.success for r in result.results) else "partial",
                "completion_reason": "ok" if result.results else "no_steps",
                "steps": [asdict(r) for r in result.results],
            }

        except BaseException as exc:  # pragma: no cover - runtime guard
            if isinstance(exc, SystemExit) and exc.code == 0:
                logger.info("Orchestration exited cleanly via agent_signal.")
                await queue.put(
                    _format_sse_event(
                        "response.completed",
                        {
                            "status": "completed",
                            "completion_reason": "clean_exit",
                        },
                    )
                )
            else:
                logger.exception("Orchestration task failed: %s", exc)
                error_payload = {"error": str(exc)}
                await queue.put(_format_sse_event("response.failed", error_payload))
                await queue.put(_format_sse_event("error", error_payload))
        else:
            await queue.put(_format_sse_event("response", result_dict))
            await queue.put(
                _format_sse_event(
                    "response.completed",
                    {
                        "status": result_dict.get("status"),
                        "completion_reason": result_dict.get("completion_reason"),
                    },
                )
            )
        finally:
            if heartbeat:
                heartbeat.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await heartbeat
            await queue.put(None)

    asyncio.create_task(_run_and_stream())
    return StreamingResponse(
        _drain_queue(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _ensure_workspace_controller(
    payload: Dict[str, Any],
    user_id: str,
) -> Dict[str, Any]:
    """Ensure controller base_url is set from workspace if not provided in payload."""
    from server.core.workspace_service import ensure_workspace

    # If controller base_url is already set, use it
    controller_data = payload.get("controller", {})
    if controller_data.get("base_url"):
        return payload

    # Otherwise, get/create workspace and use its controller_base_url
    try:
        ws = ensure_workspace(user_id)
        if ws.controller_base_url:
            if "controller" not in payload:
                payload["controller"] = {}
            payload["controller"]["base_url"] = ws.controller_base_url
            logger.info(f"Using workspace controller_base_url: {ws.controller_base_url}")
    except Exception as e:
        logger.warning(f"Failed to resolve workspace for user {user_id}: {e}")
        # Continue without workspace - controller might be set manually

    return payload

@app.post("/orchestrate")
async def orchestrate(
    payload: Dict[str, Any] = Body(...),
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Run a single orchestrator task (non-streaming).

    Authentication: Requires a valid Supabase JWT token in the Authorization header.
    The user_id is extracted from the token (sub claim).

    Automatically resolves workspace and uses its controller_base_url if controller.base_url
    is not provided in the payload.

    Payload:
        task: Required task description string
        worker: Optional worker configuration overrides
        grounding: Optional grounding/code agent configuration
        controller: Optional VM controller connection details (base_url auto-resolved from workspace if not provided)
        tool_constraints: Optional dict with:
            - mode: "auto" | "custom"
            - providers: List[str] (for custom mode)
            - tools: List[str] (for custom mode)
    """
    from server.api.orchestrator_adapter import orchestrate_to_orchestrator

    user_id = current_user.sub
    # Auto-resolve workspace controller if not provided
    payload = _ensure_workspace_controller(payload, user_id)

    request = _parse_orchestrate_request(payload)
    tool_constraints = payload.get("tool_constraints")

    orch_request = orchestrate_to_orchestrator(
        request,
        user_id=user_id,
        tool_constraints=tool_constraints,
    )

    try:
        result = await _execute_orchestrator(orch_request)
    except Exception as exc:  # pragma: no cover - runtime guard
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "task": orch_request.task,
        "status": "success" if all(r.success for r in result.results) else "partial",
        "completion_reason": "ok" if result.results else "no_steps",
        "steps": [asdict(r) for r in result.results],
    }


@app.get("/orchestrate/stream")
async def orchestrate_stream(
    task: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    """
    Streaming endpoint that accepts a `task` query param.

    Authentication: Requires a valid Supabase JWT token in the Authorization header.
    The user_id is extracted from the token (sub claim).

    Automatically resolves workspace and uses its controller_base_url.
    """
    request = OrchestrateRequest(
        task=task,
        worker=WorkerConfig.from_dict({}),
        grounding=GroundingConfig.from_dict({}),
        controller=ControllerConfig.from_dict({}),
    )
    return _create_streaming_response(
        request,
        user_id=current_user.sub,
        auto_resolve_workspace=True,
    )


@app.post("/orchestrate/stream")
async def orchestrate_stream_post(
    payload: Dict[str, Any] = Body(...),
    current_user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    """
    Streaming endpoint with full payload support (tool constraints, controller overrides, etc.).

    Authentication: Requires a valid Supabase JWT token in the Authorization header.
    The user_id is extracted from the token (sub claim).

    Automatically resolves workspace and uses its controller_base_url if controller.base_url
    is not provided in the payload.

    Payload:
        task: Required task description string
        controller: Optional VM controller connection details (base_url auto-resolved from workspace if not provided)
        tool_constraints: Optional dict with:
            - mode: "auto" | "custom"
            - providers: List[str] (for custom mode)
            - tools: List[str] (for custom mode)
    """
    user_id = current_user.sub

    # Auto-resolve workspace controller if not provided
    payload = _ensure_workspace_controller(payload, user_id)

    request = _parse_orchestrate_request(payload)

    # Extract tool_constraints from payload
    tool_constraints = payload.get("tool_constraints")

    return _create_streaming_response(
        request,
        user_id=user_id,
        tool_constraints=tool_constraints,
        auto_resolve_workspace=True,
    )


@app.get("/config")
async def config_defaults(
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Return the default orchestrator configuration. Clients can merge overrides
    onto this structure when calling `/orchestrate`.

    Authentication: Requires a valid Supabase JWT token in the Authorization header.
    """
    return {
        "controller": DEFAULT_CONTROLLER_CONFIG,
        "worker": DEFAULT_WORKER_CONFIG,
        "grounding": DEFAULT_GROUNDING_CONFIG,
    }


__all__ = ["app"]
