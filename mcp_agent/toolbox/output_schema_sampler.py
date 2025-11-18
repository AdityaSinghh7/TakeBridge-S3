from __future__ import annotations

from typing import Any, Dict, List

from mcp_agent.toolbox.envelope import normalize_action_response
from mcp_agent.toolbox.types import ActionResponse


def _infer_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def _merge_type_sets(existing: List[str], new_type: str) -> List[str]:
    if new_type not in existing:
        existing.append(new_type)
    return existing


def _infer_schema_for_values(values: List[Any]) -> Dict[str, Any]:
    """
    Infer a simple JSON-schema-like shape for a list of values.

    This is intentionally conservative and only uses a small subset of JSON
    Schema: type, properties, required, and items.
    """
    if not values:
        return {"type": "unknown"}

    first = values[0]
    if isinstance(first, dict):
        return infer_json_schema_from_samples(values)  # type: ignore[arg-type]
    if isinstance(first, list):
        item_values: List[Any] = []
        for v in values:
            if isinstance(v, list):
                item_values.extend(v)
        if not item_values:
            return {"type": "array"}
        return {"type": "array", "items": _infer_schema_for_values(item_values)}

    types: List[str] = []
    for v in values:
        types = _merge_type_sets(types, _infer_type(v))
    if len(types) == 1:
        return {"type": types[0]}
    return {"type": types}


def infer_json_schema_from_samples(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Infer a minimal JSON-schema-like object for a list of payload samples.

    Currently supports:
      - type: "object"
      - properties: per-key schemas
      - required: keys present in all samples
    """
    if not samples:
        return {"type": "object", "properties": {}, "required": []}

    all_keys = set().union(*(sample.keys() for sample in samples))
    required_keys = {
        key
        for key in all_keys
        if all(key in sample for sample in samples)
    }
    properties: Dict[str, Any] = {}
    for key in sorted(all_keys):
        values = [sample[key] for sample in samples if key in sample]
        properties[key] = _infer_schema_for_values(values)

    return {
        "type": "object",
        "properties": properties,
        "required": sorted(required_keys),
    }


def sample_output_schema_for_wrapper(
    func: callable,
    success_examples: List[Dict[str, Any]],
    error_examples: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """
    Call a wrapper function with example args and infer output schemas.

    This is intended for use by dev scripts and probes only and should not be
    invoked in latency-sensitive planner paths.
    """
    success_payloads: List[Dict[str, Any]] = []
    error_payloads: List[Dict[str, Any]] = []

    for payload in success_examples:
        raw: ActionResponse = func(**payload)  # type: ignore[misc]
        env = normalize_action_response(raw)
        if env["successful"]:
            data = env["data"]
            if isinstance(data, dict):
                success_payloads.append(data)
        else:
            data = env["data"]
            if isinstance(data, dict):
                error_payloads.append(data)

    if error_examples:
        for payload in error_examples:
            raw_err: ActionResponse = func(**payload)  # type: ignore[misc]
            env_err = normalize_action_response(raw_err)
            if env_err["successful"]:
                data = env_err["data"]
                if isinstance(data, dict):
                    success_payloads.append(data)
            else:
                data = env_err["data"]
                if isinstance(data, dict):
                    error_payloads.append(data)

    schema: Dict[str, Any] = {}
    if success_payloads:
        schema["success"] = infer_json_schema_from_samples(success_payloads)
    if error_payloads:
        schema["error"] = infer_json_schema_from_samples(error_payloads)
    return schema

