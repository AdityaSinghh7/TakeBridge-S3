from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

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


def _unwrap_inner_envelope(obj: Any) -> Any:
    """
    Some providers (e.g., Composio tools) embed a secondary
    success/error envelope that looks like:

        {
          "successfull": bool,
          "successful": bool,
          "error": str | None,
          "data": {...},
          ...
        }

    For schema inference we care about the inner `data` payload, not this
    secondary envelope. When we detect this pattern, return `obj['data']`
    (if it is a dict/list); otherwise return the object unchanged.
    """
    if isinstance(obj, dict) and "data" in obj:
        if any(k in obj for k in ("successfull", "successful", "error", "logs", "auth_refresh_required")):
            inner = obj.get("data")
            if isinstance(inner, (dict, list)):
                return inner
    return obj
def _extract_payload_for_schema(
    envelope: ActionResponse,
    provider: Optional[str] = None,
    tool_name: Optional[str] = None,
) -> Any:
    """
    Given a canonical ActionResponse, return the object we should treat as the
    root for schema inference.

    For Composio-style MCP responses, `data` often has the shape:
        { "content": [...], "isError": bool, "meta": ..., "structuredContent": ... }

    The actual tool payload is usually nested in structuredContent or in
    JSON-encoded `content[*].text`. This helper tries to unwrap that; if it
    can't, it falls back to envelope["data"].
    """
    data = envelope.get("data") or {}
    if not isinstance(data, dict):
        return data

    has_content = isinstance(data.get("content"), list)
    has_is_error = "isError" in data

    if has_content and has_is_error:
        # 1. Prefer structuredContent if it's already a dict
        sc = data.get("structuredContent")
        if isinstance(sc, dict):
            return _unwrap_inner_envelope(sc)

        # 2. Try parsing structuredContent as JSON string
        if isinstance(sc, str):
            try:
                parsed = json.loads(sc)
                if isinstance(parsed, (dict, list)):
                    return _unwrap_inner_envelope(parsed)
            except Exception:
                pass

        # 3. Try parsing `content[*].text` as JSON or finding nested dicts
        for item in data.get("content", []):
            if not isinstance(item, dict):
                continue

            # Look for a nested dict directly
            for key in ("structuredContent", "data", "json"):
                blob = item.get(key)
                if isinstance(blob, dict):
                    return _unwrap_inner_envelope(blob)

            text = item.get("text")
            if isinstance(text, str):
                try:
                    parsed = json.loads(text)
                except Exception:
                    continue
                if isinstance(parsed, (dict, list)):
                    return _unwrap_inner_envelope(parsed)

        # If all else fails, fall through and use `data` as-is.

    # Non-Composio or unknown shape → just return data (possibly unwrapped)
    return _unwrap_inner_envelope(data)


def sample_output_schema_for_wrapper(
    func: callable,
    success_examples: List[Dict[str, Any]],
    error_examples: List[Dict[str, Any]] | None = None,
    *,
    provider: str | None = None,
    tool_name: str | None = None,
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
        root = _extract_payload_for_schema(env, provider=provider, tool_name=tool_name)
        if env["successful"]:
            if isinstance(root, dict):
                success_payloads.append(root)
        else:
            if isinstance(root, dict):
                error_payloads.append(root)

    if error_examples:
        for payload in error_examples:
            raw_err: ActionResponse = func(**payload)  # type: ignore[misc]
            env_err = normalize_action_response(raw_err)
            root_err = _extract_payload_for_schema(env_err, provider=provider, tool_name=tool_name)
            if env_err["successful"]:
                if isinstance(root_err, dict):
                    success_payloads.append(root_err)
            else:
                if isinstance(root_err, dict):
                    error_payloads.append(root_err)

    schema: Dict[str, Any] = {}
    if success_payloads:
        schema["success"] = infer_json_schema_from_samples(success_payloads)
    if error_payloads:
        schema["error"] = infer_json_schema_from_samples(error_payloads)
    return schema
