"""
FastAPI server that exposes the orchestrator loop.

Input/output contracts are defined in `computer_use_agent.orchestrator.data_types`.
The endpoint performs dataclass validation and returns JSON payloads that
mirror those structures.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import time
import uuid
from dataclasses import asdict
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

from fastapi import Body, FastAPI, HTTPException, Depends, Header
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
from vm_manager.aws_vm_manager import create_agent_instance_for_user
from vm_manager.config import settings
from orchestrator_agent.data_types import OrchestratorRequest
from shared.run_context import RUN_LOG_ID
from .auth import get_current_user, CurrentUser
from shared.supabase_client import get_service_supabase_client
from shared.db.engine import SessionLocal
from sqlalchemy import text

# Persisted event whitelist (see docs/latest_frontend_connection_guide.md)
PERSISTED_EVENTS = {
    # Orchestrator Agent
    "orchestrator.planning.completed",
    "orchestrator.step.completed",
    # Computer-Use Agent
    "runner.started",
    "runner.step.agent_response",
    "runner.step.behavior",
    "runner.step.completed",
    "runner.completed",
    "worker.reflection.completed",
    "worker.step.ready",
    "code_agent.session.started",
    "code_agent.session.completed",
    "code_agent.step.response",
    "code_agent.step.execution",
    "code_agent.step.completed",
    "grounding.generate_coords.started",
    "grounding.generate_coords.completed",
    "grounding.generate_coords.service_failed",
    "grounding.generate_text_coords.started",
    "grounding.generate_text_coords.completed",
    "behavior_narrator.completed",
    # MCP Agent
    "mcp.task.started",
    "mcp.task.completed",
    "mcp.planner.failed",
    "mcp.llm.completed",
    "mcp.action.planned",
    "mcp.action.started",
    "mcp.action.failed",
    "mcp.action.completed",
    "mcp.sandbox.run",
    "mcp.observation_processor.completed",
    "mcp.summary.created",
    "mcp.high_signal",
    # Human Attention (handback to human)
    "human_attention.required",
    "human_attention.resumed",
}
try:
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover
    load_dotenv = None

if load_dotenv:
    load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Suppress uvicorn access logs to WARNING level (keep errors, remove routine logs)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

logger.info("Starting Orchestrator API")

class _RunLogFilter(logging.Filter):
    """Filter that only allows records when the current run_id matches."""

    def __init__(self, run_id: str) -> None:
        super().__init__()
        self.run_id = run_id

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - thin helper
        current = RUN_LOG_ID.get()
        record.run_id = current or ""  # type: ignore[attr-defined]
        return current == self.run_id


def _attach_run_log_handler(run_id: str) -> logging.Handler:
    """Create and attach a file handler that captures logs for a specific run_id."""
    logs_dir = os.path.join("logs", "streams")
    os.makedirs(logs_dir, exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    filename = f"{timestamp}-{run_id}.log"
    path = os.path.join(logs_dir, filename)

    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setLevel(logging.INFO)
    handler.addFilter(_RunLogFilter(run_id))
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] run_id=%(run_id)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    return handler


def _detach_run_log_handler(handler: logging.Handler) -> None:
    """Detach and close a run-specific handler safely."""
    root_logger = logging.getLogger()
    try:
        root_logger.removeHandler(handler)
    except ValueError:
        pass
    with contextlib.suppress(Exception):
        handler.flush()
        handler.close()


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
        "http://localhost:5174",
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

# Mount task compose routes
try:
    from server.api.routes_compose_task import router as compose_task_router  # type: ignore
    app.include_router(compose_task_router)
    logger.info("Mounted task compose routes")
except Exception as _e:  # pragma: no cover
    logger.warning("Failed to mount task compose routes: %s", _e)

# Mount workflow/run routes
try:
    from server.api.routes_workflows import router as workflows_router  # type: ignore
    app.include_router(workflows_router)
    logger.info("Mounted workflow routes")
except Exception as _e:  # pragma: no cover
    logger.warning("Failed to mount workflow routes: %s", _e)


def _parse_orchestrate_request(payload: Dict[str, Any]) -> OrchestrateRequest:
    try:
        return OrchestrateRequest.from_dict(payload)
    except Exception as exc:  # pragma: no cover - validation guard
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def _execute_orchestrator(
    request: OrchestrateRequest, emitter: Optional[StreamEmitter] = None
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


def _json_safe(val: Any) -> Any:
    try:
        json.dumps(val)
        return val
    except Exception:
        if isinstance(val, dict):
            return {k: _json_safe(v) for k, v in val.items()}
        if isinstance(val, (list, tuple)):
            return [_json_safe(v) for v in val]
        return str(val)


def _touch_run_row(run_id: str) -> None:
    db = SessionLocal()
    try:
        db.execute(
            text(
                """
                UPDATE workflow_runs
                SET last_heartbeat_at = NOW(), updated_at = NOW()
                WHERE id = :run_id
                """
            ),
            {"run_id": run_id},
        )
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def _insert_run_event(
    run_id: Optional[str],
    kind: str,
    message: str,
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    if not run_id:
        return
    try:
        client = get_service_supabase_client()
        client.table("run_events").insert(
            {
                "id": str(uuid.uuid4()),
                "run_id": run_id,
                "kind": kind,
                "message": message,
                "payload": _json_safe(payload) if payload else {},
            }
        ).execute()
    except Exception:
        logger.debug("Failed to insert run_event run_id=%s kind=%s", run_id, kind)
    _touch_run_row(run_id)


def _persist_run_event(run_id: Optional[str], event: str, data: Optional[Any]) -> None:
    if not run_id:
        return
    if PERSISTED_EVENTS is not None and event not in PERSISTED_EVENTS:
        return
    if isinstance(data, dict):
        message = str(data.get("message") or data.get("status") or event)
    elif data is not None:
        message = str(data)
    else:
        message = event
    _insert_run_event(run_id, event, message, data if data is not None else {})


def _build_run_event_emitter(run_id: str) -> StreamEmitter:
    def _publish(event: str, data: Optional[Any] = None) -> None:
        try:
            _persist_run_event(run_id, event, data)
        except Exception:
            logger.debug("Failed to persist run event via emitter run_id=%s event=%s", run_id, event)

    return StreamEmitter(_publish)


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


def _update_run_status(run_id: str, status: str, summary: Optional[str] = None):
    db = SessionLocal()
    try:
        db.execute(
            text(
                """
                UPDATE workflow_runs
                SET status = :status,
                    summary = COALESCE(:summary, summary),
                    ended_at = CASE WHEN :terminal THEN NOW() ELSE ended_at END,
                    updated_at = NOW()
                WHERE id = :run_id
                """
            ),
            {
                "status": status,
                "summary": summary,
                "run_id": run_id,
                "terminal": status in {"success", "error", "attention", "cancelled"},
            },
        )
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def _normalize_controller_payload(controller_data: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    base_url = controller_data.get("base_url")
    if not base_url:
        raise RuntimeError("controller_base_url_missing")
    parsed = urlparse(base_url)
    host = controller_data.get("host") or (parsed.hostname if parsed else None)
    port = controller_data.get("port") or (parsed.port or settings.AGENT_CONTROLLER_PORT)
    controller_payload = {
        "base_url": base_url,
        "host": host,
        "port": port,
    }
    workspace_info = {
        "id": controller_data.get("id") or str(uuid.uuid4()),
        "controller_base_url": base_url,
        "vnc_url": controller_data.get("vnc_url"),
        "controller_host": host,
        "controller_port": port,
    }
    return controller_payload, workspace_info


def _provision_controller_session(user_id: str, run_id: Optional[str] = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    instance_id, controller_base_url, vnc_url = create_agent_instance_for_user(user_id)
    parsed = urlparse(controller_base_url)
    host = parsed.hostname if parsed else None
    port = parsed.port or settings.AGENT_CONTROLLER_PORT
    controller_payload = {
        "base_url": controller_base_url,
        "host": host,
        "port": port,
    }
    workspace_info = {
        "id": str(uuid.uuid4()),
        "controller_base_url": controller_base_url,
        "vnc_url": vnc_url,
        "controller_host": host,
        "controller_port": port,
    }

    endpoint = {
        "controller_base_url": controller_base_url,
        "vnc_url": vnc_url,
        "host": host,
        "port": port,
        "instance_id": instance_id,
    }

    if run_id:
        vm_id = workspace_info["id"]
        db = SessionLocal()
        try:
            db.execute(
                text(
                    """
                    INSERT INTO vm_instances (id, run_id, status, provider, spec, endpoint, created_at)
                    VALUES (:id, :run_id, :status, :provider, :spec, :endpoint, NOW())
                    """
                ),
                {
                    "id": vm_id,
                    "run_id": run_id,
                    "status": "ready",
                    "provider": "aws",
                    "spec": json.dumps(
                        {"instance_type": settings.AGENT_INSTANCE_TYPE, "region": settings.AWS_REGION}
                    ),
                    "endpoint": json.dumps(endpoint),
                },
            )
            db.execute(
                text(
                    """
                    UPDATE workflow_runs
                    SET vm_id = :vm_id,
                        environment = :env,
                        updated_at = NOW()
                    WHERE id = :run_id
                    """
                ),
                {"vm_id": vm_id, "env": json.dumps({"endpoint": endpoint}), "run_id": run_id},
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    return controller_payload, workspace_info


def _resolve_controller_session(
    user_id: str,
    controller_override: Optional[Dict[str, Any]] = None,
    run_id: Optional[str] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    if controller_override and controller_override.get("base_url"):
        return _normalize_controller_payload(controller_override)
    return _provision_controller_session(user_id, run_id)

def _create_streaming_response(
    request: OrchestrateRequest,
    user_id: Optional[str] = None,
    tool_constraints: Optional[Dict[str, Any]] = None,
    workspace: Optional[Dict[str, Any]] = None,
    run_id: Optional[str] = None,
    workflow_id: Optional[str] = None,
) -> StreamingResponse:
    """Create streaming response using orchestrator agent.

    Args:
        request: OrchestrateRequest format
        user_id: Optional user ID for multi-tenancy
        tool_constraints: Optional tool constraints dict
        workspace: Optional workspace context (id, controller_base_url, vnc_url)
        run_id: Optional workflow_run id to persist events/status
        workflow_id: Optional workflow id for context

    Returns:
        StreamingResponse with SSE events
    """
    queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    initial_payload = {"status": "accepted"}
    if workspace:
        initial_payload["workspace"] = workspace
    first_chunk = _format_sse_event("response.created", initial_payload)
    logger.info("SSE stream started")
    queue.put_nowait(first_chunk)
    queue.put_nowait(_format_sse_event("response.in_progress", {"status": "running"}))

    def _publish(event: str, data: Optional[Any] = None) -> None:
        chunk = _format_sse_event(event, data)
        try:
            # Trace every SSE emission for visibility
            logger.debug(
                "SSE event=%s payload_keys=%s",
                event,
                list(data.keys()) if isinstance(data, dict) else type(data).__name__,
            )
            loop.call_soon_threadsafe(queue.put_nowait, chunk)
        except RuntimeError as exc:
            if "closed" not in str(exc).lower():
                raise
        if run_id:
            try:
                _persist_run_event(run_id, event, data)
            except Exception:
                pass

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
        log_token = None
        handler = None
        run_id_local = run_id or None
        try:
            from server.api.orchestrator_adapter import orchestrate_to_orchestrator

            orch_request = orchestrate_to_orchestrator(
                request,
                user_id=user_id,
                tool_constraints=tool_constraints,
                workspace=workspace,
                run_id=run_id,
            )
            run_id_local = run_id or getattr(orch_request, "request_id", None) or "run"
            handler = _attach_run_log_handler(run_id_local)
            log_token = RUN_LOG_ID.set(run_id_local)

            # Start keepalive after run_id is bound so any logs it emits are tagged.
            heartbeat = asyncio.create_task(_emit_keepalive())

            logger.info("Executing orchestrator_agent request")
            result = await _execute_orchestrator(orch_request, emitter)

            # Convert RunState to dict for response
            # Check if the run stopped due to handback - respect that status
            completion_status = result.intermediate.get("completion_status")
            if completion_status == "attention":
                run_status = "attention"
                completion_reason = "handback_to_human"
            elif completion_status == "impossible":
                run_status = "error"
                completion_reason = result.intermediate.get("impossible_reason", "task_impossible")
            else:
                run_status = "success" if all(r.success for r in result.results) else "partial"
                completion_reason = "ok" if result.results else "no_steps"
            
            result_dict = {
                "task": orch_request.task,
                "status": run_status,
                "completion_reason": completion_reason,
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
                if run_id:
                    _update_run_status(run_id, "error", summary=str(exc))
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
            if run_id:
                # Don't update status if it's "attention" - mark_run_attention already set it
                if result_dict.get("status") != "attention":
                    summary = "; ".join(
                        [
                            r.get("final_summary") or ""
                            for r in result_dict.get("steps", [])
                            if isinstance(r, dict)
                        ]
                    )
                    _update_run_status(run_id, result_dict.get("status") or "success", summary=summary or None)
        finally:
            if heartbeat:
                heartbeat.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await heartbeat
            if log_token is not None:
                RUN_LOG_ID.reset(log_token)
            if handler is not None:
                _detach_run_log_handler(handler)
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
    current_user: CurrentUser = Depends(get_current_user),
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

    # Extract user_id from header or env
    user_id = current_user.sub

    controller_override = payload.get("controller")
    try:
        controller_data, workspace_info = _resolve_controller_session(user_id, controller_override)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    payload = {**payload, "controller": controller_data}

    request = _parse_orchestrate_request(payload)
    tool_constraints = payload.get("tool_constraints")

    orch_request = orchestrate_to_orchestrator(
        request,
        user_id=user_id,
        tool_constraints=tool_constraints,
        workspace=workspace_info,
    )

    try:
        result = await _execute_orchestrator(orch_request)
    except Exception as exc:  # pragma: no cover - runtime guard
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # Check if the run stopped due to handback - respect that status
    completion_status = result.intermediate.get("completion_status")
    if completion_status == "attention":
        run_status = "attention"
        completion_reason = "handback_to_human"
    elif completion_status == "impossible":
        run_status = "error"
        completion_reason = result.intermediate.get("impossible_reason", "task_impossible")
    else:
        run_status = "success" if all(r.success for r in result.results) else "partial"
        completion_reason = "ok" if result.results else "no_steps"

    return {
        "task": orch_request.task,
        "status": run_status,
        "completion_reason": completion_reason,
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
    current_user: CurrentUser = Depends(get_current_user),
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
    # Extract user_id from header or env
    user_id = current_user.sub

    run_id = payload.get("run_id")

    controller_override = payload.get("controller")
    try:
        controller_data, workspace_info = _resolve_controller_session(user_id, controller_override, run_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    payload = {**payload, "controller": controller_data}

    # Extract tool_constraints and optional composed_plan from payload
    tool_constraints = payload.get("tool_constraints")
    composed_plan = payload.get("composed_plan")

    request = _parse_orchestrate_request(payload)

    # Attach composed_plan so orchestrator_adapter can forward it
    if composed_plan is not None:
        setattr(request, "composed_plan", composed_plan)

    workspace_info = payload.get("workspace") or workspace_info

    return _create_streaming_response(request, user_id, tool_constraints, workspace_info, run_id=run_id)


def _require_internal_token(token: Optional[str]) -> None:
    expected = os.getenv("INTERNAL_API_TOKEN")
    if not expected or token != expected:
        raise HTTPException(status_code=403, detail="forbidden")


@app.post("/internal/runs/{run_id}/execute")
async def internal_execute_run(
    run_id: str,
    payload: Dict[str, Any] = Body(...),
    x_internal_token: Optional[str] = Header(default=None),
) -> StreamingResponse:
    """
    Internal endpoint for worker to trigger execution for a queued run.
    """
    _require_internal_token(x_internal_token)

    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")

    task = (payload.get("task") or "").strip()
    if not task:
        raise HTTPException(status_code=400, detail="task required")

    controller_override = payload.get("controller")
    try:
        controller_data, workspace_info = _resolve_controller_session(user_id, controller_override, run_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    payload = {**payload, "controller": controller_data, "task": task}
    tool_constraints = payload.get("tool_constraints")
    composed_plan = payload.get("composed_plan")

    request = _parse_orchestrate_request(payload)
    if composed_plan is not None:
        setattr(request, "composed_plan", composed_plan)
    workspace_info = payload.get("workspace") or workspace_info

    return _create_streaming_response(
        request,
        user_id=user_id,
        tool_constraints=tool_constraints,
        workspace=workspace_info,
        run_id=run_id,
        workflow_id=payload.get("workflow_id"),
    )


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


@app.post("/runs/{run_id}/resume")
async def resume_run(
    run_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Resume a run that was paused for human attention.

    This endpoint:
    1. Validates that the run exists and belongs to the user
    2. Validates that the run is in 'attention' status
    3. Captures the current screenshot from the VM
    4. Calls OpenAI to infer what the human did
    5. Updates the agent_states with the inference result
    6. Updates the run status to 'running' (or queues for async continuation)

    Returns:
        Dict with inference result and updated status
    """
    from server.api.controller_client import VMControllerClient
    from server.api.handback_inference import infer_human_action, format_inference_for_context
    from shared.db.workflow_runs import merge_agent_states
    import base64

    user_id = current_user.sub
    db = SessionLocal()

    try:
        # 1. Fetch the run and validate ownership + status
        row = db.execute(
            text("""
                SELECT id, user_id, status, agent_states, environment
                FROM workflow_runs
                WHERE id = :run_id
            """),
            {"run_id": run_id},
        ).fetchone()

        if row is None:
            raise HTTPException(status_code=404, detail="Run not found")

        row_user_id = row[1]
        row_status = row[2]
        row_agent_states = row[3]
        row_environment = row[4]

        # Check ownership
        if row_user_id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to resume this run")

        # Check status
        if row_status != "attention":
            raise HTTPException(
                status_code=400,
                detail=f"Run is not in 'attention' status (current: {row_status})"
            )

        # 2. Parse agent_states to get handback info
        agent_states = row_agent_states if isinstance(row_agent_states, dict) else {}
        if isinstance(row_agent_states, str):
            try:
                agent_states = json.loads(row_agent_states)
            except Exception:
                agent_states = {}

        computer_use_state = agent_states.get("agents", {}).get("computer_use", {})
        handback = computer_use_state.get("handback", {})

        if not handback:
            raise HTTPException(
                status_code=400,
                detail="No handback state found for this run"
            )

        handback_request = handback.get("request", "")
        before_screenshot_b64 = handback.get("screenshot_b64", "")

        if not before_screenshot_b64:
            raise HTTPException(
                status_code=400,
                detail="No handback screenshot found"
            )

        # 3. Get controller from environment and capture current screenshot
        environment = row_environment if isinstance(row_environment, dict) else {}
        if isinstance(row_environment, str):
            try:
                environment = json.loads(row_environment)
            except Exception:
                environment = {}

        endpoint = environment.get("endpoint", {})
        controller_base_url = endpoint.get("controller_base_url")

        if not controller_base_url:
            raise HTTPException(
                status_code=400,
                detail="No controller endpoint found for this run"
            )

        # Create controller client and capture current screenshot
        try:
            controller = VMControllerClient(base_url=controller_base_url)
            current_screenshot_bytes = controller.capture_screenshot()
            current_screenshot_b64 = base64.b64encode(current_screenshot_bytes).decode("utf-8")
        except Exception as e:
            logger.error("Failed to capture current screenshot: %s", e)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to capture current screenshot: {str(e)}"
            )

        # 4. Call OpenAI to infer what the human did
        try:
            inference_result = infer_human_action(
                request=handback_request,
                before_screenshot_b64=before_screenshot_b64,
                after_screenshot_b64=current_screenshot_b64,
            )
        except Exception as e:
            logger.error("Handback inference failed: %s", e)
            inference_result = {
                "changes_observed": "Inference failed",
                "request_fulfilled": False,
                "confidence": "low",
                "details": str(e),
            }

        # 5. Extract previous trajectory for full context
        runner_state = computer_use_state.get("runner", {})
        previous_trajectory = runner_state.get("trajectory_md", "")
        
        # 6. Format inference for agent context WITH previous trajectory
        inference_context = format_inference_for_context(
            inference_result,
            handback_request,
            previous_trajectory=previous_trajectory,
        )
        
        # 7. Update agent_states with inference AND continuation marker
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        resume_from_step = handback.get("step_index", 0) + 1
        
        inference_update = {
            "handback": {
                **handback,
                "inference": inference_result,
                "resumed_at": now,
            },
            # Continuation marker for the orchestrator to detect and inject context
            "continuation": {
                "should_inject_inference": True,
                "inference_context": inference_context,
                "resume_from_step": resume_from_step,
                "resumed_at": now,
            }
        }

        try:
            merge_agent_states(run_id, inference_update, path=["agents", "computer_use"])
            logger.info("Updated agent_states with continuation marker for run_id=%s", run_id)
        except Exception as e:
            logger.error("Failed to update agent_states with inference: %s", e)

        # 8. Update run status to 'queued' for continuation
        db.execute(
            text("""
                UPDATE workflow_runs
                SET status = 'queued',
                    updated_at = :now
                WHERE id = :run_id
            """),
            {"run_id": run_id, "now": now},
        )
        db.commit()

        # 9. Emit resume event
        _insert_run_event(
            run_id=run_id,
            kind="human_attention.resumed",
            message=f"Human intervention completed. Request fulfilled: {inference_result.get('request_fulfilled', False)}",
            payload={
                "inference": inference_result,
                "handback_request": handback_request,
                "resume_from_step": resume_from_step,
                "timestamp": now,
            },
        )

        # 10. Return response
        return {
            "status": "resumed",
            "run_id": run_id,
            "inference": inference_result,
            "inference_context": inference_context,
            "handback_request": handback_request,
            "message": "Run resumed. The agent will continue with the inferred context.",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Resume run failed: %s", e, exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


__all__ = ["app"]
