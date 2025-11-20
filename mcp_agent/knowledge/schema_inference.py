from __future__ import annotations

from typing import Any, Dict, List


def infer_schema_from_value(value: Any) -> Dict[str, Any]:
    """
    Infer a JSON-schema-like description from a sample value.

    This is best-effort and intended for documentation, not strict validation.
    """
    if isinstance(value, dict):
        return {
            "type": "object",
            "properties": {k: infer_schema_from_value(v) for k, v in value.items()},
        }
    if isinstance(value, list):
        if not value:
            return {"type": "array", "items": {"type": "any"}}
        item_schemas = [infer_schema_from_value(v) for v in value[:3]]
        return {
            "type": "array",
            "items": merge_schemas(item_schemas),
        }
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int):
        return {"type": "integer"}
    if isinstance(value, float):
        return {"type": "number"}
    if value is None:
        return {"type": "null"}
    return {"type": "string"}


def merge_schemas(schemas: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Merge multiple inferred schemas into a broader one.

    Used primarily for array item inference.
    """
    if not schemas:
        return {"type": "any"}

    types = {s.get("type") for s in schemas}
    if len(types) == 1:
        t = types.pop()
        base: Dict[str, Any] = {"type": t}
        if t == "object":
            props: Dict[str, List[Dict[str, Any]]] = {}
            for s in schemas:
                for k, v in s.get("properties", {}).items():
                    props.setdefault(k, []).append(v)
            base["properties"] = {k: merge_schemas(vs) for k, vs in props.items()}
        elif t == "array":
            items = [s.get("items", {"type": "any"}) for s in schemas]
            base["items"] = merge_schemas(items)
        return base

    return {"type": list(types)}

