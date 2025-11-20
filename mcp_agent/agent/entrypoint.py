"""Main entry point for MCP task execution.

Provides a clean API for executing MCP tasks with proper context management.
"""

from __future__ import annotations

from typing import Any, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext

from mcp_agent.core.context import AgentContext


def execute_task(
    task: str,
    user_id: str,
    *,
    budget: Any | None = None,
    extra_context: Dict[str, Any] | None = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Execute an MCP task for a user.
    
    This is the main public API for the MCP agent. It initializes the context,
    loads available tools, and runs the ReAct planning loop to complete the task.
    
    Args:
        task: The task description (natural language)
        user_id: The user/tenant identifier
        budget: Optional budget constraints (max steps, cost, etc.)
        extra_context: Additional context to pass to the planner
        **kwargs: Additional arguments passed to the underlying planner
    
    Returns:
        Dict containing:
            - success: bool - whether the task completed successfully
            - final_summary: str - summary of task execution
            - user_id: str - the user who ran the task
            - run_id: str - unique identifier for this run
            - raw_outputs: dict - raw outputs from tool calls
            - budget_usage: dict - resource usage statistics
            - logs: list - execution logs
            - steps: list - execution steps
            - error: str | None - error message if failed
    
    Example:
        >>> result = execute_task(
        ...     "Send an email to john@example.com",
        ...     user_id="dev-local"
        ... )
        >>> print(result["success"])
        True
    """
    # Create AgentContext
    context = AgentContext.create(user_id=user_id)
    
    # Use the migrated planner in agent/
    from mcp_agent.agent.planner import execute_mcp_task
    
    return execute_mcp_task(
        task=task,
        user_id=user_id,
        budget=budget,
        extra_context=extra_context or {},
        **kwargs
    )

