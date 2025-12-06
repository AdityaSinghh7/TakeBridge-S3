from __future__ import annotations

"""
Composable task plan data structures for the orchestrator.

These are intentionally lightweight and JSON-friendly so they can be:
- Returned directly from the compose endpoint to the frontend
- Edited by users
- Attached to OrchestratorRequest as a strong planning hint
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Literal, Optional, Any


StepType = Literal["mcp", "cua"]


@dataclass
class ComposedStep:
    """Single executable step in a composed plan.

    This is the tool/app-level unit of work that the orchestrator should
    ultimately help execute, either via MCP tools or computer-use actions.
    """

    id: str
    type: StepType
    description: str

    # MCP-only fields
    provider_id: Optional[str] = None
    tool_id: Optional[str] = None
    tool_name: Optional[str] = None

    # Computer-use-only fields
    app_name: Optional[str] = None
    action_kind: Optional[str] = None

    # Optional prompt snippet to send to the main agent loop.
    # Example: "Use gmail_search tool to retrieve the last 2 emails from the inbox."
    prompt: Optional[str] = None
    # High-level result for this step (data to retrieve or success criteria for actions).
    expected_outcome: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ComposedPlan:
    """Top-level composed plan exchanged with the frontend."""

    schema_version: int
    original_task: str
    steps: List[ComposedStep] = field(default_factory=list)
    notes: Optional[str] = None
    # Optional convenience field: concatenated prompts for all steps,
    # suitable to send as the orchestrator task instead of the raw input.
    combined_prompt: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "schema_version": self.schema_version,
            "original_task": self.original_task,
            "notes": self.notes,
            "steps": [s.to_dict() for s in self.steps],
            "combined_prompt": self.combined_prompt,
        }


__all__ = [
    "ComposedPlan",
    "ComposedStep",
    "StepType",
]

