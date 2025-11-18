from __future__ import annotations

from typing import Any, Dict

from .types import ActionResponse


# Canonical ActionResponse envelope used by planner, sandbox, and actions:
#
# {
#   "successful": bool,         # required
#   "data": dict[str, Any],     # required, always a dict (possibly empty)
#   "error": str | None,        # required, None when successful
#   "raw": Any | None,          # optional, original provider payload
# }
#
# All adapters MUST call normalize_action_response(...) and only pass this shape
# (or a superset carrying additional metadata) to the planner, sandbox, and
# raw_outputs. Downstream code should rely on these fields rather than legacy
# variants like "success" / "successfull".


def unwrap_nested_data(value: Any) -> Any:
    """
    Recursively collapse common `{\"data\": {...}}` nesting patterns.

    This mirrors the old sandbox-only collapse helper so that both planner and
    sandbox callers see a consistent payload shape.
    """
    if isinstance(value, dict):
        collapsed = {k: unwrap_nested_data(v) for k, v in value.items()}
        if set(collapsed.keys()) == {"data"} and isinstance(collapsed["data"], dict):
            return collapsed["data"]
        return collapsed
    if isinstance(value, list):
        return [unwrap_nested_data(item) for item in value]
    return value


def normalize_action_response(raw: Dict[str, Any] | None) -> ActionResponse:
    """
    Normalize a raw MCP/tool response into a canonical ActionResponse envelope.

    Enforces:
      - `successful`: bool (derived from `successful` / `success` / `successfull` / `error`)
      - `data`: dict (unwraps common double-nesting and wraps non-dicts)
      - `error`: string or None (None only when successful)
      - `raw`: original provider payload (when provided)
    """
    source: Dict[str, Any] = dict(raw or {})

    # Derive success flag from historical variants.
    success = source.get("successful")
    if success is None:
        success = source.get("success")
    if success is None:
        success = source.get("successfull")
    if success is None and "error" in source:
        success = source["error"] in (None, "", False)
    if success is None:
        success = True
    successful = bool(success)

    # Normalize data payload to a dict.
    data_value = source.get("data")
    if data_value is not None:
        data_value = unwrap_nested_data(data_value)
    if data_value is None:
        normalized_data: Dict[str, Any] = {}
    elif isinstance(data_value, dict):
        normalized_data = data_value
    else:
        normalized_data = {"value": unwrap_nested_data(data_value)}

    # Normalize error: when unsuccessful but no explicit error, fall back to
    # a generic sentinel so callers never see a missing error message.
    error_value = source.get("error")
    if error_value in (None, ""):
        if successful:
            error_str: str | None = None
        else:
            error_str = "unknown_error"
    else:
        error_str = str(error_value)

    envelope: ActionResponse = ActionResponse(
        successful=successful,
        data=normalized_data,
        error=error_str,
    )
    if raw is not None:
        envelope["raw"] = raw
    return envelope
