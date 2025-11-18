from __future__ import annotations

from typing import Any, Dict, List


def format_data_schema_pretty(schema: Dict[str, Any], header: str) -> str:
    """
    Render a JSON-schema-like description of the `data` field into a
    human-readable bullet list.
    """
    lines: List[str] = [header]

    def walk(path: str, node: Dict[str, Any]) -> None:
        t = node.get("type", "any")
        if isinstance(t, list):
            t_str = " | ".join(str(entry) for entry in t)
        else:
            t_str = str(t)

        if t_str == "object":
            props = node.get("properties", {}) or {}
            for key, child in props.items():
                child_path = f"{path}.{key}" if path else key
                child_type = child.get("type", "any")
                if isinstance(child_type, list):
                    child_type_str = " | ".join(str(entry) for entry in child_type)
                else:
                    child_type_str = str(child_type)
                desc = child.get("description", "")
                lines.append(f"- {child_path}: {child_type_str}")
                if desc:
                    lines.append(f"  {desc}")
                walk(child_path, child)
        elif t_str == "array":
            items = node.get("items", {"type": "any"})
            item_type = items.get("type", "any")
            if isinstance(item_type, list):
                item_type_str = " | ".join(str(entry) for entry in item_type)
            else:
                item_type_str = str(item_type)
            lines.append(f"- {path}: list[{item_type_str}]")
            walk(f"{path}[*]", items)

    walk("data", schema)
    return "\n".join(lines)

