"""
FastAPI server that exposes the orchestrator loop.

Input/output contracts are defined in `framework.orchestrator.data_types`.
The endpoint performs dataclass validation and returns JSON payloads that
mirror those structures.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict
from typing import Any, Dict, Optional

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from framework.orchestrator.data_types import (
    DEFAULT_CONTROLLER_CONFIG,
    DEFAULT_GROUNDING_CONFIG,
    DEFAULT_WORKER_CONFIG,
    OrchestrateRequest,
)
from framework.orchestrator.runner import runner
from framework.utils.latency_logger import LATENCY_LOGGER
from framework.utils.streaming import (
    StreamEmitter,
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


def _parse_orchestrate_request(payload: Dict[str, Any]) -> OrchestrateRequest:
    try:
        return OrchestrateRequest.from_dict(payload)
    except Exception as exc:  # pragma: no cover - validation guard
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _execute_runner(request: OrchestrateRequest):
    try:
        with LATENCY_LOGGER.measure("server", "orchestrate"):  # total request latency
            return runner(request)
    except Exception as exc:  # pragma: no cover - runtime guard
        logger.exception("Orchestration failed: %s", exc)
        raise


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


@app.post("/orchestrate/stream")
async def orchestrate_stream(payload: Dict[str, Any] = Body(...)) -> StreamingResponse:
    """
    Run the orchestrator loop and stream lifecycle updates back to the client via SSE.
    """
    request = _parse_orchestrate_request(payload)
    queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    queue.put_nowait(_format_sse_event("response.created", {"status": "accepted"}))
    queue.put_nowait(_format_sse_event("response.in_progress", {"status": "running"}))

    def _publish(event: str, data: Optional[Any] = None) -> None:
        chunk = _format_sse_event(event, data)
        loop.call_soon_threadsafe(queue.put_nowait, chunk)

    emitter = StreamEmitter(_publish)

    async def _drain_queue():
        try:
            while True:
                chunk = await queue.get()
                if chunk is None:
                    break
                yield chunk
        finally:
            while not queue.empty():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

    async def _run_and_stream() -> None:
        try:
            token = set_current_emitter(emitter)
            try:
                result = await loop.run_in_executor(None, _execute_runner, request)
            finally:
                reset_current_emitter(token)
        except Exception as exc:  # pragma: no cover - runtime guard
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
