"""Execution history management for agent state.

Manages the step-by-step trajectory of agent execution, including:
- Recording steps (thoughts, actions, observations)
- Context window management
- Observation summarization for LLM consumption
- Trajectory formatting
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

StepType = Literal["tool", "sandbox", "search", "finish", "fail"]


@dataclass
class AgentStep:
    """Canonical step in agent execution history."""

    action_step: int
    action_type: StepType
    success: bool
    action_reasoning: str
    action_input: Dict[str, Any]
    action_outcome: Dict[str, Any]
    error: Optional[str] = None
    is_smart_summary: bool = False
    observation: Optional[Any] = None
    observation_metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "action_step": self.action_step,
            "action_type": self.action_type,
            "success": self.success,
            "action_reasoning": self.action_reasoning,
            "action_input": self.action_input,
            "action_outcome": self.action_outcome,
            "error": self.error,
            "is_smart_summary": self.is_smart_summary,
            "observation": self.observation,
            "observation_metadata": self.observation_metadata,
        }


class ExecutionHistory:
    """Manages execution history and trajectory formatting.

    Responsibilities:
    - Store execution steps (thoughts, actions, observations)
    - Manage context window (trim old steps when needed)
    - Summarize observations for LLM consumption
    - Build trajectory for planner state

    NOT responsible for:
    - Executing actions (see executor.py)
    - Making decisions (see orchestrator.py)
    - Tool discovery or caching (see tool_cache.py)
    """

    def __init__(self) -> None:
        """Initialize empty history."""
        self._history: List[AgentStep] = []

    @property
    def history(self) -> List[AgentStep]:
        """Get read-only view of history."""
        return self._history

    @property
    def steps_taken(self) -> int:
        """Get total number of steps taken."""
        return len(self._history)

    def record_step(
        self,
        *,
        action_type: StepType,
        success: bool,
        action_reasoning: str,
        action_input: Dict[str, Any],
        action_outcome: Dict[str, Any],
        error: Optional[str] = None,
        is_smart_summary: bool = False,
        observation: Optional[Any] = None,
        observation_metadata: Optional[Dict[str, Any]] = None,
    ) -> AgentStep:
        """Add a canonical step to execution history."""
        step = AgentStep(
            action_step=len(self._history),
            action_type=action_type,
            success=success,
            action_reasoning=action_reasoning,
            action_input=action_input,
            action_outcome=action_outcome,
            error=error,
            is_smart_summary=is_smart_summary,
            observation=observation,
            observation_metadata=observation_metadata,
        )
        self._history.append(step)
        return step

    def get_context_window(self, max_steps: Optional[int] = None) -> List[AgentStep]:
        """Get recent history within limits.

        Args:
            max_steps: Maximum number of steps to return (None = all)

        Returns:
            List of recent steps (oldest first)
        """
        if max_steps is None or max_steps <= 0:
            return self._history
        return self._history[-max_steps:]

    def build_trajectory(self) -> List[Dict[str, Any]]:
        """Build a structured trajectory from canonical AgentSteps (no formatted text)."""
        trajectory: List[Dict[str, Any]] = []

        def _fmt(obj: Any) -> Any:
            if obj is None:
                return None
            if isinstance(obj, dict):
                return dict(obj)
            return obj

        for step in self._history:
            trajectory.append(
                {
                    "step": step.action_step,
                    "type": step.action_type,
                    "action_reasoning": step.action_reasoning,
                    "action_input": _fmt(step.action_input),
                    "action_outcome": _fmt(step.action_outcome),
                    "success": step.success,
                    "error": step.error,
                    "is_smart_summary": step.is_smart_summary,
                    "observation": _fmt(step.observation),
                }
            )

        return trajectory

    @staticmethod
    def summarize_tool_observation(observation: Dict[str, Any]) -> str:
        """Summarize tool execution results: key fields only.

        This is a static helper that can be used by executor to create
        observation summaries before recording the step.

        Full results are stored in raw_outputs if needed for reference.
        """
        if not observation:
            return "No output"

        # Check if it's a successful result
        if isinstance(observation, dict):
            if observation.get("error"):
                error_msg = str(observation.get("error", "Unknown error"))
                return f"Error: {error_msg[:100]}"

            if "successful" in observation:
                if not observation["successful"]:
                    error_msg = observation.get("error", "Unknown failure")
                    return f"Failed: {error_msg[:100]}"

                # Summarize successful data
                data = observation.get("data", {})
                return ExecutionHistory._summarize_data_payload(data)

        # Fall back to generic summarization
        return ExecutionHistory._summarize_data_payload(observation)

    @staticmethod
    def summarize_sandbox_observation(observation: Dict[str, Any]) -> str:
        """Format sandbox execution results for trajectory.

        Unlike tool calls, sandbox code is expected to return compact summaries,
        so we show the full return value (up to reasonable limit) rather than
        summarizing further.
        """
        if not observation:
            return "No output"

        # Check for errors
        if isinstance(observation, dict):
            if observation.get("error"):
                error_msg = str(observation.get("error", "Unknown error"))
                return f"Error: {error_msg[:200]}"

            # Show the full result/return value from sandbox code
            # The code should already be returning compact summaries
            if "result" in observation:
                result = observation["result"]
                # Return full result up to 1000 chars (sandbox should keep it compact)
                result_str = str(result) if not isinstance(result, str) else result
                if len(result_str) <= 1000:
                    return result_str
                else:
                    return result_str[:997] + "..."

            # If no result field, show success status
            if observation.get("successful"):
                return "Execution completed successfully"

        # Fallback to string representation
        obs_str = str(observation)
        return obs_str[:1000] if len(obs_str) <= 1000 else obs_str[:997] + "..."

    @staticmethod
    def _summarize_data_payload(data: Any, max_chars: int = 500) -> str:
        """Smart data summarization showing actual values, not just structure.

        For tool call results, we want the model to see:
        - Array lengths (e.g., "messages: 0 items")
        - Numeric values (e.g., "resultSizeEstimate: 0")
        - Short strings (e.g., "status: active")
        - Text previews (e.g., "body: Hello world...")

        This allows the model to understand what actually happened without
        seeing full payloads.
        """
        if data is None:
            return "null"

        if isinstance(data, bool):
            return str(data)

        if isinstance(data, (int, float)):
            return str(data)

        if isinstance(data, str):
            if len(data) == 0:
                return '""'
            elif len(data) <= 100:
                return f'"{data}"'
            else:
                return f'"{data[:97]}..."'

        if isinstance(data, list):
            count = len(data)
            if count == 0:
                return "[]"
            elif count == 1:
                item_summary = ExecutionHistory._summarize_data_payload(data[0], max_chars=100)
                return f"[{item_summary}]"
            else:
                first_summary = ExecutionHistory._summarize_data_payload(data[0], max_chars=80)
                return f"[{count} items, first: {first_summary}]"

        if isinstance(data, dict):
            if not data:
                return "{}"

            # Build smart key-value summaries
            parts = []
            chars_used = 0

            for key, value in data.items():
                # Summarize the value intelligently
                if isinstance(value, list):
                    val_str = f"{len(value)} items" if value else "[]"
                elif isinstance(value, dict):
                    val_str = f"{len(value)} keys" if value else "{}"
                elif isinstance(value, str):
                    if len(value) == 0:
                        val_str = '""'
                    elif len(value) <= 50:
                        val_str = f'"{value}"'
                    else:
                        val_str = f'"{value[:47]}..."'
                elif isinstance(value, (int, float, bool)):
                    val_str = str(value)
                elif value is None:
                    val_str = "null"
                else:
                    val_str = f"{type(value).__name__}"

                part = f"{key}: {val_str}"
                if chars_used + len(part) + 2 > max_chars:
                    parts.append("...")
                    break

                parts.append(part)
                chars_used += len(part) + 2  # +2 for ", "

            return "{" + ", ".join(parts) + "}"

        return f"{type(data).__name__} object"

    def to_dict(self) -> List[Dict[str, Any]]:
        """Convert history to dict for serialization."""
        return [step.to_dict() for step in self._history]
