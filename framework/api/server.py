"""
FastAPI server that exposes the orchestrator loop.

Input/output contracts are defined in `framework.orchestrator.data_types`.
The endpoint performs dataclass validation and returns JSON payloads that
mirror those structures.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import json
import logging
import time
from dataclasses import asdict
from typing import Any, Dict, Optional

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from framework.orchestrator.data_types import (
    DEFAULT_CONTROLLER_CONFIG,
    DEFAULT_GROUNDING_CONFIG,
    DEFAULT_WORKER_CONFIG,
    OrchestrateRequest,
    WorkerConfig,
    GroundingConfig,
    ControllerConfig,
)
from framework.orchestrator.runner import runner
from framework.utils.latency_logger import LATENCY_LOGGER
from framework.utils import agent_signal
from framework.utils.streaming import (
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

app = FastAPI(title="TakeBridge Orchestrator API", version="0.1.0")
logger.info("API initialized")

# Treat the API server as non-interactive so Ctrl+C exits immediately.
agent_signal.set_interactive_mode(False)


def _parse_orchestrate_request(payload: Dict[str, Any]) -> OrchestrateRequest:
    try:
        return OrchestrateRequest.from_dict(payload)
    except Exception as exc:  # pragma: no cover - validation guard
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _execute_runner(
    request: OrchestrateRequest, emitter: Optional[StreamEmitter] = None
):
    """Execute the runner with optional stream emission."""
    # logger.info(f"GEMINI_DEBUG: Emitter received in thread: {emitter}")
    token = None
    if emitter:
        token = set_current_emitter(emitter)
        # logger.info(f"GEMINI_DEBUG: Emitter after set: {get_current_emitter()}")
    try:
        with LATENCY_LOGGER.measure("server", "orchestrate"):  # total request latency
            return runner(request)
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


@app.post("/orchestrate")
async def orchestrate(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """
    Run a single orchestrator loop using the shared dataclass contracts.
    Only the `task` field is required in the payload. Optional sections:
      - worker: overrides worker configuration (engine params, reflection, etc.)
      - grounding: overrides grounding/code agent configuration
      - controller: overrides VM controller connection details
      - platform / enable_code_execution: optional execution flags

    Grounding defaults:
      - `RUNPOD_ID` (from environment) is used to derive
        `https://<RUNPOD_ID>-3005.proxy.runpod.net` as the base URL.
      - `RUNPOD_API_KEY` (from environment) is added as a Bearer token when present.
      - The `/call_llm` path is automatically appended for coordinate inference.
      - No system prompt is sent for coordinate grounding unless supplied.
    """
    request = _parse_orchestrate_request(payload)
    try:
        result = _execute_runner(request)
    except Exception as exc:  # pragma: no cover - runtime guard
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return asdict(result)


@app.get("/orchestrate/stream")
async def orchestrate_stream(task: str) -> StreamingResponse:
    """
    Run the orchestrator loop and stream lifecycle updates back to the client via SSE.
    """
    request = OrchestrateRequest(
        task=task,
        worker=WorkerConfig.from_dict({}),
        grounding=GroundingConfig.from_dict({}),
        controller=ControllerConfig.from_dict({}),
    )
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
        # logger.info("GEMINI_DEBUG: Starting to drain queue")
        try:
            while True:
                chunk = await queue.get()
                if chunk is None:
                    # logger.info("GEMINI_DEBUG: Received None, breaking")
                    break
                # logger.info(f"GEMINI_DEBUG: Yielding chunk: {chunk!r}")
                yield chunk
                await asyncio.sleep(0.01)
        finally:
            # logger.info("GEMINI_DEBUG: Draining queue finished")
            while not queue.empty():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

    async def _run_and_stream() -> None:
        heartbeat = None
        try:
            heartbeat = asyncio.create_task(_emit_keepalive())
            logger.info(f"GEMINI_DEBUG: Emitter before thread: {emitter}")
            result = await asyncio.to_thread(_execute_runner, request, emitter)
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
            result_dict = asdict(result)
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
