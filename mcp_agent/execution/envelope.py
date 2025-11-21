"""Slim envelope processing for MCP tool responses (migrated from toolbox/envelope.py).

Normalizes and aggressively truncates responses for LLM consumption.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext
    from mcp_agent.types import ActionResponse


def unwrap_nested_data(value: Any) -> Any:
    """
    Recursively collapse common `{"data": {...}}` nesting patterns.
    
    Args:
        value: Potentially nested data structure
    
    Returns:
        Unnested data
    """
    if isinstance(value, dict):
        collapsed = {k: unwrap_nested_data(v) for k, v in value.items()}
        if set(collapsed.keys()) == {"data"} and isinstance(collapsed["data"], dict):
            return collapsed["data"]
        return collapsed
    if isinstance(value, list):
        return [unwrap_nested_data(item) for item in value]
    return value


def unwrap_composio_content(data: Any) -> Any:
    """
    Detect and unwrap Composio's double-encoded response format.
    
    Composio returns: {"content": [{"text": "{\"actual\": \"data\"}"}], ...}
    This function parses the stringified JSON and returns the actual data.
    """
    if not isinstance(data, dict):
        return data
    
    content = data.get("content")
    if isinstance(content, list) and len(content) > 0:
        item = content[0]
        if isinstance(item, dict) and "text" in item:
            text = item["text"]
            if isinstance(text, str) and (text.startswith("{") or text.startswith("[")):
                try:
                    parsed = json.loads(text)

                    if isinstance(parsed, dict) and "data" in parsed:
                        is_envelope = any(
                            key in parsed
                            for key in (
                                "successfull",
                                "successful",
                                "auth_refresh_required",
                                "log_id",
                            )
                        )

                        if is_envelope:
                            s1 = parsed.get("successfull")
                            s2 = parsed.get("successful")
                            if (s1 is not False) and (s2 is not False):
                                return parsed["data"]
                            return parsed

                    return parsed
                except (ValueError, TypeError, json.JSONDecodeError):
                    pass
    
    return data


def normalize_action_response(raw: Dict[str, Any] | None) -> ActionResponse:
    """
    Normalize a raw MCP/tool response into a canonical ActionResponse envelope.
    
    Enforces:
        - `successful`: bool (derived from success/successfull/error fields)
        - `data`: dict (unwraps double-nesting and wraps non-dicts)
        - `error`: string or None
        - `raw`: original provider payload (when provided)
    
    Args:
        raw: Raw MCP response dict
    
    Returns:
        Normalized ActionResponse
    """
    from mcp_agent.types import ActionResponse
    
    source: Dict[str, Any] = dict(raw or {})
    
    # Derive success flag from historical variants
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
    
    # Normalize data payload to a dict
    data_value = source.get("data")
    if data_value is not None:
        data_value = unwrap_nested_data(data_value)
        data_value = unwrap_composio_content(data_value)
    
    if data_value is None:
        normalized_data: Dict[str, Any] = {}
    elif isinstance(data_value, dict):
        normalized_data = data_value
    else:
        normalized_data = {"value": unwrap_nested_data(data_value)}
    
    # Normalize error
    error_value = source.get("error")
    if error_value in (None, ""):
        error_str: str | None = None if successful else "unknown_error"
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


def process_observation(
    context: AgentContext,
    raw_response: Dict[str, Any],
    metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Process raw MCP response into slim observation for LLM.
    
    Applies aggressive truncation:
        - Strings > 500 chars → truncated with "..."
        - Arrays > 20 items → first 20 + truncation notice
        - Objects nested > 3 levels → flattened
    
    Args:
        context: Agent context (for logging)
        raw_response: Raw MCP tool response
        metadata: Optional metadata about the tool
    
    Returns:
        Slim observation dict suitable for LLM
    """
    # Normalize first
    envelope = normalize_action_response(raw_response)
    
    # Check success
    if not envelope["successful"]:
        return {
            "successful": False,
            "error": envelope["error"],
        }
    
    # Truncate data
    data = envelope["data"]
    slim_data = _truncate_recursive(data, max_depth=3, depth=0)
    
    return {
        "successful": True,
        "data": slim_data,
    }


def _truncate_recursive(obj: Any, max_depth: int, depth: int) -> Any:
    """
    Recursively truncate data structures for LLM consumption.
    
    Args:
        obj: Object to truncate
        max_depth: Maximum nesting depth
        depth: Current depth
    
    Returns:
        Truncated object
    """
    MAX_STR_LEN = 500
    MAX_ARRAY_LEN = 20
    
    # Stop at max depth
    if depth >= max_depth:
        if isinstance(obj, (dict, list)):
            return f"<truncated: {type(obj).__name__} at depth {depth}>"
        return obj
    
    # Truncate strings
    if isinstance(obj, str):
        if len(obj) > MAX_STR_LEN:
            return obj[:MAX_STR_LEN] + "..."
        return obj
    
    # Truncate lists
    if isinstance(obj, list):
        if len(obj) > MAX_ARRAY_LEN:
            truncated = [_truncate_recursive(item, max_depth, depth + 1) for item in obj[:MAX_ARRAY_LEN]]
            return truncated + [{"_truncated": True, "_total": len(obj)}]
        return [_truncate_recursive(item, max_depth, depth + 1) for item in obj]
    
    # Truncate dicts
    if isinstance(obj, dict):
        return {
            k: _truncate_recursive(v, max_depth, depth + 1)
            for k, v in obj.items()
        }
    
    # Pass through primitives
    return obj
