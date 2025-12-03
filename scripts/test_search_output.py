#!/usr/bin/env python3
"""
Smoke-test for search output fields.

Run:
  python scripts/test_search_output.py --query "gmail inbox"
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from mcp_agent.knowledge.search import search_tools
from mcp_agent.knowledge.introspection import get_manifest
from mcp_agent.knowledge.utils import flatten_schema_fields
from mcp_agent.user_identity import normalize_user_id


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect search tool output fields.")
    parser.add_argument("--query", required=True, help="Search query text")
    parser.add_argument("--provider", help="Optional provider filter (e.g., gmail)")
    parser.add_argument(
        "--user-id",
        help="User id (defaults to TB_DEFAULT_USER_ID or 'dev-local')",
        default=os.getenv("TB_DEFAULT_USER_ID", "dev-local"),
    )
    args = parser.parse_args()

    try:
        user_id = normalize_user_id(args.user_id)
    except Exception as exc:
        print(f"Invalid user_id: {exc}", file=sys.stderr)
        return 1

    results = search_tools(
        query=args.query,
        provider=args.provider,
        detail_level="summary",
        limit=10,
        user_id=user_id,
    )

    # Load manifest and IO specs to compare wrapper vs IoToolSpec schemas
    manifest = get_manifest(user_id=user_id, refresh=True)
    provider_map = {p.provider: p for p in manifest.providers}

    print(f"Found {len(results)} tools for query '{args.query}' (user_id={user_id})")
    for idx, tool in enumerate(results, start=1):
        tool_id = tool.get("tool_id")
        provider, _, tool_name = tool_id.partition(".") if tool_id else ("", "", "")
        wrapper_fields: list[str] = []

        # Wrapper schema -> flatten
        prov_spec = provider_map.get(provider)
        if prov_spec:
            match = next((t for t in prov_spec.actions if t.name == tool_name), None)
            if match and match.output_schema:
                wrapper_fields = flatten_schema_fields(match.output_schema, max_depth=3, max_fields=30)

        output_fields = tool.get("output_fields") or []
        print(f"{idx}. {tool_id}")
        print(f"   output_fields ({len(output_fields)}):")
        if output_fields:
            for field in output_fields:
                print(f"     - {field}")
        else:
            print("     (none)")
        print(f"   wrapper_fields ({len(wrapper_fields)}):")
        for field in wrapper_fields[:30]:
            print(f"     - {field}")
        if not wrapper_fields:
            print("     (none)")
        print(f"   signature: {tool.get('signature')}")
        print(f"   score: {tool.get('score')}")
        print()

    print("Raw JSON:")
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
