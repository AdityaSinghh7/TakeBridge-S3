#!/usr/bin/env python3
"""
Inspect available tools for a user and compare them with search results for a query.

Example:
  python scripts/check_tool_search.py --user-id dev-local --query "gmail inbox"
  python scripts/check_tool_search.py --user-id dev-local --query "search slack messages" --provider slack
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List

from mcp_agent.knowledge.introspection import get_manifest
from mcp_agent.knowledge.search import search_tools
from mcp_agent.user_identity import normalize_user_id


def _collect_available_tools(user_id: str, provider: str | None) -> List[Dict[str, Any]]:
    """Return compact descriptors for all authorized+available tools for the user."""
    manifest = get_manifest(user_id=user_id, refresh=True)
    provider_filter = provider.lower() if provider else None
    tools: List[Dict[str, Any]] = []

    for prov in manifest.providers:
        if not prov.authorized:
            continue
        if provider_filter and prov.provider.lower() != provider_filter:
            continue
        for tool in prov.actions:
            if not tool.available:
                continue
            entry = tool.to_compact_descriptor().to_dict()
            entry["provider"] = prov.provider
            tools.append(entry)

    tools.sort(key=lambda t: t.get("tool_id", ""))
    return tools


def _run_search(query: str, user_id: str, provider: str | None, limit: int) -> List[Dict[str, Any]]:
    """Execute semantic tool search for the user/query."""
    return search_tools(
        query=query,
        provider=provider,
        detail_level="summary",
        limit=limit,
        user_id=user_id,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect tool availability and search results for a user/query.")
    parser.add_argument(
        "--user-id",
        default=os.getenv("TB_DEFAULT_USER_ID", "dev-local"),
        help="User id (defaults to TB_DEFAULT_USER_ID or 'dev-local').",
    )
    parser.add_argument("--query", required=True, help="Natural-language search query.")
    parser.add_argument("--provider", help="Optional provider filter (e.g., gmail).")
    parser.add_argument("--limit", type=int, default=20, help="Max search results to return (default: 20).")
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Print only the final JSON object (no human-readable summary).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        user_id = normalize_user_id(args.user_id)
    except Exception as exc:
        print(f"Invalid user id: {exc}", file=sys.stderr)
        return 1

    try:
        available_tools = _collect_available_tools(user_id, args.provider)
    except Exception as exc:
        print(f"Failed to load available tools: {exc}", file=sys.stderr)
        return 1

    try:
        search_results = _run_search(args.query, user_id, args.provider, args.limit)
    except Exception as exc:
        print(f"Search failed: {exc}", file=sys.stderr)
        return 1

    payload: Dict[str, Any] = {
        "user_id": user_id,
        "query": args.query,
        "provider_filter": args.provider,
        "available_tools": available_tools,
        "search_results": search_results,
    }

    if not args.json_only:
        provider_label = args.provider or "all authorized providers"
        print(f"User: {user_id}")
        print(f"Provider filter: {provider_label}")
        print(f"Available tools: {len(available_tools)}")
        print(f"Search results for '{args.query}': {len(search_results)}")
        print("-" * 60)

    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
