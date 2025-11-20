"""View generators for ReAct discovery flow.

Implements two views:
1. Inventory View: Slim provider tree (provider + tool names only)
2. Deep View: Detailed tool specs for discovered tools
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext


def get_inventory_view(context: AgentContext) -> Dict[str, Any]:
    """
    Generate inventory view: provider names + tool names only.
    
    This is the initial state shown to the LLM before discovery.
    Ultra-slim to minimize tokens.
    
    Args:
        context: Agent context with user_id
    
    Returns:
        Dict with providers list:
        {
            "providers": [
                {"provider": "gmail", "tools": ["gmail_send_email", "gmail_search"]},
                {"provider": "slack", "tools": ["slack_post_message", "slack_search_messages"]}
            ]
        }
    """
    from mcp_agent.registry.manager import RegistryManager
    from mcp_agent.actions import get_provider_action_map
    
    registry = RegistryManager(context)
    action_map = get_provider_action_map()
    
    providers = []
    for provider_info in registry.get_available_providers():
        if not provider_info.authorized:
            continue  # Skip unauthorized providers
        
        # Get tool names for this provider
        funcs = action_map.get(provider_info.provider, ())
        tool_names = [f.__name__ for f in funcs]
        
        providers.append({
            "provider": provider_info.provider,
            "tools": tool_names,
        })
    
    return {"providers": providers}


def get_deep_view(context: AgentContext, tool_ids: List[str]) -> List[Dict[str, Any]]:
    """
    Generate deep view: detailed specs for specific tools.
    
    This is returned after search to provide full tool documentation.
    Aggressively debloated - only essential fields.
    
    Args:
        context: Agent context with user_id
        tool_ids: List of tool IDs (e.g., ["gmail.gmail_search", "slack.slack_post_message"])
    
    Returns:
        List of tool specs (debloated):
        [
            {
                "tool_id": "gmail.gmail_search",
                "description": "...",
                "input_params": {"required": [...], "optional": [...]},
                "output_fields": ["messages[].messageId", "messages[].subject", ...],
                "call_signature": "gmail.gmail_search(query, max_results)"
            }
        ]
        
    REMOVED from output (compared to old search results):
        - raw docstrings
        - source paths/line numbers
        - py_module/py_name (internal implementation details)
        - verbose output_schema (replaced with flat output_fields)
        - availability_reason, score, etc.
    """
    from mcp_agent.toolbox.search import search_tools
    from mcp_agent.user_identity import normalize_user_id
    
    user_id = normalize_user_id(context.user_id)
    
    # Parse tool_ids to extract providers
    providers_needed = set()
    for tool_id in tool_ids:
        if "." in tool_id:
            provider, _ = tool_id.split(".", 1)
            providers_needed.add(provider)
    
    # Search for each provider separately to get matching tools
    all_tools = []
    for provider in providers_needed:
        # Get all tools for this provider
        results = search_tools(
            query=None,  # Empty query returns all tools
            provider=provider,
            detail_level="full",
            limit=100,
            user_id=user_id,
        )
        all_tools.extend(results)
    
    # Filter to requested tool_ids
    filtered_tools = []
    for tool in all_tools:
        tool_id = tool.get("tool_id") or f"{tool.get('provider')}.{tool.get('tool')}"
        if tool_id in tool_ids:
            filtered_tools.append(tool)
    
    # Debloat: keep only essential fields
    debloated = []
    for tool in filtered_tools:
        slim = {
            "tool_id": tool.get("tool_id"),
            "description": tool.get("description", ""),
            "input_params": tool.get("input_params", {}),
            "output_fields": tool.get("output_fields", []),
            "call_signature": tool.get("call_signature", tool.get("tool_id", "")),
        }
        debloated.append(slim)
    
    return debloated

