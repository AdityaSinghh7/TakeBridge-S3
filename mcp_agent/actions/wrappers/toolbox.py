"""Local toolbox helpers (no external MCP provider).

This module exposes internal utilities as standard MCP tools so the planner can
use them with the same "tool" command shape as any other provider.

Currently includes:
- `inspect_tool_output`: schema drill-down for tool output `data` payloads.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from mcp_agent.core.context import AgentContext
from mcp_agent.types import ToolInvocationResult
from mcp_agent.knowledge.introspection import get_index
from mcp_agent.knowledge.utils import flatten_schema_fields


def _unwrap_data_envelope(schema: Any) -> Dict[str, Any]:
    """If schema is an envelope with top-level `data`, return that subtree."""
    if not isinstance(schema, dict):
        return {}
    props = schema.get("properties")
    if isinstance(props, dict):
        data_schema = props.get("data")
        if isinstance(data_schema, dict):
            return data_schema
    return schema


def _schema_type(schema: Any) -> str:
    if not isinstance(schema, dict):
        return "unknown"
    value = schema.get("type")
    if isinstance(value, str) and value:
        return value
    if isinstance(schema.get("properties"), dict):
        return "object"
    if "items" in schema:
        return "array"
    if "oneOf" in schema or "anyOf" in schema:
        return "union"
    if "enum" in schema:
        return "enum"
    return "unknown"


def _array_item_schema(schema: Dict[str, Any]) -> Dict[str, Any] | None:
    items = schema.get("items")
    return items if isinstance(items, dict) else None


def _parse_field_path(field_path: str) -> List[Tuple[str, int]]:
    """
    Parse a dot path into segments.

    Returns list of (name, array_hops) where array_hops is number of trailing [].
      - "variants[].inventory_item" -> [("variants", 1), ("inventory_item", 0)]
      - "orders[][]" -> [("orders", 2)]
    """
    field_path = (field_path or "").strip()
    if not field_path:
        return []
    parts = [p for p in field_path.split(".") if p]
    parsed: List[Tuple[str, int]] = []
    for part in parts:
        hops = 0
        while part.endswith("[]"):
            part = part[:-2]
            hops += 1
        parsed.append((part, hops))
    return parsed


def _navigate_schema(schema: Dict[str, Any], field_path: str) -> Dict[str, Any]:
    """Navigate into schema by field_path; returns the located schema node."""
    node: Dict[str, Any] = schema
    for name, hops in _parse_field_path(field_path):
        # Property selection
        if name:
            props = node.get("properties")
            if not isinstance(props, dict) or name not in props:
                raise KeyError(f"Unknown field '{name}' at path '{field_path}'.")
            child = props.get(name)
            if not isinstance(child, dict):
                raise KeyError(f"Field '{name}' at path '{field_path}' has no schema object.")
            node = child

        # Array hops (each [] moves into items)
        for _ in range(hops):
            if _schema_type(node) != "array":
                raise TypeError(f"Field '{name}' at path '{field_path}' is not an array.")
            item = _array_item_schema(node)
            if not isinstance(item, dict):
                raise TypeError(f"Array items schema missing for '{name}' at path '{field_path}'.")
            node = item

    return node


def _children_for_node(node: Dict[str, Any], *, max_children: int = 80) -> tuple[List[Dict[str, str]], int, bool]:
    """
    Return (children, total_child_fields, truncated_children).

    - For object nodes: children are its properties.
    - For array nodes: children are the item properties when item is object.
    """
    node_type = _schema_type(node)
    props: Dict[str, Any] = {}
    if node_type == "object":
        raw = node.get("properties")
        props = raw if isinstance(raw, dict) else {}
    elif node_type == "array":
        item = _array_item_schema(node) or {}
        raw = item.get("properties") if isinstance(item, dict) else None
        props = raw if isinstance(raw, dict) else {}

    total = len(props)
    items = list(props.items())
    truncated = total > max_children
    if truncated:
        items = items[:max_children]

    children: List[Dict[str, str]] = []
    for name, subschema in items:
        children.append({"name": str(name), "type": _schema_type(subschema)})

    return children, total, truncated


def inspect_tool_output(
    context: AgentContext,
    tool_id: str,
    field_path: str = "",
    max_depth: int = 4,
    max_fields: int = 120,
) -> ToolInvocationResult:
    """
    Inspect a tool's output schema (the `data` payload) at a specific field path.

    Args:
        context: Agent context (used for user-scoped toolbox index)
        tool_id: Full tool id (e.g., "shopify.shopify_get_order_list")
        field_path: Dot path into the output schema. Arrays use [] (e.g., "orders[]", "orders[].line_items[]").
        max_depth: Max depth for flattened preview of the located subtree.
        max_fields: Max number of flattened preview lines to return.
    """
    try:
        tool_id = (tool_id or "").strip()
        if not tool_id:
            return {"successful": False, "error": "tool_id is required."}

        index = get_index(user_id=context.user_id)
        spec = index.get_tool(tool_id)
        if spec is None:
            return {"successful": False, "error": f"Unknown tool_id '{tool_id}'."}

        base_schema = _unwrap_data_envelope(spec.output_schema or {})
        if not base_schema:
            return {"successful": False, "error": f"No output schema registered for '{tool_id}'."}

        node = _navigate_schema(base_schema, field_path)
        node_type = _schema_type(node)

        children, total_child_fields, children_truncated = _children_for_node(node)

        # Flatten preview of the located node. For array nodes, preview the item schema (if present).
        preview_schema = node
        if node_type == "array":
            preview_schema = _array_item_schema(node) or {}

        flattened_preview = flatten_schema_fields(
            preview_schema if isinstance(preview_schema, dict) else {},
            max_depth=max_depth,
            max_fields=max_fields,
        )

        truncated = bool(children_truncated or len(flattened_preview) >= max_fields)

        return {
            "successful": True,
            "data": {
                "tool_id": tool_id,
                "field_path": field_path or "",
                "node_type": node_type,
                "children": children,
                "flattened_preview": flattened_preview,
                "total_child_fields": int(total_child_fields),
                "truncated": bool(truncated),
            },
        }
    except Exception as exc:
        return {"successful": False, "error": str(exc)}


# Schema for the `data` payload returned by inspect_tool_output.
inspect_tool_output.__tb_output_schema__ = {
    "properties": {
        "data": {
            "type": "object",
            "properties": {
                "tool_id": {"type": "string"},
                "field_path": {"type": "string"},
                "node_type": {"type": "string"},
                "children": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "type": {"type": "string"},
                        },
                    },
                },
                "flattened_preview": {"type": "array", "items": {"type": "string"}},
                "total_child_fields": {"type": "integer"},
                "truncated": {"type": "boolean"},
            },
        }
    }
}

