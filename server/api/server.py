"""
FastAPI server that exposes the orchestrator loop.

Input/output contracts are defined in `computer_use_agent.orchestrator.data_types`.
The endpoint performs dataclass validation and returns JSON payloads that
mirror those structures.
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

from fastapi import Body, FastAPI, Header, HTTPException
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
        "http://localhost:5173",
        "https://localhost:5173",
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
) -> StreamingResponse:
    """Create streaming response using orchestrator agent.

    Args:
        request: OrchestrateRequest format
        user_id: Optional user ID for multi-tenancy
        tool_constraints: Optional tool constraints dict

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

@app.post("/orchestrate")
async def orchestrate(
    payload: Dict[str, Any] = Body(...),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
) -> Dict[str, Any]:
    """
    Run a single orchestrator task (non-streaming).

    Headers:
        X-User-Id: Optional user ID for multi-tenancy (falls back to TB_DEFAULT_USER_ID env var)

    Payload:
        task: Required task description string
        worker: Optional worker configuration overrides
        grounding: Optional grounding/code agent configuration
        controller: Optional VM controller connection details
        tool_constraints: Optional dict with:
            - mode: "auto" | "custom"
            - providers: List[str] (for custom mode)
            - tools: List[str] (for custom mode)
    """
    from server.api.orchestrator_adapter import orchestrate_to_orchestrator

    request = _parse_orchestrate_request(payload)
    user_id = x_user_id or os.getenv("TB_DEFAULT_USER_ID")
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
async def orchestrate_stream(task: str) -> StreamingResponse:
    """
    Backward-compatible streaming endpoint that only accepts a `task` query param.
    """
    request = OrchestrateRequest(
        task=task,
        worker=WorkerConfig.from_dict({}),
        grounding=GroundingConfig.from_dict({}),
        controller=ControllerConfig.from_dict({}),
    )
    return _create_streaming_response(request)


@app.post("/orchestrate/stream")
async def orchestrate_stream_post(
    payload: Dict[str, Any] = Body(...),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
) -> StreamingResponse:
    """
    Streaming endpoint with full payload support (tool constraints, controller overrides, etc.).

    Headers:
        X-User-Id: Optional user ID for multi-tenancy (falls back to TB_DEFAULT_USER_ID env var)

    Payload:
        tool_constraints: Optional dict with:
            - mode: "auto" | "custom"
            - providers: List[str] (for custom mode)
            - tools: List[str] (for custom mode)
    """
    request = _parse_orchestrate_request(payload)

    # Extract user_id from header or env
    user_id = x_user_id or os.getenv("TB_DEFAULT_USER_ID")

    # Extract tool_constraints from payload
    tool_constraints = payload.get("tool_constraints")

    return _create_streaming_response(request, user_id, tool_constraints)


@app.get("/config")
async def config_defaults() -> Dict[str, Any]:
    """
    Return the default orchestrator configuration. Clients can merge overrides
    onto this structure when calling `/orchestrate`.
    """
    return {
        "controller": DEFAULT_CONTROLLER_CONFIG,
        "worker": DEFAULT_WORKER_CONFIG,
        "grounding": DEFAULT_GROUNDING_CONFIG,
    }


__all__ = ["app"]
