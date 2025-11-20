"""Agent layer - ReAct planning loop and task execution."""

from .entrypoint import execute_task
from .planner import execute_mcp_task, PlannerRuntime, MCPTaskResult
from .context import PlannerContext
from .budget import Budget, BudgetTracker, BudgetSnapshot
from .llm import PlannerLLM
from .state import AgentState, AgentStep
from .executor import ActionExecutor, execute_action

__all__ = [
    # Main entrypoints
    "execute_task",
    "execute_mcp_task",
    # Legacy planner (backward compatibility)
    "PlannerRuntime",
    "MCPTaskResult",
    "PlannerContext",
    # New architecture
    "AgentState",
    "AgentStep",
    "ActionExecutor",
    "execute_action",
    # Supporting types
    "Budget",
    "BudgetTracker",
    "BudgetSnapshot",
    "PlannerLLM",
]
