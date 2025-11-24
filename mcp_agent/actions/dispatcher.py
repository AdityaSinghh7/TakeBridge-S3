"""Central dispatcher for MCP tool calls.

Routes (provider, tool) pairs to the appropriate wrapper function.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

from mcp_agent.core.exceptions import ToolNotFoundError
from mcp_agent.types import ToolInvocationResult
from .provider_loader import discover_providers, load_action_map

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext


def get_provider_action_map():
    """Get mapping of provider -> action functions."""
    providers = discover_providers()
    return load_action_map(providers)


def dispatch_tool(
    context: AgentContext,
    provider: str,
    tool: str,
    payload: Dict[str, Any],
) -> ToolInvocationResult:
    """
    Dispatch a tool call to the appropriate wrapper function.
    
    Args:
        context: Agent context with user_id and db_session
        provider: Provider name ("gmail", "slack")
        tool: Tool name ("gmail_send_email", etc.)
        payload: Tool arguments as dict
    
    Returns:
        Standardized ToolInvocationResult
    
    Raises:
        ToolNotFoundError: If provider/tool combination not found
    """
    # Get provider action map
    action_map = get_provider_action_map()
    
    # Find provider
    if provider not in action_map:
        raise ToolNotFoundError(
            provider,
            tool,
            details={"available_providers": list(action_map.keys())},
        )
    
    # Find tool function
    funcs = action_map[provider]
    wrapper_func = None
    for func in funcs:
        if func.__name__ == tool:
            wrapper_func = func
            break
    
    if wrapper_func is None:
        available_tools = [f.__name__ for f in funcs]
        raise ToolNotFoundError(
            provider,
            tool,
            details={"available_tools": available_tools},
        )
    
    # Call wrapper with context and payload
    return wrapper_func(context, **payload)
