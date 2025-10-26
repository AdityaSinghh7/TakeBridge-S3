"""
FastAPI server that exposes the orchestrator loop.

Input/output contracts are defined in `framework.orchestrator.data_types`.
The endpoint performs dataclass validation and returns JSON payloads that
mirror those structures.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any, Dict

from fastapi import Body, FastAPI, HTTPException

from framework.orchestrator.data_types import OrchestrateRequest
from framework.orchestrator.runner import runner
from framework.utils.latency_logger import LATENCY_LOGGER

logger = logging.getLogger(__name__)

app = FastAPI(title="TakeBridge Orchestrator API", version="0.1.0")


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
    try:
        request = OrchestrateRequest.from_dict(payload)
    except Exception as exc:  # pragma: no cover - validation guard
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        with LATENCY_LOGGER.measure("server", "orchestrate"):  # total request latency
            result = runner(request)
    except Exception as exc:  # pragma: no cover - runtime guard
        logger.exception("Orchestration failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return asdict(result)


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
