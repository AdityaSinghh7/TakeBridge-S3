"""
Control-plane API server.

Owns auth + database-backed operations and proxies runtime execution endpoints.
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import hashlib
import json
import logging
import os
import secrets
import time
import uuid
from datetime import datetime, timezone
from dataclasses import asdict
from typing import Any, Dict, Optional, Tuple, List
from urllib.parse import urlparse

from fastapi import Body, FastAPI, HTTPException, Depends, Header, Request
from fastapi.responses import StreamingResponse, Response
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
from shared.stdio import ensure_utf8_stdio
from vm_manager.vm_provider import create_agent_instance_for_user, current_provider, provider_spec
from vm_manager.config import settings
from orchestrator_agent.data_types import OrchestratorRequest
from shared.run_context import RUN_LOG_ID
from .auth import get_current_user, CurrentUser
from .internal_runtime import router as internal_runtime_router
from .runtime_proxy import proxy_request
from .run_drive import (
    stage_drive_files_for_run,
    DriveStageError,
    detect_drive_changes,
    commit_drive_changes_for_run,
)
from shared.supabase_client import get_service_supabase_client
from shared.db.engine import SessionLocal, DB_URL
from shared.db import vm_instances, workflow_runs
from mcp_agent.registry.connected_accounts import (
    check_connected_account_statuses,
    resolve_tool_constraint_providers,
)

# Persisted event whitelist (see docs/latest_frontend_connection_guide.md)
PERSISTED_EVENTS = {
    # Orchestrator Agent
    "orchestrator.planning.completed",
    "orchestrator.step.completed",
    "orchestrator.task.completed",
    "orchestrator.summary.created",
    # Computer-Use Agent
    "runner.started",
    "runner.step.agent_response",
    "runner.step.behavior",
    "runner.step.completed",
    "runner.completed",
    # "worker.step.started",
    # "worker.reflection.completed",
    "worker.reflection.summary",
    "worker.step.ready",
    "code_agent.session.started",
    "code_agent.session.completed",
    "code_agent.step.response",
    "code_agent.step.execution",
    "code_agent.step.completed",
    "code_agent.step.recorded",
    "code_agent.summary.created",
    # "grounding.generate_coords.started",
    # "grounding.generate_coords.completed",
    "grounding.generate_coords.service_failed",
    "grounding.generate_text_coords.started",
    "grounding.generate_text_coords.completed",
    # "behavior_narrator.summary",
    # MCP Agent
    "mcp.task.started",
    "mcp.planner.started",
    "mcp.task.completed",
    "mcp.planner.failed",
    "mcp.search.completed",
    "mcp.action.planned",
    "mcp.action.failed",
    "mcp.action.started",
    "mcp.action.completed",
    "mcp.sandbox.run",
    "mcp.observation_processor.completed",
    "mcp.summary.created",
    "mcp.high_signal",
    "mcp.step.recorded",
    # Human Attention (handback to human)
    "human_attention.required",
    "human_attention.resumed",
    # Server error signals
    "response.failed",
    "error",
    
    "workspace.attachments",
}
try:
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover
    load_dotenv = None

if load_dotenv:
    load_dotenv()

logging.basicConfig(level=logging.INFO)
ensure_utf8_stdio()
logger = logging.getLogger(__name__)

# Suppress uvicorn access logs to WARNING level (keep errors, remove routine logs)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

_RUNTIME_PROXY_ENABLED = (os.getenv("RUNTIME_PROXY_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"})


def _runtime_proxy_enabled() -> bool:
    return _RUNTIME_PROXY_ENABLED


def _summarize_db_url(db_url: str) -> str:
    """Return a safe, password-free DB URL summary for logs."""
    try:
        parsed = urlparse(db_url)
    except Exception:
        return "<invalid>"
    if parsed.scheme.startswith("sqlite"):
        return parsed.scheme
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    user = f"{parsed.username}@" if parsed.username else ""
    path = parsed.path or ""
    return f"{parsed.scheme}://{user}{host}{port}{path}"


def _token_fingerprint(token: str) -> str:
    if not token:
        return "unset"
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:10]


logger.info(
    "Config INTERNAL_API_TOKEN_set=%s INTERNAL_API_TOKEN_fp=%s DB_URL=%s",
    bool((os.getenv("INTERNAL_API_TOKEN") or "").strip()),
    _token_fingerprint((os.getenv("INTERNAL_API_TOKEN") or "").strip()),
    _summarize_db_url(DB_URL),
)

logger.info("Starting Control Plane API")


class _RunLogFilter(logging.Filter):
    """Filter that only allows records when the current run_id matches."""

    def __init__(self, run_id: str) -> None:
        super().__init__()
        self.run_id = run_id

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - thin helper
        current = RUN_LOG_ID.get()
        # Always populate run_id on the record for formatting
        record.run_id = current or self.run_id or ""  # type: ignore[attr-defined]
        # Allow logs even if context got lost (threadpool/async gaps); best-effort match
        if current is None:
            return True
        return current == self.run_id


def _attach_run_log_handler(run_id: str) -> tuple[logging.Handler, logging.Handler]:
    """Create and attach file + console handlers that capture logs for a specific run_id."""
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
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.addFilter(_RunLogFilter(run_id))
    console.setFormatter(formatter)

    root_logger.addHandler(handler)
    root_logger.addHandler(console)
    return handler, console


def _detach_run_log_handler(handlers: tuple[logging.Handler, logging.Handler]) -> None:
    """Detach and close run-specific handlers safely."""
    root_logger = logging.getLogger()
    file_handler, console_handler = handlers
    for h in (file_handler, console_handler):
        try:
            root_logger.removeHandler(h)
        except ValueError:
            pass
        with contextlib.suppress(Exception):
            h.flush()
            h.close()


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


app = FastAPI(title="TakeBridge Control Plane API", version="0.1.0", lifespan=app_lifespan)
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

# Mount internal runtime API routes (service-to-service only)
try:
    app.include_router(internal_runtime_router)
    logger.info("Mounted internal runtime routes")
except Exception as _e:  # pragma: no cover
    logger.warning("Failed to mount internal runtime routes: %s", _e)

# Mount workflow/run routes
try:
    from server.api.routes_workflows import router as workflows_router  # type: ignore
    app.include_router(workflows_router)
    logger.info("Mounted workflow routes")
except Exception as _e:  # pragma: no cover
    logger.warning("Failed to mount workflow routes: %s", _e)

# Mount drive routes
try:
    from server.api.routes_drive import router as drive_router  # type: ignore
    app.include_router(drive_router)
    logger.info("Mounted drive routes")
except Exception as _e:  # pragma: no cover
    logger.warning("Failed to mount drive routes: %s", _e)

# Mount user metadata routes
try:
    from server.api.routes_user_metadata import router as user_metadata_router  # type: ignore
    app.include_router(user_metadata_router)
    logger.info("Mounted user metadata routes")
except Exception as _e:  # pragma: no cover
    logger.warning("Failed to mount user metadata routes: %s", _e)

# Mount Guacamole auth routes
try:
    from server.api.routes_guac_auth import router as guac_auth_router  # type: ignore
    app.include_router(guac_auth_router)
    logger.info("Mounted Guacamole auth routes")
except Exception as _e:  # pragma: no cover
    logger.warning("Failed to mount Guacamole auth routes: %s", _e)


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
        workflow_runs.touch_run(db, run_id=run_id)
        try:
            from shared.db.user_metadata import record_run_heartbeat

            record_run_heartbeat(db, run_id=run_id)
        except Exception:
            pass
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def _event_indicates_error(kind: str, payload: Optional[Dict[str, Any]]) -> bool:
    payload = payload or {}
    if kind in {"mcp.action.failed", "mcp.planner.failed", "response.failed", "error"}:
        return True
    if payload.get("error"):
        return True
    if payload.get("success") is False:
        return True
    status = payload.get("status")
    if isinstance(status, str) and status.lower() in {"failed", "error", "attention"}:
        return True
    completion_reason = payload.get("completion_reason")
    if isinstance(completion_reason, str) and completion_reason.upper() in {"FAIL", "HANDOFF_TO_HUMAN"}:
        return True
    return False


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
    if run_id and _event_indicates_error(kind, payload):
        db = SessionLocal()
        try:
            from shared.db.user_metadata import record_run_event

            record_run_event(
                db,
                run_id=run_id,
                kind=kind,
                message=message,
                payload=payload or {},
            )
            db.commit()
        except Exception:
            db.rollback()
            logger.debug("Failed to update user metadata for run_event run_id=%s kind=%s", run_id, kind)
        finally:
            db.close()


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
        workflow_runs.update_status(
            db,
            run_id=run_id,
            status=status,
            summary=summary,
            terminal_statuses={"success", "error", "attention", "cancelled", "partial"},
        )
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def _merge_run_environment(run_id: str, patch: Dict[str, Any]) -> None:
    db = SessionLocal()
    try:
        workflow_runs.merge_environment(db, run_id=run_id, patch=patch)
        db.commit()
    except Exception:
        db.rollback()
        raise
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
            vm_instances.insert_vm_instance(
                db,
                vm_id=vm_id,
                run_id=run_id,
                status="ready",
                provider=current_provider(),
                spec=provider_spec(),
                endpoint=endpoint,
            )
            workflow_runs.set_vm_id(db, run_id=run_id, vm_id=vm_id)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
        _merge_run_environment(run_id, {"endpoint": endpoint})

    return controller_payload, workspace_info


def _resolve_controller_session(
    user_id: str,
    controller_override: Optional[Dict[str, Any]] = None,
    run_id: Optional[str] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Resolve the controller session to use for a run.

    Priority:
    1) Explicit override with base_url.
    2) Persisted workflow_runs.environment (for resumed/rehydrated runs).
    3) Provision a fresh controller session.
    """
    if controller_override and controller_override.get("base_url"):
        return _normalize_controller_payload(controller_override)

    # If we have a run_id, try to reuse the persisted environment so the
    # orchestrator reconnects to the same controller after requeue/resume.
    if run_id:
        db = SessionLocal()
        try:
            env = workflow_runs.get_environment(db, run_id=run_id)
        finally:
            db.close()

        if env:
            endpoint = env.get("endpoint") if isinstance(env, dict) else None
            if isinstance(endpoint, str):
                try:
                    endpoint = json.loads(endpoint)
                except Exception:
                    endpoint = None

            if isinstance(endpoint, dict):
                base_url = (
                    endpoint.get("controller_base_url")
                    or endpoint.get("base_url")
                )
                if base_url:
                    host = endpoint.get("controller_host") or endpoint.get("host")
                    port = endpoint.get("controller_port") or endpoint.get("port")
                    controller_payload = {
                        "base_url": base_url,
                        "host": host,
                        "port": port,
                    }
                    workspace_info = {
                        "id": endpoint.get("instance_id") or endpoint.get("id") or str(uuid.uuid4()),
                        "controller_base_url": base_url,
                        "vnc_url": endpoint.get("vnc_url"),
                        "controller_host": host,
                        "controller_port": port,
                    }
                    return controller_payload, workspace_info

    # Fallback to provisioning a new session
    return _provision_controller_session(user_id, run_id)


