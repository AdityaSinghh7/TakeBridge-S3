"""Tool search functionality - semantic search over available MCP tools.

Combines:
- Tool search (semantic matching against toolbox index)
- View generators (inventory and deep views for ReAct discovery)
- Provider listing
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Dict, List, Literal

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext

from mcp_agent.user_identity import normalize_user_id
from mcp_agent.knowledge.introspection import get_index, get_manifest
from mcp_agent.knowledge.index import ToolboxIndex
from mcp_agent.knowledge.types import CompactToolDescriptor, LLMToolDescriptor, ProviderSpec, ToolSpec
from mcp_agent.knowledge.introspection import get_tool_spec, ensure_io_specs_loaded

DetailLevel = Literal["names", "summary", "full"]


def list_providers(user_id: str) -> List[Dict[str, Any]]:
    """List all configured providers for a user."""
    normalized = normalize_user_id(user_id)
    manifest = get_manifest(user_id=normalized)
    providers = []
    for provider in manifest.providers:
        entry = provider.summary()
        entry["path"] = f"providers/{provider.provider}/provider.json"
        providers.append(entry)
    return providers


def search_tools(
    query: str | None = None,
    *,
    provider: str | None = None,
    detail_level: DetailLevel = "summary",
    limit: int = 20,
    user_id: str,
) -> List[Dict[str, Any]]:
    """
    Search the toolbox index for tools matching a natural-language query.

    Args:
        query: Optional free-text query; when empty, returns high-signal tools.
        provider: Optional provider filter (e.g. "gmail").
        detail_level: Label for logging only; descriptor shape is unchanged.
        limit: Maximum number of tools to return.
        user_id: Current user id used to scope the toolbox index.

    Returns:
        A list of dicts produced by CompactToolDescriptor.to_dict().
        These are ultra-compact representations containing only essential
        information for sandbox code generation and tool invocation.
    """
    # Ensure IoToolSpecs are registered for schema enrichment
    ensure_io_specs_loaded()
    normalized_user = normalize_user_id(user_id)
    norm_query = _normalize_query(query)
    provider_filter = provider.lower().strip() if provider else None
    index: ToolboxIndex = get_index(user_id=normalized_user)
    matches: List[tuple[int, ProviderSpec, ToolSpec]] = []

    for prov in index.providers.values():
        if not (prov.authorized and prov.registered and any(t.available for t in prov.actions)):
            continue
        if provider_filter and prov.provider.lower() != provider_filter:
            continue
        for tool in prov.actions:
            if not tool.available:
                continue
            score = _score_tool(tool, norm_query)
            if norm_query.terms and score == 0:
                continue
            matches.append((score, prov, tool))

    matches = [entry for entry in matches if entry[0] > 0]
    matches.sort(key=lambda item: (-item[0], item[1].provider, item[2].name))
    if limit and limit > 0:
        matches = matches[:limit]

    results: List[Dict[str, Any]] = []
    for score, prov, tool in matches:
        # Enrich with IoToolSpec output schema if available
        # This populates output_fields with structured field paths
        io_spec = get_tool_spec(prov.provider, tool.name)
        if io_spec is not None and io_spec.output_spec.data_schema_success:
            # Update tool's output_schema before conversion to compact descriptor
            tool.output_schema = io_spec.output_spec.data_schema_success

        # Use compact descriptor - much smaller, optimized for LLM context
        descriptor: CompactToolDescriptor = tool.to_compact_descriptor()
        entry = descriptor.to_dict()

        # Add score for ranking (not part of the descriptor itself)
        entry["score"] = float(score)

        results.append(entry)

    return results


class _Query:
    def __init__(self, raw: str | None) -> None:
        text = (raw or "").strip().lower()
        self.raw = text
        self.terms = [term for term in re.split(r"[^a-z0-9_]+", text) if term]


def _normalize_query(query: str | None) -> _Query:
    return _Query(query)


def _score_tool(tool: ToolSpec, query: _Query) -> int:
    """
    Score a tool against a query for relevance.

    Prevents cross-provider contamination by hard-filtering when query explicitly
    mentions a provider (e.g., "gmail search" won't return Slack tools).
    """
    if not query.terms:
        return 2 if tool.available else 1

    # Provider alignment check - prevent cross-provider contamination
    known_providers = ["gmail", "slack", "github", "google", "microsoft", "composio"]
    query_lower = query.raw.lower()

    # Check if query mentions any specific provider
    mentioned_providers = [p for p in known_providers if p in query_lower]

    if mentioned_providers:
        # Query explicitly mentions a provider
        tool_provider = tool.provider.lower()
        if tool_provider not in mentioned_providers:
            # Hard filter - query asks for "gmail" but this is a "slack" tool
            return 0
        # Provider match - boost the score significantly
        score = 10
    else:
        # No specific provider mentioned - start with neutral score
        score = 0

    haystacks = {
        "name": tool.name.lower(),
        "provider": tool.provider.lower(),
        "description": (tool.description or "").lower(),
        "doc": (tool.docstring or "").lower(),
        "mcp_tool": (tool.mcp_tool_name or "").lower(),
    }
    param_names = [param.name.lower() for param in tool.parameters]
    for term in query.terms:
        if term in haystacks["name"]:
            score += 5
        if term in haystacks["provider"]:
            score += 3
        if term in haystacks["description"]:
            score += 2
        if term in haystacks["doc"]:
            score += 1
        if any(term in name for name in param_names):
            score += 1
        if term in haystacks["mcp_tool"]:
            score += 2
    if score > 0 and tool.available:
        score += 1
    return score


# ============================================================================
# View generators for ReAct discovery flow
# ============================================================================


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
    from mcp_agent.registry import get_available_providers
    from mcp_agent.actions import get_provider_action_map

    action_map = get_provider_action_map()

    providers = []
    for provider_info in get_available_providers(context):
        if not provider_info.get("authorized"):
            continue

        funcs = action_map.get(provider_info["provider"], ())
        tool_names = [f.__name__ for f in funcs]

        providers.append({
            "provider": provider_info["provider"],
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
        results = search_tools(
            query=None,
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
