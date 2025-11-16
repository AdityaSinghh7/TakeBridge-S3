"""
Standalone MCP planner entrypoint.

This module surfaces the single public API described in Standalone_MCP_Plan.md:

    execute_mcp_task(
        task: str,
        *,
        user_id: str,
        budget: Budget | None = None,
        extra_context: dict | None = None,
    ) -> MCPTaskResult

The planner operates independently of the GUI/desktop automation agent. Callers
must supply a task string plus the caller's stable `user_id`, along with optional
budget overrides. ``MCPTaskResult`` contains success state, summary text, budget
usage, raw outputs (when available), logs, and an optional error message.
"""

from .budget import Budget, BudgetSnapshot
from .runtime import MCPTaskResult, execute_mcp_task

__all__ = [
    "Budget",
    "BudgetSnapshot",
    "MCPTaskResult",
    "execute_mcp_task",
]
