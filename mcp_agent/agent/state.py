"""Agent state management - pure data container for planning session.

This module provides AgentState, a focused state container that holds the
"memory" of the agent during execution. It handles:
- Execution history (thoughts, actions, observations)
- Tool discovery cache (inventory + deep views)
- Budget tracking
- Context window management

Separated from PlannerContext to enforce clear boundaries between:
- State (what we remember)
- Logic (how we process)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

from shared.token_cost_tracker import TokenCostTracker

from .budget import Budget, BudgetTracker

StepType = Literal["tool", "sandbox", "search", "finish", "fail"]


@dataclass
class AgentStep:
    """Single step in agent execution history."""

    index: int
    type: StepType
    command: Dict[str, Any]
    success: bool
    preview: str
    result_key: Optional[str] = None
    error: Optional[str] = None
    output: Any = None
    is_summary: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "index": self.index,
            "type": self.type,
            "command": self.command,
            "success": self.success,
            "preview": self.preview,
            "result_key": self.result_key,
            "error": self.error,
            "output": self.output,
            "is_summary": self.is_summary,
        }


@dataclass
class AgentState:
    """Planning session state - the 'memory' of the agent.

    This is a pure data container focused on what the agent remembers:
    - What has been done (history)
    - What tools are available (inventory)
    - What tools have been discovered (discovered_tools)
    - How much budget remains (budget_tracker)

    Responsibilities:
    - Store execution history
    - Cache discovered tool details
    - Track budget consumption
    - Manage context window (trim old steps when needed)

    NOT responsible for:
    - Executing actions (see executor.py)
    - Making decisions (see orchestrator.py)
    - Formatting prompts (see prompts.py)
    """

    # Core identity
    task: str
    user_id: str
    request_id: str

    # Budget constraints
    budget: Budget
    budget_tracker: BudgetTracker = field(init=False)
    token_tracker: TokenCostTracker = field(default_factory=TokenCostTracker)

    # Discovery state
    inventory: Dict[str, Any] = field(default_factory=dict)  # {"providers": [...]}
    discovered_tools: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # tool_id -> deep_view

    # Execution history
    history: List[AgentStep] = field(default_factory=list)

    # Raw outputs from tools/sandbox (for detailed inspection)
    raw_outputs: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)

    # Terminal state
    finished: bool = False
    failed: bool = False
    failure_reason: Optional[str] = None
    final_result: Any = None

    def __post_init__(self):
        """Initialize derived fields."""
        self.budget_tracker = BudgetTracker(self.budget)

    # --- History management ---

    def add_step(
        self,
        *,
        type: StepType,
        command: Dict[str, Any],
        success: bool,
        preview: str,
        result_key: Optional[str] = None,
        error: Optional[str] = None,
        output: Any = None,
        is_summary: bool = False,
    ) -> AgentStep:
        """Add a step to execution history."""
        step = AgentStep(
            index=len(self.history),
            type=type,
            command=command,
            success=success,
            preview=preview[:200],  # Truncate long previews
            result_key=result_key,
            error=error,
            output=output,
            is_summary=is_summary,
        )
        self.history.append(step)
        return step

    def get_context_window(self, max_steps: Optional[int] = None) -> List[AgentStep]:
        """Get recent history within limits.

        Args:
            max_steps: Maximum number of steps to return (None = all)

        Returns:
            List of recent steps (oldest first)
        """
        if max_steps is None or max_steps <= 0:
            return self.history
        return self.history[-max_steps:]

    # --- Tool discovery cache ---

    def cache_tool_deep_view(self, tool_id: str, view: Dict[str, Any]) -> None:
        """Cache detailed tool specification after discovery."""
        self.discovered_tools[tool_id] = view

    def get_tool_deep_view(self, tool_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached tool specification."""
        return self.discovered_tools.get(tool_id)

    def has_discovered_tool(self, tool_id: str) -> bool:
        """Check if tool has been discovered."""
        return tool_id in self.discovered_tools

    # --- Raw output storage ---

    def append_raw_output(self, key: str, entry: Dict[str, Any]) -> None:
        """Append raw output entry for detailed inspection."""
        if key not in self.raw_outputs:
            self.raw_outputs[key] = []
        self.raw_outputs[key].append(entry)

    def get_raw_outputs(self, key: str) -> List[Dict[str, Any]]:
        """Retrieve raw outputs by key."""
        return self.raw_outputs.get(key, [])

    # --- Terminal state management ---

    def is_terminal(self) -> bool:
        """Check if agent has reached terminal state."""
        return self.finished or self.failed

    def mark_finished(self, result: Any) -> None:
        """Mark execution as successfully finished."""
        self.finished = True
        self.final_result = result

    def mark_failed(self, reason: str) -> None:
        """Mark execution as failed."""
        self.failed = True
        self.failure_reason = reason

    # --- Budget checks ---

    def is_budget_exhausted(self) -> bool:
        """Check if any budget limit has been exceeded."""
        snapshot = self.budget_tracker.snapshot()
        return (
            snapshot.steps_taken >= snapshot.max_steps
            or snapshot.tool_calls >= snapshot.max_tool_calls
            or snapshot.code_runs >= snapshot.max_code_runs
            or snapshot.estimated_llm_cost_usd >= snapshot.max_llm_cost_usd
        )

    def get_budget_snapshot(self) -> Dict[str, Any]:
        """Get current budget state as dict."""
        snapshot = self.budget_tracker.snapshot()
        return {
            "steps_taken": snapshot.steps_taken,
            "tool_calls": snapshot.tool_calls,
            "code_runs": snapshot.code_runs,
            "estimated_llm_cost_usd": snapshot.estimated_llm_cost_usd,
            "max_steps": snapshot.max_steps,
            "max_tool_calls": snapshot.max_tool_calls,
            "max_code_runs": snapshot.max_code_runs,
            "max_llm_cost_usd": snapshot.max_llm_cost_usd,
        }

    # --- Serialization ---

    def to_dict(self) -> Dict[str, Any]:
        """Convert state to dict for serialization."""
        return {
            "task": self.task,
            "user_id": self.user_id,
            "request_id": self.request_id,
            "budget": self.get_budget_snapshot(),
            "inventory": self.inventory,
            "discovered_tools": self.discovered_tools,
            "history": [step.to_dict() for step in self.history],
            "raw_outputs": self.raw_outputs,
            "finished": self.finished,
            "failed": self.failed,
            "failure_reason": self.failure_reason,
            "final_result": self.final_result,
        }
