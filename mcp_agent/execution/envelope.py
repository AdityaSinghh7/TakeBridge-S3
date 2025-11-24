"""Response normalization for MCP tool outputs.

Normalizes raw MCP responses into canonical format, unwrapping nested structures
and handling provider-specific encoding patterns.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
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

    Also checks the isError flag to detect backend errors even when the outer
    envelope indicates success.
    """
    import os
    import sys

    if not isinstance(data, dict):
        return data

    # Check if Composio flagged this as an error (even if outer envelope succeeded)
    is_error = data.get("isError", False)

    content = data.get("content")
    if isinstance(content, list) and len(content) > 0:
        item = content[0]
        if isinstance(item, dict) and "text" in item:
            text = item["text"]
            if isinstance(text, str) and (text.startswith("{") or text.startswith("[")):
                try:
                    parsed = json.loads(text)

                    # Debug logging
                    if os.getenv("MCP_DEBUG_UNWRAP") == "1":
                        print(f"\n[DEBUG] unwrap_composio_content parsed:", file=sys.stderr)
                        print(f"  isError flag: {is_error}", file=sys.stderr)
                        print(f"  Type: {type(parsed)}", file=sys.stderr)
                        if isinstance(parsed, dict):
                            print(f"  Keys: {list(parsed.keys())}", file=sys.stderr)
                            print(f"  successful/successfull: {parsed.get('successful')}/{parsed.get('successfull')}", file=sys.stderr)
                            if "data" in parsed:
                                inner_data = parsed["data"]
                                print(f"  data type: {type(inner_data)}", file=sys.stderr)
                                if isinstance(inner_data, dict):
                                    print(f"  data keys: {list(inner_data.keys())}", file=sys.stderr)
                                    if "messages" in inner_data:
                                        msgs = inner_data["messages"]
                                        print(f"  messages count: {len(msgs) if isinstance(msgs, list) else 'N/A'}", file=sys.stderr)

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

                            # If isError flag is set OR inner response failed, return full envelope
                            if is_error or (s1 is False) or (s2 is False):
                                if os.getenv("MCP_DEBUG_UNWRAP") == "1":
                                    print(f"  → Returning full envelope (error detected)", file=sys.stderr)
                                return parsed

                            # Success case: extract data
                            if (s1 is not False) and (s2 is not False):
                                extracted_data = parsed["data"]
                                if os.getenv("MCP_DEBUG_UNWRAP") == "1":
                                    print(f"  → Extracting data from envelope", file=sys.stderr)
                                return extracted_data

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