def _attach_workspace_files(workspace: Dict[str, Any], run_id: Optional[str]) -> Dict[str, Any]:
    if not run_id:
        return workspace
    try:
        drive_files = stage_drive_files_for_run(run_id, workspace)
    except DriveStageError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    updated = dict(workspace)
    if drive_files:
        updated["drive"] = drive_files
    return updated


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
        final_status: Optional[str] = None
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
            logger.info("Stream start: resolved run_id=%s", run_id_local)
            handler = _attach_run_log_handler(run_id_local)
            try:
                file_handler, console_handler = handler
                logger.info(
                    "Run log handlers attached for run_id=%s file=%s",
                    run_id_local,
                    getattr(file_handler, "baseFilename", "?"),
                )
            except Exception:
                logger.info("Run log handlers attached for run_id=%s", run_id_local)
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
                run_status = "success"
                completion_reason = "ok" if result.results else "no_steps"

            result_dict = {
                "task": orch_request.task,
                "status": run_status,
                "completion_reason": completion_reason,
                "steps": [asdict(r) for r in result.results],
            }
            final_status = run_status

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
                final_status = "error"
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
            drive_changes: List[Dict[str, Any]] = []
            committed_drive_changes: List[Dict[str, Any]] = []
            committed_drive_changes: List[Dict[str, Any]] = []
            if run_id_local and workspace:
                try:
                    drive_changes = detect_drive_changes(run_id_local, workspace)
                except Exception as exc:
                    logger.warning("Failed to detect drive changes for run %s: %s", run_id_local, exc)
                if drive_changes:
                    logger.info("[drive] detected %s changed files for run %s", len(drive_changes), run_id_local)
                try:
                    committed_drive_changes = commit_drive_changes_for_run(run_id_local, workspace)
                except Exception as exc:
                    logger.warning("Failed to commit drive changes for run %s: %s", run_id_local, exc)
                try:
                    committed_drive_changes = commit_drive_changes_for_run(run_id_local, workspace)
                except Exception as exc:
                    logger.warning("Failed to commit drive changes for run %s: %s", run_id_local, exc)
            if run_id and run_id_local and final_status and final_status != "attention":
                try:
                    from vm_manager.vm_wrapper import terminate_run_instance
                    terminate_run_instance(run_id_local)
                except Exception as exc:
                    logger.warning(
                        "Failed to stop VM instance for run_id=%s status=%s: %s",
                        run_id_local,
                        final_status,
                        exc,
                    )
            if heartbeat:
                heartbeat.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await heartbeat
            if log_token is not None:
                RUN_LOG_ID.reset(log_token)
            if handler is not None:
                _detach_run_log_handler(handler)
                try:
                    file_handler, _ = handler
                    logger.info(
                        "Run log handlers detached for run_id=%s file=%s",
                        run_id_local,
                        getattr(file_handler, "baseFilename", "?"),
                    )
                except Exception:
                    logger.info("Run log handlers detached for run_id=%s", run_id_local)
            if committed_drive_changes:
                _publish(
                    "run.drive.committed",
                    {"run_id": run_id_local, "changes": committed_drive_changes},
                )
            await queue.put(None)

    asyncio.create_task(_run_and_stream())
    return StreamingResponse(
        _drain_queue(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

@app.post("/orchestrate")
async def orchestrate(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    current_user: CurrentUser = Depends(get_current_user),
) -> Response:
    """
    Run a single orchestrator task (non-streaming) via the runtime service.
    """
    if not _runtime_proxy_enabled():
        from server.api.orchestrator_adapter import orchestrate_to_orchestrator

        user_id = current_user.sub
        controller_override = payload.get("controller")
        try:
            controller_data, workspace_info = _resolve_controller_session(user_id, controller_override)
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        payload = {**payload, "controller": controller_data}

        request_obj = _parse_orchestrate_request(payload)
        tool_constraints = payload.get("tool_constraints")

        orch_request = orchestrate_to_orchestrator(
            request_obj,
            user_id=user_id,
            tool_constraints=tool_constraints,
            workspace=workspace_info,
        )

        try:
            result = await _execute_orchestrator(orch_request)
        except Exception as exc:  # pragma: no cover - runtime guard
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        completion_status = result.intermediate.get("completion_status")
        if completion_status == "attention":
            run_status = "attention"
            completion_reason = "handback_to_human"
        elif completion_status == "impossible":
            run_status = "error"
            completion_reason = result.intermediate.get("impossible_reason", "task_impossible")
        else:
            run_status = "success"
            completion_reason = "ok" if result.results else "no_steps"

        return Response(
            content=json.dumps(
                {
                    "task": orch_request.task,
                    "status": run_status,
                    "completion_reason": completion_reason,
                    "steps": [asdict(r) for r in result.results],
                }
            ),
            media_type="application/json",
        )
    return await proxy_request(request, stream=False)


@app.get("/orchestrate/stream")
async def orchestrate_stream(
    request: Request,
    task: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    """
    Backward-compatible streaming endpoint that only accepts a `task` query param.
    """
    if not _runtime_proxy_enabled():
        request_obj = OrchestrateRequest(
            task=task,
            worker=WorkerConfig.from_dict({}),
            grounding=GroundingConfig.from_dict({}),
            controller=ControllerConfig.from_dict({}),
        )
        return _create_streaming_response(request_obj)
    return await proxy_request(request, stream=True)


@app.post("/orchestrate/stream")
async def orchestrate_stream_post(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    current_user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    """
    Streaming endpoint with full payload support (tool constraints, controller overrides, etc.).
    """
    if not _runtime_proxy_enabled():
        user_id = current_user.sub
        run_id = payload.get("run_id")

        controller_override = payload.get("controller")
        try:
            controller_data, workspace_info = _resolve_controller_session(user_id, controller_override, run_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        payload = {**payload, "controller": controller_data}

        tool_constraints = payload.get("tool_constraints")
        composed_plan = payload.get("composed_plan")

        request_obj = _parse_orchestrate_request(payload)
        if composed_plan is not None:
            setattr(request_obj, "composed_plan", composed_plan)

        workspace_info = payload.get("workspace") or workspace_info
        workspace_info = _attach_workspace_files(workspace_info, run_id)

        return _create_streaming_response(request_obj, user_id, tool_constraints, workspace_info, run_id=run_id)
    return await proxy_request(request, stream=True)


@app.post("/compose_task")
async def compose_task_proxy(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    current_user: CurrentUser = Depends(get_current_user),
) -> Response:
    """
    Proxy task composition to runtime service.
    """
    if not _runtime_proxy_enabled():
        from server.api.routes_compose_task import compose_task as compose_task_local

        result = await compose_task_local(payload, current_user)
        return Response(content=json.dumps(result), media_type="application/json")
    return await proxy_request(request, stream=False)


def _require_internal_token(
    token: Optional[str],
    *,
    run_id: Optional[str] = None,
    user_agent: Optional[str] = None,
    token_source: Optional[str] = None,
) -> None:
    expected = (os.getenv("INTERNAL_API_TOKEN") or "").strip()
    provided = (token or "").strip()
    if not expected or not secrets.compare_digest(provided, expected):
        logger.warning(
            "Internal execute forbidden run_id=%s token_source=%s expected_set=%s expected_len=%s expected_fp=%s provided_len=%s provided_fp=%s user_agent=%s",
            run_id,
            token_source or "unknown",
            bool(expected),
            len(expected),
            _token_fingerprint(expected),
            len(provided),
            _token_fingerprint(provided),
            (user_agent or "")[:120],
        )
        raise HTTPException(status_code=403, detail="forbidden")


@app.post("/internal/runs/{run_id}/execute")
async def internal_execute_run(
    run_id: str,
    request: Request,
    payload: Dict[str, Any] = Body(...),
    x_internal_token: Optional[str] = Header(default=None, alias="X-Internal-Token"),
    authorization: Optional[str] = Header(default=None),
) -> StreamingResponse:
    """
    Internal endpoint for worker to trigger execution for a queued run.
    """
    token_source = "x-internal-token" if x_internal_token else "missing"
    token_value = x_internal_token
    if not token_value and authorization:
        token_source = "authorization"
        auth = authorization.strip()
        token_value = auth[7:].strip() if auth.lower().startswith("bearer ") else auth

    _require_internal_token(
        token_value,
        run_id=run_id,
        user_agent=request.headers.get("user-agent"),
        token_source=token_source,
    )

    workflow_id = payload.get("workflow_id")
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")

    task = (payload.get("task") or "").strip()
    if not task:
        raise HTTPException(status_code=400, detail="task required")

    tool_constraints = payload.get("tool_constraints")
    if tool_constraints is None:
        db = SessionLocal()
        try:
            metadata = workflow_runs.get_metadata(db, run_id=run_id)
        finally:
            db.close()
        if isinstance(metadata, dict):
            tool_constraints = metadata.get("tool_constraints")
    if tool_constraints is not None and not isinstance(tool_constraints, dict):
        raise HTTPException(status_code=400, detail="tool_constraints_must_be_object")

    logger.info(
        "Internal execute requested run_id=%s workflow_id=%s user_id=%s task_len=%s tool_constraints=%s",
        run_id,
        workflow_id,
        user_id,
        len(task),
        bool(tool_constraints),
    )

    providers_to_check = resolve_tool_constraint_providers(tool_constraints)
    status_check = check_connected_account_statuses(
        user_id,
        providers=providers_to_check,
    )
    blocked_providers = status_check.get("blocked_providers") or []
    if blocked_providers:
        detail = {
            "error": "oauth_refresh_required",
            "providers": blocked_providers,
            "reasons": status_check.get("reasons") or {},
        }
        logger.warning(
            "Internal execute blocked due to oauth refresh required run_id=%s workflow_id=%s user_id=%s providers=%s reasons=%s",
            run_id,
            workflow_id,
            user_id,
            blocked_providers,
            detail["reasons"],
        )
        db = SessionLocal()
        try:
            workflow_runs.merge_metadata(
                db,
                run_id=run_id,
                patch={
                    "oauth_refresh_required": {
                        "providers": blocked_providers,
                        "reasons": detail["reasons"],
                        "checked_at": datetime.now(timezone.utc).isoformat(),
                        "source": "pre_execute",
                    }
                },
            )
            workflow_runs.update_status(
                db,
                run_id=run_id,
                status="attention",
                summary="oauth_refresh_required",
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
        raise HTTPException(status_code=409, detail=detail)
    if not _runtime_proxy_enabled():
        controller_override = payload.get("controller")
        try:
            controller_data, workspace_info = _resolve_controller_session(user_id, controller_override, run_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc))

        payload = {**payload, "controller": controller_data, "task": task, "tool_constraints": tool_constraints}
        composed_plan = payload.get("composed_plan")

        request_obj = _parse_orchestrate_request(payload)
        if composed_plan is not None:
            setattr(request_obj, "composed_plan", composed_plan)
        workspace_info = payload.get("workspace") or workspace_info
        workspace_info = _attach_workspace_files(workspace_info, run_id)

        return _create_streaming_response(
            request_obj,
            user_id=user_id,
            tool_constraints=tool_constraints,
            workspace=workspace_info,
            run_id=run_id,
            workflow_id=workflow_id,
        )

    payload = {**payload, "task": task, "tool_constraints": tool_constraints}
    body = json.dumps(payload, default=str).encode("utf-8")
    return await proxy_request(request, stream=True, body=body)


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


async def _resume_run_local(run_id: str, current_user: CurrentUser) -> Dict[str, Any]:
    from server.api.controller_client import VMControllerClient
    from server.api.handback_inference import infer_human_action
    from shared.db.workflow_runs import merge_agent_states, decode_agent_states
    from orchestrator_agent.bridges import run_computer_use_agent_resume
    from computer_use_agent.orchestrator.data_types import OrchestrateRequest
    from orchestrator_agent.translator import translate_step_output
    from orchestrator_agent.data_types import StepResult, PlannedStep
    import base64

    user_id = current_user.sub
    db = SessionLocal()
    log_token: Optional[Any] = None
    run_handlers: Optional[Tuple[logging.Handler, logging.Handler]] = None

    try:
        run_handlers = _attach_run_log_handler(run_id)
        log_token = RUN_LOG_ID.set(run_id)

        row = workflow_runs.get_resume_row(db, run_id=run_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Run not found")

        row_user_id = row.get("user_id")
        row_status = row.get("status")
        row_agent_states = row.get("agent_states")
        row_environment = row.get("environment")

        if str(row_user_id) != str(user_id):
            raise HTTPException(status_code=403, detail="Not authorized to resume this run")

        if row_status != "attention":
            raise HTTPException(
                status_code=400,
                detail=f"Run is not in 'attention' status (current: {row_status})",
            )

        agent_states = decode_agent_states(row_agent_states)

        computer_use_state = agent_states.get("agents", {}).get("computer_use", {}) or {}
        orchestrator_state = agent_states.get("orchestrator")
        if isinstance(orchestrator_state, str):
            try:
                orchestrator_state = json.loads(orchestrator_state)
            except Exception:
                orchestrator_state = {}
        computer_use_snapshot = {
            "status": computer_use_state.get("status"),
            "completion_reason": computer_use_state.get("completion_reason"),
            "step_index_next": computer_use_state.get("step_index_next"),
            "trajectory_till_now": computer_use_state.get("trajectory_till_now", {}),
        }

        request_dict = computer_use_state.get("request") or {}
        cu_request: Optional[OrchestrateRequest] = None
        if request_dict:
            try:
                cu_request = OrchestrateRequest.from_dict(request_dict)
            except Exception as exc:
                logger.warning("Failed to rebuild OrchestrateRequest from snapshot: %s", exc)

        handback_request = computer_use_state.get("handback_request")
        before_screenshot_b64 = computer_use_state.get("handback_screenshot_b64")
        handback = computer_use_state.get("handback", {})

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
                detail="No controller endpoint found for this run",
            )
        if cu_request and controller_base_url:
            cu_request.controller.base_url = controller_base_url

        try:
            controller = VMControllerClient(base_url=controller_base_url)
            controller.wait_for_health()
            current_screenshot_bytes = controller.capture_screenshot()
            current_screenshot_b64 = base64.b64encode(current_screenshot_bytes).decode("utf-8")
        except Exception as e:
            logger.error("Failed to capture current screenshot: %s", e)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to capture current screenshot: {str(e)}",
            )

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

        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        resume_from_step = computer_use_snapshot.get("step_index_next", 0) + 1

        trajectory_snapshot = computer_use_snapshot.get("trajectory_till_now") or {}
        generator_messages = trajectory_snapshot.get("generator_messages") or []
        updated_generator_messages = copy.deepcopy(generator_messages)
        updated_generator_messages.append(
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": f"HANDBACK RESULT:\n{json.dumps(inference_result, ensure_ascii=False)}",
                    }
                ],
            }
        )
        updated_trajectory = {
            **trajectory_snapshot,
            "generator_messages": updated_generator_messages,
        }

        inference_update = {
            **computer_use_snapshot,
            "trajectory_till_now": updated_trajectory,
            "inference_result": inference_result,
            "latest_screenshot_b64": current_screenshot_b64,
        }

        try:
            merge_agent_states(run_id, inference_update, path=["agents", "computer_use"])
            logger.info("Updated agent_states with inference snapshot for run_id=%s", run_id)
        except Exception as e:
            logger.error("Failed to update agent_states with inference: %s", e)

        translated_resume: Dict[str, Any] = {}
        resume_trajectory = ""
        resume_step_result: Dict[str, Any] = {}
        resume_raw: Dict[str, Any] = {}
        try:
            resume_trajectory, resume_raw = run_computer_use_agent_resume(
                run_id=run_id,
                inference_update=inference_update,
                cu_request=cu_request,
                orchestrator_state=orchestrator_state,
            )
        except Exception as exc:
            logger.error("Resume CU execution failed: %s", exc, exc_info=True)

        overall_success = False
        error_msg: Optional[str] = None
        combined_trajectory = resume_trajectory
        try:
            prior_runner = (computer_use_state.get("runner") or {}).get("trajectory_md") or ""
            if prior_runner:
                combined_trajectory = prior_runner + "\n\n" + resume_trajectory
        except Exception:
            combined_trajectory = resume_trajectory
        try:
            translated_resume = translate_step_output(
                task=cu_request.task if cu_request else "",
                target="computer_use",
                trajectory=combined_trajectory,
                debug_step_id="resume-cu",
            )
            overall_success = bool(translated_resume.get("overall_success", translated_resume.get("success", True)))
            error_msg = translated_resume.get("error")
        except Exception as exc:
            logger.error("Failed to translate resume trajectory: %s", exc, exc_info=True)
            translated_resume = {
                "overall_success": False,
                "error": f"translation_failed: {exc}",
                "summary": "",
                "artifacts": {},
            }
            overall_success = False
            error_msg = translated_resume.get("error")

        plan_entries: List[PlannedStep] = []
        existing_results: List[StepResult] = []
        intermediate = {}
        cost_baseline = 0.0
        if isinstance(orchestrator_state, dict):
            intermediate = orchestrator_state.get("intermediate") or {}
            cost_baseline = orchestrator_state.get("cost_baseline", 0.0)
            try:
                plan_entries = [PlannedStep(**p) for p in (orchestrator_state.get("plan") or [])]
            except Exception as exc:
                logger.warning("Failed to hydrate plan from orchestrator_state: %s", exc)
            try:
                for res in orchestrator_state.get("results") or []:
                    try:
                        existing_results.append(StepResult(**res))
                    except Exception:
                        logger.warning("Failed to hydrate StepResult from orchestrator_state.")
            except Exception as exc:
                logger.warning("Failed to hydrate results from orchestrator_state: %s", exc)

        completed_ids = {res.step_id for res in existing_results}
        resume_planned = next((p for p in plan_entries if p.step_id not in completed_ids), None)
        if resume_planned is None:
            resume_planned = PlannedStep(
                step_id=f"resume-{run_id}",
                target="computer_use",
                next_task=cu_request.task if cu_request else "resume",
                verification="resume",
                max_steps=getattr(cu_request.worker, "max_steps", None) if cu_request else None,
                description="Resumed computer_use step",
                depends_on=[],
                hints={},
                metadata={},
            )

        status_flag = "completed" if overall_success else "failed"
        step_result_output = {
            "translated": translated_resume,
            "raw": resume_raw,
            "trajectory": combined_trajectory,
        }
        step_result_obj = StepResult.from_planned(
            resume_planned,
            status=status_flag,
            success=overall_success,
            output=step_result_output,
            error=error_msg,
            finished_at=datetime.utcnow(),
        )
        resume_step_result = asdict(step_result_obj)
        existing_results.append(step_result_obj)
        pending_after = [p for p in plan_entries if p.step_id not in {r.step_id for r in existing_results}]

        updated_orchestrator_state = {
            "status": "running",
            "loop_iteration": len(existing_results),
            "cost_baseline": cost_baseline,
            "plan": [asdict(p) for p in plan_entries],
            "results": [asdict(r) for r in existing_results],
            "intermediate": intermediate,
            "pending_steps": [asdict(p) for p in pending_after],
            "should_resume": True,
        }

        resume_update = {
            "handback": {
                **handback,
                "inference": inference_result,
                "resumed_at": now,
            },
            "continuation": {
                "should_inject_inference": True,
                "resume_from_step": resume_from_step,
                "resumed_at": now,
            },
        }

        resume_artifacts = {
            "resume": {
                "trajectory_md": resume_trajectory,
                "translated": translated_resume,
                "raw": resume_raw,
                "step_result": resume_step_result,
            }
        }

        try:
            merge_agent_states(
                run_id,
                {
                    **resume_artifacts,
                    **resume_update,
                },
                path=["agents", "computer_use"],
            )
            merge_agent_states(
                run_id,
                {"orchestrator": updated_orchestrator_state},
            )
            if translated_resume:
                merge_agent_states(
                    run_id,
                    {"last_resume_step": resume_step_result},
                    path=["agents", "orchestrator"],
                )
            logger.info("Updated agent_states with resume artifacts for run_id=%s", run_id)
        except Exception as e:
            logger.error("Failed to update agent_states with resume artifacts: %s", e)

        workflow_runs.update_status(
            db,
            run_id=run_id,
            status="queued",
            updated_at=now,
        )
        db.commit()

        _insert_run_event(
            run_id=run_id,
            kind="human_attention.resumed",
            message=f"Human intervention completed. Request fulfilled: {inference_result.get('request_fulfilled', False)}",
            payload={
                "inference": inference_result,
                "handback_request": handback_request,
                "resume_from_step": resume_from_step,
                "timestamp": now,
                "resume_translated": translated_resume,
                "resume_step_result": resume_step_result,
            },
        )

        return {
            "status": "resumed",
            "run_id": run_id,
            "inference": inference_result,
            "handback_request": handback_request,
            "resume_translated": translated_resume,
            "resume_trajectory": resume_trajectory,
            "resume_step_result": resume_step_result,
            "message": "Run resumed. The agent will continue with the inferred context.",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Resume run failed: %s", e, exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if log_token is not None:
            RUN_LOG_ID.reset(log_token)
        if run_handlers is not None:
            _detach_run_log_handler(run_handlers)
        db.close()


@app.post("/runs/{run_id}/resume")
async def resume_run(
    run_id: str,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> Response:
    """
    Proxy resume flow to runtime service.
    """
    if not _runtime_proxy_enabled():
        result = await _resume_run_local(run_id, current_user)
        return Response(content=json.dumps(result), media_type="application/json")
    return await proxy_request(request, stream=False)


__all__ = ["app"]
