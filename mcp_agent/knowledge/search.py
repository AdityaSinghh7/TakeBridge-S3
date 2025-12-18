"""Tool search functionality - semantic search over available MCP tools.

Combines:
- Tool search (semantic matching against toolbox index)
- View generators (inventory and deep views for ReAct discovery)
- Provider listing
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional

import numpy as np

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext

from mcp_agent.user_identity import normalize_user_id
from mcp_agent.knowledge.introspection import get_index, get_manifest
from mcp_agent.knowledge.index import ToolboxIndex
from mcp_agent.knowledge.types import CompactToolDescriptor, LLMToolDescriptor, ProviderSpec, ToolSpec
from mcp_agent.knowledge.introspection import get_tool_spec, ensure_io_specs_loaded

logger = logging.getLogger(__name__)

DetailLevel = Literal["names", "summary", "full"]

# Minimum score thresholds for filtering results
MIN_SEMANTIC_SCORE_THRESHOLD = 0.25  # Minimum score to include in results when using semantic search (increased for better precision)
MIN_FALLBACK_SCORE_THRESHOLD = 0.3  # Higher threshold for fallback heuristic mode
ADAPTIVE_THRESHOLD_RATIO = 0.5  # Keep tools within 70% of top score when using adaptive threshold

# Provider families used for soft matching/boosting
PROVIDER_FAMILIES = {
    "google": {"google", "googledocs", "googlesheets", "googleslides", "googledrive", "gmail"},
    "gmail": {"gmail"},
    "slack": {"slack"},
    "github": {"github"},
    "microsoft": {"microsoft"},
    "composio": {"composio"},
}

# used for /api/mcp/auth/providers endpoint ONLY
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
    index: ToolboxIndex = get_index(user_id=normalized_user)
    norm_query = _normalize_query(query, index)
    provider_filter = provider.lower().strip() if provider else None

    # Get query embedding once
    query_embedding = norm_query.embedding

    # Check if we have embeddings available
    has_tool_embeddings = any(
        index.get_tool_embedding(t.tool_id) is not None
        for prov in index.providers.values()
        for t in prov.actions
    )

    # Log fallback usage for debugging
    if query and not has_tool_embeddings:
        logger.warning(
            f"Tool embeddings not available for user {normalized_user}. "
            "Using heuristic fallback scoring. Index may need refresh."
        )
    elif query and query_embedding is None:
        logger.warning(
            f"Query embedding failed for query '{query}'. Using heuristic fallback."
        )

    matches: List[tuple[float, ProviderSpec, ToolSpec]] = []

    for prov in index.providers.values():
        # Simplified: only check authorized (registered field removed as redundant)
        if not (prov.authorized and any(t.available for t in prov.actions)):
            continue
        if provider_filter and prov.provider.lower() != provider_filter:
            continue
        for tool in prov.actions:
            if not tool.available:
                continue

            # Get pre-computed tool embedding
            tool_embedding = index.get_tool_embedding(tool.tool_id)

            # Score using semantic similarity
            score = _score_tool_semantic(tool, norm_query, tool_embedding, query_embedding)

            # Debug logging for first few tools
            if query and len(matches) < 3:
                logger.debug(
                    f"Tool {tool.tool_id}: score={score:.3f}, "
                    f"has_embedding={tool_embedding is not None}, "
                    f"query_embedding={query_embedding is not None}"
                )

            # Skip tools with zero score only if we have a query
            if norm_query.terms and score <= 0.0:
                continue

            matches.append((score, prov, tool))

    # Filter out low scores using adaptive threshold
    # Use stricter threshold if using fallback (no embeddings)
    using_fallback = query_embedding is None or not has_tool_embeddings
    base_threshold = MIN_FALLBACK_SCORE_THRESHOLD if using_fallback else MIN_SEMANTIC_SCORE_THRESHOLD
    
    # Apply query-specific threshold adjustment
    threshold = _get_adaptive_threshold(query or "", base_threshold, using_fallback)
    
    # Apply adaptive threshold: keep top score and any within ratio of it
    matches = _apply_adaptive_threshold(matches, threshold)

    if query:
        logger.info(
            f"Search '{query}': {len(matches)} matches after threshold, "
            f"threshold={threshold:.3f}, using_fallback={using_fallback}, "
            f"has_tool_embeddings={has_tool_embeddings}, query_embedding={query_embedding is not None}"
        )
        if matches:
            logger.debug(
                f"Top scores: {[(t.tool_id, s) for s, _, t in matches[:5]]}"
            )
    
    # Sort by: exact name match first, then score
    matches.sort(key=lambda item: (
        not _has_exact_name_match(item[2], norm_query),  # False (0) for matches sorts first
        -item[0],  # Then by score descending
        item[1].provider,
        item[2].name
    ))
    
    if limit and limit > 0:
        matches = matches[:limit]

    results: List[Dict[str, Any]] = []
    for score, prov, tool in matches:
        # Use wrapper-provided output_schema only; do not enrich from IoToolSpec/JSON

        # Use compact descriptor - much smaller, optimized for LLM context
        descriptor: CompactToolDescriptor = tool.to_compact_descriptor()
        entry = descriptor.to_dict()

        # Add score for ranking (not part of the descriptor itself)
        entry["score"] = float(score)

        results.append(entry)

    return results


class _Query:
    def __init__(self, raw: str | None, embedding: Optional[np.ndarray] = None) -> None:
        text = (raw or "").strip().lower()
        self.raw = text
        self.terms = [term for term in re.split(r"[^a-z0-9_]+", text) if term]
        self.embedding = embedding


def _normalize_query(query: str | None, index: ToolboxIndex) -> _Query:
    """Normalize query and generate embedding if available.

    Args:
        query: Raw query string.
        index: ToolboxIndex to use for embedding cache.

    Returns:
        _Query object with normalized text and embedding.
    """
    text = (query or "").strip().lower()
    embedding = None

    if text:
        # Get or generate query embedding
        embedding = index.get_query_embedding(text)

    return _Query(raw=text, embedding=embedding)


def _provider_matches(query_lower: str, tool_provider: str) -> tuple[bool, bool]:
    """Determine whether the query mentions a provider family and if the tool matches it.

    Returns:
        (matches_family, family_mentioned)
    """
    mentioned_families = [fam for fam in PROVIDER_FAMILIES if fam in query_lower]
    if not mentioned_families:
        return True, False

    provider_norm = tool_provider.lower()
    for fam in mentioned_families:
        if provider_norm in PROVIDER_FAMILIES[fam]:
            return True, True
    return False, True


def _has_exact_name_match(tool: ToolSpec, query: _Query) -> bool:
    """Check if any query term exactly matches tool name.

    Args:
        tool: ToolSpec to check.
        query: _Query object with normalized terms.

    Returns:
        True if any query term appears in tool name.
    """
    if not query.terms:
        return False
    tool_name_lower = tool.name.lower()
    return any(term in tool_name_lower for term in query.terms)


def _get_adaptive_threshold(query: str, base_threshold: float, using_fallback: bool) -> float:
    """Adjust threshold based on query characteristics.

    Args:
        query: Query string.
        base_threshold: Base threshold value.
        using_fallback: Whether using fallback heuristic mode.

    Returns:
        Adjusted threshold value.
    """
    if using_fallback:
        return base_threshold

    # Short, specific queries (1-2 words) → higher threshold
    words = query.split()
    if len(words) <= 2:
        return max(base_threshold, 0.3)  # More selective for short queries

    # Longer queries → can be more lenient
    return base_threshold


def _apply_adaptive_threshold(
    matches: List[tuple[float, ProviderSpec, ToolSpec]], min_threshold: float
) -> List[tuple[float, ProviderSpec, ToolSpec]]:
    """Apply adaptive threshold: keep top score and any within ratio of it.

    Args:
        matches: List of (score, provider, tool) tuples.
        min_threshold: Minimum absolute threshold.

    Returns:
        Filtered matches list.
    """
    if not matches:
        return []

    matches_sorted = sorted(matches, key=lambda x: -x[0])
    top_score = matches_sorted[0][0]

    # Keep top result and any within ADAPTIVE_THRESHOLD_RATIO of top score
    # But never go below min_threshold
    threshold = max(min_threshold, top_score * ADAPTIVE_THRESHOLD_RATIO)
    return [m for m in matches_sorted if m[0] >= threshold]


def _score_tool_semantic(
    tool: ToolSpec,
    query: _Query,
    tool_embedding: Optional[np.ndarray],
    query_embedding: Optional[np.ndarray],
) -> float:
    """
    Score a tool against a query using semantic similarity.

    Uses cosine similarity between query and tool embeddings, with soft provider
    boosting instead of hard filtering.

    Args:
        tool: ToolSpec to score.
        query: _Query object with normalized text and terms.
        tool_embedding: Pre-computed embedding for the tool.
        query_embedding: Pre-computed embedding for the query.

    Returns:
        Semantic similarity score between 0.0 and 1.0 (after provider boost).
    """
    from .embeddings import get_embedding_service

    # If no query, return default score based on availability
    if not query.terms:
        return 0.5 if tool.available else 0.3

    # Fallback to heuristic scoring if embeddings unavailable
    if query_embedding is None or tool_embedding is None:
        return _score_tool_heuristic_fallback(tool, query)

    # Compute cosine similarity
    embedding_service = get_embedding_service()
    semantic_score = embedding_service.cosine_similarity(query_embedding, tool_embedding)

    # Apply exact term matching boost (strong signal for relevance)
    query_terms_lower = [t.lower() for t in query.terms]
    tool_name_lower = tool.name.lower()
    desc_lower = (tool.description or "").lower()

    # Boost for exact term matches in tool name (strongest signal)
    name_matches = sum(1 for term in query_terms_lower if term in tool_name_lower)
    if name_matches > 0:
        # Strong boost for name matches (0.2 per match, capped at 0.4)
        name_boost = min(0.2 * name_matches, 0.4)
        semantic_score += name_boost

    # Boost for exact term matches in description (weaker signal)
    desc_matches = sum(1 for term in query_terms_lower if term in desc_lower)
    if desc_matches > 0:
        # Smaller boost for description matches
        desc_boost = min(0.1 * desc_matches, 0.2)
        semantic_score += desc_boost

    # Apply provider boost/filter
    query_lower = query.raw.lower()
    tool_provider = tool.provider.lower()
    provider_matches, provider_mentioned = _provider_matches(query_lower, tool_provider)
    if provider_mentioned:
        if provider_matches:
            semantic_score *= 1.5  # strong boost when provider family is explicitly mentioned
        else:
            semantic_score *= 0.6  # soften mismatch instead of hard filtering

    # Small boost for available tools
    if tool.available:
        semantic_score *= 1.05

    # Clamp to [0, 1] range
    return float(np.clip(semantic_score, 0.0, 1.0))


def _score_tool_heuristic_fallback(tool: ToolSpec, query: _Query) -> float:
    """
    Fallback heuristic scoring when embeddings are unavailable.

    This maintains backward compatibility and handles error cases gracefully.

    Args:
        tool: ToolSpec to score.
        query: _Query object with normalized text and terms.

    Returns:
        Heuristic score normalized to [0, 1] range.
    """
    if not query.terms:
        return 0.5 if tool.available else 0.3

    # Provider alignment check (soft)
    query_lower = query.raw.lower()
    tool_provider = tool.provider.lower()
    provider_matches, provider_mentioned = _provider_matches(query_lower, tool_provider)

    if provider_mentioned:
        # Start higher when the provider family is explicitly mentioned
        score = 0.6 if provider_matches else 0.1
    else:
        score = 0.0

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
            score += 0.15
        if term in haystacks["provider"]:
            score += 0.1
        if term in haystacks["description"]:
            score += 0.08
        if term in haystacks["doc"]:
            score += 0.05
        if any(term in name for name in param_names):
            score += 0.05
        if term in haystacks["mcp_tool"]:
            score += 0.08

    if score > 0 and tool.available:
        score += 0.05

    # Normalize to [0, 1] range
    return float(np.clip(score, 0.0, 1.0))


# ============================================================================
# View generators for ReAct discovery flow
# ============================================================================


def get_inventory_view(
    context: AgentContext,
    tool_constraints: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generate inventory view: provider names + tool names only.

    This is the initial state shown to the LLM before discovery.
    Ultra-slim to minimize tokens.

    Args:
        context: Agent context with user_id
        tool_constraints: Optional dict with:
            - mode: "auto" | "custom"
            - providers: List[str] (for custom mode)
            - tools: List[str] (for custom mode)

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

        # Apply tool constraints filtering
        if tool_constraints:
            mode = tool_constraints.get("mode", "auto")
            if mode == "custom":
                allowed_providers = tool_constraints.get("providers", [])
                # If providers list is specified and provider not in it, skip
                if allowed_providers and provider_info["provider"] not in allowed_providers:
                    continue

        funcs = action_map.get(provider_info["provider"], ())
        tool_names = [f.__name__ for f in funcs]

        # Apply tool-level filtering if in custom mode
        if tool_constraints and tool_constraints.get("mode") == "custom":
            allowed_tools = tool_constraints.get("tools", [])
            if allowed_tools:
                # Filter to only allowed tools
                tool_names = [name for name in tool_names if name in allowed_tools]

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
