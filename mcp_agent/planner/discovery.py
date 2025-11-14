from __future__ import annotations

from typing import List, Dict

from mcp_agent.toolbox.search import search_tools
from mcp_agent.registry import registry_version

from .context import PlannerContext


def perform_initial_discovery(
    context: PlannerContext,
    *,
    limit: int = 40,
    detail_level: str = "summary",
) -> List[Dict[str, object]]:
    """
    Ensure the planner has up-to-date tool metadata for the task.
    Always routes through `search_tools(...)`, keeping discovery logic centralized.
    """
    current_version = registry_version(context.user_id)
    needs_refresh = (
        not context.discovery_completed
        or context.registry_version != current_version
    )
    if not needs_refresh:
        return context.search_results

    results = _run_search(
        context,
        query=context.task,
        detail_level=detail_level,
        limit=limit,
    )
    context.registry_version = current_version
    context.replace_search_results(results)
    return context.search_results


def perform_refined_discovery(
    context: PlannerContext,
    *,
    query: str,
    detail_level: str = "summary",
    limit: int = 10,
) -> List[Dict[str, object]]:
    """Run an on-demand discovery query requested by the planner."""
    results = _run_search(
        context,
        query=query,
        detail_level=detail_level,
        limit=limit,
    )
    if results:
        context.add_search_results(results)
    return results


def _run_search(
    context: PlannerContext,
    *,
    query: str,
    detail_level: str,
    limit: int,
) -> List[Dict[str, object]]:
    try:
        results = search_tools(
            query=query,
            detail_level=detail_level,
            limit=limit,
            user_id=context.user_id,
        )
        context.record_event(
            "mcp.search.run",
            {
                "query": query[:200],
                "detail_level": detail_level,
                "result_count": len(results),
            },
        )
        return results
    except Exception as exc:
        context.record_event(
            "mcp.search.error",
            {
                "query": query[:200],
                "detail_level": detail_level,
                "error": str(exc),
            },
        )
        return []
