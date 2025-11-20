"""Shared planner types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .state import StepType


@dataclass
class StepResult:
    """Structured result returned by the executor for each planner command."""

    type: StepType
    success: bool
    observation: Any
    preview: str
    error: Optional[str] = None
    raw_output_key: Optional[str] = None
    error_code: Optional[str] = None
