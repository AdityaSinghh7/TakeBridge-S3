"""Budget tracking for MCP agent task execution."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict


@dataclass
class Budget:
    """Hard limits for planner runs."""

    max_steps: int = 10
    max_tool_calls: int = 30
    max_code_runs: int = 5  # Increased from 3 to allow more iterations
    max_llm_cost_usd: float = 0.50


@dataclass
class BudgetSnapshot:
    """Read-only capture of current usage."""

    steps_taken: int = 0
    tool_calls: int = 0
    code_runs: int = 0
    estimated_llm_cost_usd: float = 0.0
    max_steps: int = Budget().max_steps
    max_tool_calls: int = Budget().max_tool_calls
    max_code_runs: int = Budget().max_code_runs
    max_llm_cost_usd: float = Budget().max_llm_cost_usd
    exhausted: Dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, float | int | Dict[str, bool]]:
        return asdict(self)


class BudgetTracker:
    """Mutable tracker used internally by the planner runtime."""

    def __init__(self, budget: Budget) -> None:
        self.budget = budget
        self.steps_taken = 0
        self.tool_calls = 0
        self.code_runs = 0
        self.estimated_llm_cost_usd = 0.0

    def snapshot(self) -> BudgetSnapshot:
        exhausted = {
            "max_steps": self.steps_taken >= self.budget.max_steps,
            "max_tool_calls": self.tool_calls >= self.budget.max_tool_calls,
            "max_code_runs": self.code_runs >= self.budget.max_code_runs,
            "max_llm_cost_usd": self.estimated_llm_cost_usd >= self.budget.max_llm_cost_usd,
        }
        return BudgetSnapshot(
            steps_taken=self.steps_taken,
            tool_calls=self.tool_calls,
            code_runs=self.code_runs,
            estimated_llm_cost_usd=self.estimated_llm_cost_usd,
            max_steps=self.budget.max_steps,
            max_tool_calls=self.budget.max_tool_calls,
            max_code_runs=self.budget.max_code_runs,
            max_llm_cost_usd=self.budget.max_llm_cost_usd,
            exhausted=exhausted,
        )

    def reset_llm_cost(self) -> None:
        self.estimated_llm_cost_usd = 0.0

    def update_llm_cost(self, total_cost: float) -> None:
        self.estimated_llm_cost_usd = total_cost

