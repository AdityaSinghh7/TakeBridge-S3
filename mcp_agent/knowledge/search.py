"""Tool search functionality - semantic search over available MCP tools.

Migrated from toolbox/search.py with context-awareness.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Literal

from mcp_agent.user_identity import normalize_user_id
from mcp_agent.knowledge.builder import get_index, get_manifest
from mcp_agent.knowledge.index import ToolboxIndex
from mcp_agent.knowledge.models import CompactToolDescriptor, LLMToolDescriptor, ProviderSpec, ToolSpec
from mcp_agent.knowledge.registry import get_tool_spec
from mcp_agent.knowledge.load_io_specs import ensure_io_specs_loaded

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
