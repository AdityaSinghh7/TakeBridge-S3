"""
Runtime FastAPI server that executes orchestrator runs and streams events.

Database operations are delegated to the control-plane internal API.
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import hashlib
import json
import logging
import mimetypes
import os
import secrets
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Dict, Optional, Tuple, List
from urllib.parse import urlparse

from fastapi import Body, FastAPI, HTTPException, Depends, Header, Request
from fastapi.responses import StreamingResponse, Response

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
    reset_current_emitter,
    set_current_emitter,
)
from shared.stdio import ensure_utf8_stdio
from vm_manager.vm_provider import create_agent_instance_for_user, current_provider, provider_spec
from vm_manager.config import settings
from shared.run_context import RUN_LOG_ID
from server.api.auth import get_current_user, CurrentUser
from server.api.controller_client import VMControllerClient
from server.api.handback_inference import infer_human_action
from server.api.orchestrator_adapter import orchestrate_to_orchestrator
from orchestrator_agent.summarizer import summarize_run
from server.api.drive_utils import normalize_drive_path
from shared.storage import get_attachment_storage, AttachmentStorageError

from runtime.api.control_plane_client import ControlPlaneClient, ControlPlaneError
from runtime.api.run_drive import (
    stage_drive_files_for_run,
    DriveStageError,
    detect_drive_changes,
    commit_drive_changes_for_run,
    DRIVE_VM_BASE_PATH,
    DOWNLOAD_CHUNK_BYTES,
)

PERSISTED_EVENTS = {
    "orchestrator.planning.completed",
    "orchestrator.step.completed",
    "orchestrator.task.completed",
    "orchestrator.summary.created",
    "runner.started",
    "runner.step.agent_response",
    "runner.step.behavior",
    "runner.step.completed",
    "runner.completed",
    "worker.reflection.summary",
    "worker.step.ready",
    "code_agent.session.started",
    "code_agent.session.completed",
    "code_agent.step.response",
    "code_agent.step.execution",
    "code_agent.step.completed",
    "grounding.generate_coords.service_failed",
    "grounding.generate_text_coords.started",
    "grounding.generate_text_coords.completed",
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
    "human_attention.required",
    "human_attention.resumed",
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

_RUNTIME_MAX_CONCURRENT_RUNS = int(os.getenv("RUNTIME_MAX_CONCURRENT_RUNS", "0"))
_RUNTIME_MAX_CONCURRENT_RUNS_PER_USER = int(os.getenv("RUNTIME_MAX_CONCURRENT_RUNS_PER_USER", "0"))
_RUN_SEMAPHORE = asyncio.Semaphore(_RUNTIME_MAX_CONCURRENT_RUNS) if _RUNTIME_MAX_CONCURRENT_RUNS > 0 else None
_USER_SEMAPHORES: Dict[str, asyncio.Semaphore] = {}
_USER_SEMAPHORE_LOCK = asyncio.Lock()


@contextlib.asynccontextmanager
async def _run_slot(user_id: Optional[str]):
    """Gate concurrent runs (global + per-user) when configured."""
    run_sem = _RUN_SEMAPHORE
    user_sem: Optional[asyncio.Semaphore] = None

    if run_sem is not None:
        await run_sem.acquire()

    if _RUNTIME_MAX_CONCURRENT_RUNS_PER_USER > 0 and user_id:
        async with _USER_SEMAPHORE_LOCK:
            user_sem = _USER_SEMAPHORES.get(user_id)
            if user_sem is None:
                user_sem = asyncio.Semaphore(_RUNTIME_MAX_CONCURRENT_RUNS_PER_USER)
                _USER_SEMAPHORES[user_id] = user_sem
        await user_sem.acquire()

    try:
        yield
    finally:
        if user_sem is not None:
            user_sem.release()
        if run_sem is not None:
            run_sem.release()


def _token_fingerprint(token: str) -> str:
    if not token:
        return "unset"
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:10]


logger.info(
    "Runtime Config INTERNAL_API_TOKEN_set=%s INTERNAL_API_TOKEN_fp=%s CONTROL_PLANE_BASE_URL=%s",
    bool((os.getenv("INTERNAL_API_TOKEN") or "").strip()),
    _token_fingerprint((os.getenv("INTERNAL_API_TOKEN") or "").strip()),
    os.getenv("CONTROL_PLANE_BASE_URL", "https://127.0.0.1:8000"),
)

logger.info("Starting Runtime API")


class _RunLogFilter(logging.Filter):
    """Filter that only allows records when the current run_id matches."""

    def __init__(self, run_id: str) -> None:
        super().__init__()
        self.run_id = run_id

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - thin helper
        current = RUN_LOG_ID.get()
        record.run_id = current or self.run_id or ""  # type: ignore[attr-defined]
        if current is None:
            return True
        return current == self.run_id


def _attach_run_log_handler(run_id: str) -> tuple[logging.Handler, logging.Handler]:
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
    # Startup: warm MCP (registry is DB-backed; control-plane owns DB reads)
    try:
        from mcp_agent.user_identity import normalize_user_id  # type: ignore

        user_env = os.getenv("TB_USER_ID")
        if not user_env:
            logger.info("Skipping MCP warmup: TB_USER_ID not set.")
        else:
            try:
                user_id = normalize_user_id(user_env)
                logger.info("MCP warmup for user: %s", user_id)
            except ValueError:
                logger.warning("Skipping MCP warmup: invalid TB_USER_ID.")
    except Exception:
        pass

    yield


app = FastAPI(title="TakeBridge Runtime API", version="0.1.0", lifespan=app_lifespan)

# Treat the API server as non-interactive so Ctrl+C exits immediately.
agent_signal.set_interactive_mode(False)


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
        with LATENCY_LOGGER.measure("runtime", "orchestrate"):
            control_plane = ControlPlaneClient()

            def agent_states_provider(run_id: str) -> Dict[str, Any]:
                try:
                    return control_plane.get_agent_states(run_id)
                except ControlPlaneError as exc:
                    logger.warning(
                        "Failed to fetch agent_states from control plane for run_id=%s: %s",
                        run_id,
                        exc,
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to fetch agent_states from control plane for run_id=%s: %s",
                        run_id,
                        exc,
                    )
                return {}

            runtime = OrchestratorRuntime(agent_states_provider=agent_states_provider)
            return await runtime.run_task(request)
    except BaseException as exc:  # pragma: no cover - runtime guard
        logger.exception("Orchestration failed: %s", exc)
        raise
    finally:
        if token:
            reset_current_emitter(token)


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
    try:
        ControlPlaneClient().persist_run_event(run_id, event, payload=data if isinstance(data, dict) else {}, message=message)
    except Exception:
        logger.debug("Failed to persist run event via control-plane run_id=%s event=%s", run_id, event)




async def _persist_run_summary(run_id: str, result_dict: Dict[str, Any]) -> None:
    try:
        summary_payload = await summarize_run(run_id, result_dict)
    except Exception as exc:
        logger.warning("Summarizer failed run_id=%s: %s", run_id, exc)
        return
    try:
        await asyncio.to_thread(
            _persist_run_event,
            run_id,
            "orchestrator.summary.created",
            summary_payload,
        )
    except Exception as exc:
        logger.warning("Failed to persist summary run_id=%s: %s", run_id, exc)


def _update_run_status(run_id: str, status: str, summary: Optional[str] = None):
    try:
        ControlPlaneClient().update_run_status(run_id, status, summary=summary)
    except Exception:
        logger.debug("Failed to update run status run_id=%s status=%s", run_id, status)


def _merge_run_environment(run_id: str, patch: Dict[str, Any]) -> None:
    try:
        ControlPlaneClient().merge_environment(run_id, patch)
    except Exception:
        logger.debug("Failed to merge run environment run_id=%s", run_id)


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
        ControlPlaneClient().register_vm(
            run_id,
            vm_id=workspace_info["id"],
            endpoint=endpoint,
            provider=current_provider(),
            spec=provider_spec(),
        )

    return controller_payload, workspace_info


def _resolve_controller_session(
    user_id: str,
    controller_override: Optional[Dict[str, Any]] = None,
    run_id: Optional[str] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    if controller_override and controller_override.get("base_url"):
        return _normalize_controller_payload(controller_override)

    if run_id:
        try:
            context = ControlPlaneClient().get_run_context(run_id)
            env = context.get("environment") or {}
        except Exception:
            env = {}
        if env:
            endpoint = env.get("endpoint") if isinstance(env, dict) else None
            if isinstance(endpoint, str):
                try:
                    endpoint = json.loads(endpoint)
                except Exception:
                    endpoint = None
            if isinstance(endpoint, dict):
                base_url = endpoint.get("controller_base_url") or endpoint.get("base_url")
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
            _persist_run_event(run_id, event, data)

    emitter = StreamEmitter(_publish)

    async def _emit_keepalive(interval: float = 15.0) -> None:
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
            async with _run_slot(user_id):
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
                log_token = RUN_LOG_ID.set(run_id_local)

                heartbeat = asyncio.create_task(_emit_keepalive())

                logger.info("Executing orchestrator_agent request")
                result = await _execute_orchestrator(orch_request, emitter)

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
                if result_dict.get("status") != "attention":
                    summary = "; ".join(
                        [
                            r.get("final_summary") or ""
                            for r in result_dict.get("steps", [])
                            if isinstance(r, dict)
                        ]
                    )
                    _update_run_status(run_id, result_dict.get("status") or "success", summary=summary or None)
                    asyncio.create_task(_persist_run_summary(run_id, result_dict))
        finally:
            committed_drive_changes: List[Dict[str, Any]] = []
            if run_id_local and workspace:
                try:
                    detect_drive_changes(run_id_local, workspace)
                except Exception as exc:
                    logger.warning("Failed to detect drive changes for run %s: %s", run_id_local, exc)
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
    payload: Dict[str, Any] = Body(...),
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """Run a single orchestrator task (non-streaming)."""
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
        async with _run_slot(user_id):
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

    return {
        "task": orch_request.task,
        "status": run_status,
        "completion_reason": completion_reason,
        "steps": [asdict(r) for r in result.results],
    }


@app.get("/orchestrate/stream")
async def orchestrate_stream(task: str) -> StreamingResponse:
    """Backward-compatible streaming endpoint that only accepts a `task` query param."""
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
    """Streaming endpoint with full payload support."""
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

    request = _parse_orchestrate_request(payload)
    if composed_plan is not None:
        setattr(request, "composed_plan", composed_plan)

    workspace_info = payload.get("workspace") or workspace_info
    workspace_info = _attach_workspace_files(workspace_info, run_id)

    return _create_streaming_response(request, user_id, tool_constraints, workspace_info, run_id=run_id)


@app.post("/internal/runs/{run_id}/execute")
async def internal_execute_run(
    run_id: str,
    request: Request,
    payload: Dict[str, Any] = Body(...),
    x_internal_token: Optional[str] = Header(default=None, alias="X-Internal-Token"),
    authorization: Optional[str] = Header(default=None),
) -> StreamingResponse:
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
        try:
            context = ControlPlaneClient().get_run_context(run_id)
        except Exception:
            context = {}
        else:
            tool_constraints = context.get("tool_constraints")
            context_user_id = context.get("user_id")
            if context_user_id and str(context_user_id) != str(user_id):
                raise HTTPException(status_code=400, detail="user_id_mismatch")
    if tool_constraints is not None and not isinstance(tool_constraints, dict):
        raise HTTPException(status_code=400, detail="tool_constraints_must_be_object")

    logger.info(
        "Runtime execute requested run_id=%s workflow_id=%s user_id=%s task_len=%s tool_constraints=%s",
        run_id,
        workflow_id,
        user_id,
        len(task),
        bool(tool_constraints),
    )

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


@app.get("/config")
async def config_defaults() -> Dict[str, Any]:
    """Return the default orchestrator configuration."""
    return {
        "controller": DEFAULT_CONTROLLER_CONFIG,
        "worker": DEFAULT_WORKER_CONFIG,
        "grounding": DEFAULT_GROUNDING_CONFIG,
    }


@app.post("/compose_task")
async def compose_task(
    payload: Dict[str, Any] = Body(...),
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    from orchestrator_agent.capabilities import _normalize_platform
    from orchestrator_agent.composer import compose_plan

    task = (payload.get("task") or "").strip()
    if not task:
        raise HTTPException(status_code=400, detail="Field 'task' is required and must be non-empty.")

    user_id: str = current_user.sub
    logger.info("compose_task called user_id=%s task_len=%s", user_id, len(task))

    # Fetch MCP capabilities from control-plane
    try:
        mcp_caps = ControlPlaneClient().fetch_mcp_capabilities(user_id, force_refresh=False)
    except Exception as exc:
        logger.warning("Failed to fetch MCP capabilities via control-plane: %s", exc)
        mcp_caps = {"providers": []}

    platform_override = payload.get("platform")
    platform = _normalize_platform(platform_override) if platform_override else None

    stub_apps = [
        "edge",
        "libreoffice",
        "libreoffice-writer",
        "libreoffice-calc",
        "libreoffice-impress",
        "libreoffice-base",
        "libreoffice-math",
        "notepad",
        "powershell",
        "cmd",
    ]
    try:
        from computer_use_agent.grounding.grounding_agent import list_osworld_agent_actions

        resolved_actions = list_osworld_agent_actions()
    except Exception as exc:
        logger.warning("Failed to load computer actions for compose_task: %s", exc)
        resolved_actions = []
    computer_caps = {
        "platform": platform or "windows",
        "available_apps": stub_apps,
        "active_windows": [],
        "actions": resolved_actions,
    }

    capabilities = {
        "mcp": mcp_caps,
        "computer": computer_caps,
    }

    tool_constraints = payload.get("tool_constraints")
    plan = compose_plan(task, capabilities, tool_constraints=tool_constraints)
    draft_id = str(uuid.uuid4())
    suggested_name = payload.get("name") or task[:80]
    suggested_description = payload.get("description")

    return {
        "plan": plan,
        "suggested_name": suggested_name,
        "suggested_description": suggested_description,
        "draft_id": draft_id,
    }


@app.post("/runs/{run_id}/resume")
async def resume_run(
    run_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """Resume a run that was paused for human attention."""
    from shared.db.workflow_runs import decode_agent_states
    from orchestrator_agent.bridges import run_computer_use_agent_resume
    from computer_use_agent.orchestrator.data_types import OrchestrateRequest
    from orchestrator_agent.translator import translate_step_output
    from orchestrator_agent.data_types import StepResult, PlannedStep
    import base64

    user_id = current_user.sub
    log_token: Optional[Any] = None
    run_handlers: Optional[Tuple[logging.Handler, logging.Handler]] = None
    control_plane = ControlPlaneClient()

    try:
        run_handlers = _attach_run_log_handler(run_id)
        log_token = RUN_LOG_ID.set(run_id)

        context = control_plane.get_resume_context(run_id)
        row_user_id = context.get("user_id")
        row_status = context.get("status")
        row_agent_states = context.get("agent_states")
        row_environment = context.get("environment") or {}

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
            raise HTTPException(status_code=400, detail="No controller endpoint found for this run")
        if cu_request and controller_base_url:
            cu_request.controller.base_url = controller_base_url

        try:
            controller = VMControllerClient(base_url=controller_base_url)
            controller.wait_for_health()
            current_screenshot_bytes = controller.capture_screenshot()
            current_screenshot_b64 = base64.b64encode(current_screenshot_bytes).decode("utf-8")
        except Exception as e:
            logger.error("Failed to capture current screenshot: %s", e)
            raise HTTPException(status_code=500, detail=f"Failed to capture current screenshot: {str(e)}")

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
            control_plane.merge_agent_states(run_id, inference_update, path=["agents", "computer_use"])
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
            control_plane.merge_agent_states(
                run_id,
                {
                    **resume_artifacts,
                    **resume_update,
                },
                path=["agents", "computer_use"],
            )
            control_plane.merge_agent_states(run_id, {"orchestrator": updated_orchestrator_state})
            if translated_resume:
                control_plane.merge_agent_states(
                    run_id,
                    {"last_resume_step": resume_step_result},
                    path=["agents", "orchestrator"],
                )
            logger.info("Updated agent_states with resume artifacts for run_id=%s", run_id)
        except Exception as e:
            logger.error("Failed to update agent_states with resume artifacts: %s", e)

        try:
            control_plane.update_run_status(run_id, "queued", summary=None)
        except Exception:
            logger.warning("Failed to update run status for resume run_id=%s", run_id)

        _persist_run_event(
            run_id=run_id,
            event="human_attention.resumed",
            data={
                "message": "Human intervention completed.",
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

    except ControlPlaneError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Resume run failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if log_token is not None:
            RUN_LOG_ID.reset(log_token)
        if run_handlers is not None:
            _detach_run_log_handler(run_handlers)


@app.post("/api/runs/{run_id}/commit-drive-file")
def commit_drive_file(
    run_id: str,
    payload: Dict[str, Any] = Body(default_factory=dict),
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    path_raw = payload.get("path") or payload.get("drive_path")
    if not path_raw:
        raise HTTPException(status_code=400, detail="drive_path_required")
    try:
        drive_path = normalize_drive_path(str(path_raw))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    control_plane = ControlPlaneClient()
    context = control_plane.get_run_context(run_id)
    if str(context.get("user_id")) != str(current_user.sub):
        raise HTTPException(status_code=404, detail="run_not_found")
    changes = control_plane.list_drive_changes(run_id)
    change_rows = changes.get("changes") or []
    drive_rows = changes.get("drive_files") or []

    change_row = next((row for row in change_rows if row.get("path") == drive_path), None)
    if not change_row:
        raise HTTPException(status_code=404, detail="drive_change_not_found")

    drive_row = next((row for row in drive_rows if row.get("drive_path") == drive_path), None)
    if not drive_row:
        raise HTTPException(status_code=404, detail="drive_file_not_found")

    env = context.get("environment") or {}
    endpoint = env.get("endpoint") if isinstance(env, dict) else {}
    controller_base_url = (endpoint or {}).get("controller_base_url")
    if not controller_base_url:
        raise HTTPException(status_code=400, detail="controller_base_url_missing")

    try:
        storage = get_attachment_storage()
    except AttachmentStorageError as exc:
        logger.error("Attachment storage misconfigured: %s", exc)
        raise HTTPException(status_code=500, detail="attachments_not_configured")

    content_type = change_row.get("content_type") or mimetypes.guess_type(drive_path)[0] or DEFAULT_ATTACHMENT_CONTENT_TYPE
    presigned_put_url = storage.generate_presigned_put(change_row.get("r2_key"), content_type=content_type)

    controller = VMControllerClient(base_url=controller_base_url)
    controller.wait_for_health()
    windows = ":" in DRIVE_VM_BASE_PATH or "\\" in DRIVE_VM_BASE_PATH
    vm_path = drive_row.get("vm_path")
    if not vm_path:
        if windows:
            vm_path = str(PureWindowsPath(DRIVE_VM_BASE_PATH, *drive_path.split("/")))
        else:
            vm_path = str(PurePosixPath(DRIVE_VM_BASE_PATH, *drive_path.split("/")))

    try:
        controller.upload_file_to_url(vm_path, presigned_put_url, content_type=content_type)
    except Exception as exc:
        logger.error("[drive] failed to upload %s to R2: %s", vm_path, exc)
        raise HTTPException(status_code=500, detail="drive_upload_failed")

    return {
        "path": drive_path,
        "r2_key": change_row.get("r2_key"),
        "content_type": content_type,
        "size": change_row.get("size_bytes"),
        "status": "uploaded",
    }


@app.get("/api/runs/{run_id}/drive-file")
def download_drive_file(
    run_id: str,
    path: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    try:
        drive_path = normalize_drive_path(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    control_plane = ControlPlaneClient()
    context = control_plane.get_run_context(run_id)
    if str(context.get("user_id")) != str(current_user.sub):
        raise HTTPException(status_code=404, detail="run_not_found")

    response = control_plane.get_drive_files(run_id, ensure_full=False)
    row = next((r for r in (response.get("files") or []) if r.get("drive_path") == drive_path), None)
    if not row:
        raise HTTPException(status_code=404, detail="drive_file_not_found")

    env = context.get("environment") or {}
    endpoint = env.get("endpoint") if isinstance(env, dict) else {}
    controller_base_url = (endpoint or {}).get("controller_base_url")
    if not controller_base_url:
        raise HTTPException(status_code=400, detail="controller_base_url_missing")

    controller = VMControllerClient(base_url=controller_base_url)
    controller.wait_for_health()
    windows = ":" in DRIVE_VM_BASE_PATH or "\\" in DRIVE_VM_BASE_PATH
    vm_path = row.get("vm_path")
    if not vm_path:
        if windows:
            vm_path = str(PureWindowsPath(DRIVE_VM_BASE_PATH, *drive_path.split("/")))
        else:
            vm_path = str(PurePosixPath(DRIVE_VM_BASE_PATH, *drive_path.split("/")))
    content_type = row.get("content_type") or mimetypes.guess_type(drive_path)[0] or DEFAULT_ATTACHMENT_CONTENT_TYPE

    def _iter_stream():
        with controller.stream_file(vm_path) as resp:
            for chunk in resp.iter_content(chunk_size=DOWNLOAD_CHUNK_BYTES):
                if chunk:
                    yield chunk

    return StreamingResponse(_iter_stream(), media_type=content_type)


__all__ = ["app"]
