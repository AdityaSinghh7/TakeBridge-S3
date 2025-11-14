"""
Standalone MCP planner entrypoint.

This module surfaces the single public API described in Standalone_MCP_Plan.md:

    execute_mcp_task(
        task: str,
        user_id: str = "singleton",
        budget: Budget | None = None,
        extra_context: dict | None = None,
    ) -> MCPTaskResult

The planner operates independently of the GUI/desktop automation agent. Callers
provide a task string plus optional budget overrides and receive a structured
``MCPTaskResult`` containing success state, summary text, budget usage, raw
outputs (when available), logs, and an optional error message.
"""

from .budget import Budget, BudgetSnapshot
from .runtime import MCPTaskResult, execute_mcp_task

__all__ = [
    "Budget",
    "BudgetSnapshot",
    "MCPTaskResult",
    "execute_mcp_task",
]
