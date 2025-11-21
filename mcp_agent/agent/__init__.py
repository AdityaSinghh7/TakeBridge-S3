"""Agent layer - ReAct planning loop and task execution."""

from .run_loop import execute_mcp_task, AgentOrchestrator, PlannerRuntime
from .types import MCPTaskResult
from .budget import Budget, BudgetTracker, BudgetSnapshot
from .llm import PlannerLLM
from .state import AgentState
from .history import AgentStep, StepType, ExecutionHistory
from .tool_cache import ToolCache
from .summary_manager import SummaryManager
from .executor import ActionExecutor

__all__ = [
    # Main entrypoint
    "execute_mcp_task",
    # Legacy aliases (backward compatibility)
    "AgentOrchestrator",
    "PlannerRuntime",
    "MCPTaskResult",
    # New architecture
    "AgentState",
    "AgentStep",
    "StepType",
    "ExecutionHistory",
    "ToolCache",
    "SummaryManager",
    "ActionExecutor",
    # Supporting types
    "Budget",
    "BudgetTracker",
    "BudgetSnapshot",
    "PlannerLLM",
]
