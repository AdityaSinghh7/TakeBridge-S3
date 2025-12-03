"""Shared planner types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, TypedDict

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
    is_smart_summary: bool = False
    original_tokens: Optional[int] = None
    compressed_tokens: Optional[int] = None
    # Resolved tool metadata (set for tool commands)
    tool_id: Optional[str] = None
    provider: Optional[str] = None
    server: Optional[str] = None
    tool_name: Optional[str] = None
    args: Optional[Dict[str, Any]] = None


class MCPTaskResult(TypedDict, total=False):
    success: bool
    final_summary: str
    error: Optional[str]
    error_code: Optional[str]
    error_message: Optional[str]
    error_details: dict[str, Any]
    user_id: str
    run_id: str
    raw_outputs: dict[str, Any]
    budget_usage: dict[str, Any]
    logs: list[dict[str, Any]]
    steps: list[dict[str, Any]]
    trajectory_md: str  # Rich self-contained markdown trajectory for orchestrator
