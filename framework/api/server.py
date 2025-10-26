"""
FastAPI server that exposes the orchestrator loop.

Input/output contracts are defined in `framework.orchestrator.data_types`.
The endpoint performs dataclass validation and returns JSON payloads that
mirror those structures.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, is_dataclass
from typing import Any, Dict

from fastapi import Body, FastAPI, HTTPException


logger = logging.getLogger(__name__)

app = FastAPI(title="TakeBridge Orchestrator API", version="0.1.0")


def _dataclass_to_dict(instance: Any) -> Dict[str, Any]:
    if is_dataclass(instance):
        return asdict(instance)
    raise TypeError(f"Expected dataclass instance, got {type(instance)!r}")


@app.post("/orchestrate")
async def orchestrate(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """
    Run a single orchestrator loop using the shared dataclass contracts.
    """
    

    return None


__all__ = ["app"]
