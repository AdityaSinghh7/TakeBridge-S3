#!/usr/bin/env python3
"""
Smoke-test for the tool output schema summarizer + inspector traversal.

This script is designed to run without needing live MCP network access:
- It loads the wrapper's `__tb_output_schema__` directly from the Python module.
- It runs `summarize_schema_for_llm(...)` to verify fold markers appear for large schemas.
- It can also drill down into a schema path using the same traversal logic as
  `toolbox.inspect_tool_output`.

Examples:
  python scripts/test_inspect_tool_output.py --tool-id shopify.shopify_get_orders_with_filters
  python scripts/test_inspect_tool_output.py --tool-id shopify.shopify_get_orders_with_filters --field-path orders[]
  python scripts/test_inspect_tool_output.py --tool-id gmail.gmail_search --field-path messages[]
  python scripts/test_inspect_tool_output.py --tool-id shopify.shopify_get_orders_with_filters --field-path orders[] --user-id 8cb7cbf2-f7a6-473a-920f-b6d2b9cc0c8d --use-toolbox
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from typing import Any, Dict

from mcp_agent.knowledge.utils import summarize_schema_for_llm
from mcp_agent.knowledge.utils import flatten_schema_fields


def _load_wrapper_schema(tool_id: str) -> Dict[str, Any]:
    provider, _, tool_name = tool_id.partition(".")
    if not provider or not tool_name:
        raise ValueError("tool_id must look like '<provider>.<tool_name>'")
    module = importlib.import_module(f"mcp_agent.actions.wrappers.{provider}")
    func = getattr(module, tool_name, None)
    if func is None:
        raise ValueError(f"Wrapper function not found: {provider}.{tool_name}")
    schema = getattr(func, "__tb_output_schema__", None)
    if not isinstance(schema, dict):
        raise ValueError(f"No __tb_output_schema__ found for {tool_id}")
    return schema


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect summarizer + schema path traversal.")
    parser.add_argument("--tool-id", required=True, help="Tool id, e.g. shopify.shopify_get_orders_with_filters")
    parser.add_argument("--field-path", default="", help='Optional field path, e.g. "orders[]" or "orders[].line_items[]"')
    parser.add_argument(
        "--user-id",
        default="",
        help="Optional user id for end-to-end inspection via toolbox tool (requires DB/OAuth setup).",
    )
    parser.add_argument(
        "--use-toolbox",
        action="store_true",
        help="Call toolbox.inspect_tool_output (end-to-end) instead of only local traversal.",
    )
    parser.add_argument("--summary-max-depth", type=int, default=3)
    parser.add_argument("--summary-max-fields", type=int, default=30)
    parser.add_argument("--inspect-max-depth", type=int, default=4)
    parser.add_argument("--inspect-max-fields", type=int, default=120)
    args = parser.parse_args()

    try:
        schema = _load_wrapper_schema(args.tool_id)
    except Exception as exc:
        print(f"Failed to load wrapper schema: {exc}", file=sys.stderr)
        return 1

    summary_fields, has_hidden = summarize_schema_for_llm(
        schema,
        max_depth=args.summary_max_depth,
        max_fields=args.summary_max_fields,
    )

    print(f"tool_id: {args.tool_id}")
    print(f"summary_has_hidden_fields: {has_hidden}")
    print(f"summary_output_fields ({len(summary_fields)}):")
    for line in summary_fields:
        print(f"  - {line}")

    if has_hidden:
        has_fold = any("inspect_tool_output" in line and "contains" in line for line in summary_fields)
        print(f"summary_has_fold_markers: {has_fold}")

    if args.field_path:
        if args.use_toolbox:
            if not args.user_id:
                print("--use-toolbox requires --user-id", file=sys.stderr)
                return 2
            from mcp_agent.core.context import AgentContext
            from mcp_agent.actions.wrappers.toolbox import inspect_tool_output

            ctx = AgentContext.create(args.user_id)
            resp = inspect_tool_output(
                ctx,
                tool_id=args.tool_id,
                field_path=args.field_path,
                max_depth=args.inspect_max_depth,
                max_fields=args.inspect_max_fields,
            )
            print("\ninspect_toolbox_response:")
            print(json.dumps(resp, indent=2, ensure_ascii=False))
        else:
            # Reuse the traversal helpers from the toolbox wrapper module to match production behavior.
            toolbox = importlib.import_module("mcp_agent.actions.wrappers.toolbox")
            unwrap = getattr(toolbox, "_unwrap_data_envelope")
            navigate = getattr(toolbox, "_navigate_schema")
            schema_type = getattr(toolbox, "_schema_type")
            children_for_node = getattr(toolbox, "_children_for_node")
            array_item_schema = getattr(toolbox, "_array_item_schema")

            base_schema = unwrap(schema)
            node = navigate(base_schema, args.field_path)
            node_type = schema_type(node)
            children, total_child_fields, children_truncated = children_for_node(node)
            preview_schema: Dict[str, Any] = node
            if node_type == "array":
                preview_schema = array_item_schema(node) or {}

            flattened_preview = flatten_schema_fields(
                preview_schema,
                max_depth=args.inspect_max_depth,
                max_fields=args.inspect_max_fields,
            )

            payload = {
                "tool_id": args.tool_id,
                "field_path": args.field_path,
                "node_type": node_type,
                "children": children,
                "flattened_preview": flattened_preview,
                "total_child_fields": total_child_fields,
                "truncated": bool(children_truncated or len(flattened_preview) >= args.inspect_max_fields),
            }
            print("\ninspect_preview:")
            print(json.dumps(payload, indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
