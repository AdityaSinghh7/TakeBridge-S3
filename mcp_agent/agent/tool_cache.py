"""Tool discovery cache management.

Manages the cache of discovered tools during agent execution, including:
- Merging search results with deduplication
- Tool lookup and resolution
- Context window trimming for LLM consumption
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from mcp_agent.knowledge.introspection import get_index


class ToolCache:
    """Manages discovered tool cache with deduplication and trimming.

    Responsibilities:
    - Store discovered tools (search results)
    - Merge new discoveries, keeping highest scores
    - Provide tool lookup by key
    - Trim cache to prevent context overflow
    - Resolve MCP tool names

    NOT responsible for:
    - Actually discovering tools (see executor.py)
    - Executing tools (see executor.py)
    - Formatting prompts (see prompts.py)
    """

    def __init__(self, max_cached_tools: int = 50) -> None:
        """Initialize empty tool cache.

        Args:
            max_cached_tools: Maximum number of tools to keep in cache
        """
        self._search_results: List[Dict[str, Any]] = []
        self._search_index: Dict[str, Dict[str, Any]] = {}
        self._discovery_completed: bool = False
        self._max_cached_tools = max_cached_tools

    @property
    def search_results(self) -> List[Dict[str, Any]]:
        """Get read-only view of search results."""
        return self._search_results

    @property
    def discovery_completed(self) -> bool:
        """Check if discovery has been completed."""
        return self._discovery_completed

    def merge_search_results(
        self, results: List[Dict[str, Any]], *, replace: bool = False
    ) -> None:
        """Merge new search results, keeping highest scores per tool.

        Args:
            results: New search results to merge
            replace: If True, clear existing results before merging
        """
        if replace:
            self._search_results.clear()
            self._search_index.clear()

        for entry in results:
            key = self._search_key(entry)
            if not key:
                continue

            existing = self._search_index.get(key)
            if existing:
                # Update if new score is higher
                if self._score(entry) > self._score(existing):
                    idx = self._find_search_index(key)
                    if idx is not None:
                        self._search_results[idx] = entry
                        self._search_index[key] = entry
                continue

            # New entry
            self._search_results.append(entry)
            self._search_index[key] = entry

        # Trim to prevent context overflow
        self._trim_context_for_llm()

        # Mark discovery as completed if we have any results
        if self._search_results:
            self._discovery_completed = True

    def get_tool(self, tool_id: str) -> Optional[Dict[str, Any]]:
        """Lookup a tool by ID.

        Args:
            tool_id: Tool identifier (e.g., "gmail.gmail_send_email")

        Returns:
            Tool dict if found, None otherwise
        """
        return self._search_index.get(tool_id)

    def resolve_mcp_tool_name(
        self, user_id: str, provider: str, tool_name: str
    ) -> str:
        """Resolve provider/tool pair to the underlying MCP tool name.

        Args:
            user_id: User ID for context
            provider: Provider name (e.g., "gmail")
            tool_name: Tool name (e.g., "gmail_send_email")

        Returns:
            MCP tool name if found, otherwise returns tool_name as-is
        """
        provider_key = (provider or "").strip().lower()
        tool_key = (tool_name or "").strip()
        if not provider_key or not tool_key:
            return tool_name

        tool_id = f"{provider_key}.{tool_key}"

        # Try to get from knowledge index
        try:
            index = get_index(user_id)
        except Exception:
            return tool_name

        spec = index.get_tool(tool_id)
        if spec and spec.mcp_tool_name:
            return spec.mcp_tool_name

        return tool_name

    def _trim_context_for_llm(self) -> None:
        """Keep only the most recent search results to enforce deterministic caps."""
        if len(self._search_results) > self._max_cached_tools:
            self._search_results[:] = self._search_results[-self._max_cached_tools :]

            # Rebuild search index after trimming
            new_index: Dict[str, Dict[str, Any]] = {}
            for entry in self._search_results:
                key = self._search_key(entry)
                if key:
                    new_index[key] = entry
            self._search_index = new_index

    def _search_key(self, entry: Dict[str, Any]) -> Optional[str]:
        """Extract unique key for deduplication (supports both legacy and compact formats)."""
        # Prefer tool_id (compact format)
        tool_id = entry.get("tool_id")
        if tool_id:
            return tool_id

        # Fall back to qualified_name (legacy format)
        qualified_name = entry.get("qualified_name")
        if qualified_name:
            return qualified_name

        # Last resort: construct from provider.tool (legacy format)
        provider = (entry.get("provider") or "").strip().lower()
        tool = (entry.get("tool") or "").strip().lower()
        if provider and tool:
            return f"{provider}.{tool}"

        return None

    def _find_search_index(self, key: str) -> Optional[int]:
        """Find the index of a tool in search_results by key."""
        for idx, entry in enumerate(self._search_results):
            if self._search_key(entry) == key:
                return idx
        return None

    def _score(self, entry: Dict[str, Any]) -> float:
        """Extract score from entry for comparison."""
        value = entry.get("score")
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert cache to dict for serialization."""
        return {
            "search_results": self._search_results,
            "discovery_completed": self._discovery_completed,
        }
