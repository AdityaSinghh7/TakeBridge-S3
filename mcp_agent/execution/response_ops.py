"""Single source of truth for MCP tool response handling.

Provides consistent operations for:
- Success detection
- Error extraction (top-level or nested)
- Double-nested/Composio unwrapping
- Nested key lookup
- Canonical ActionResponse envelope creation
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List

from mcp_agent.types import ActionResponse


class MCPResponseOps:
    """Utility wrapper around a raw MCP tool response payload."""

    def __init__(self, raw: Dict[str, Any] | None) -> None:
        self._had_raw_input = raw is not None
        self.raw: Dict[str, Any] = dict(raw or {})

    # --- Core helpers ---

    @staticmethod
    def unwrap_nested_data(value: Any) -> Any:
        """Recursively collapse common `{'data': {...}}` nesting patterns."""
        if isinstance(value, dict):
            collapsed = {k: MCPResponseOps.unwrap_nested_data(v) for k, v in value.items()}
            if set(collapsed.keys()) == {"data"} and isinstance(collapsed["data"], dict):
                return collapsed["data"]
            return collapsed
        if isinstance(value, list):
            return [MCPResponseOps.unwrap_nested_data(item) for item in value]
        return value

    @staticmethod
    def _unwrap_composio_content(data: Any) -> Any:
        """
        Detect and unwrap Composio's double-encoded response format.

        Composio returns: {"content": [{"text": "{\"actual\": \"data\"}"}], ...}
        This parses the stringified JSON and returns the actual data.
        """
        if not isinstance(data, dict):
            return data

        is_error_flag = data.get("isError", False)
        content = data.get("content")
        if isinstance(content, list) and content:
            item = content[0]
            if isinstance(item, dict) and "text" in item:
                text = item.get("text")
                if isinstance(text, str) and (text.startswith("{") or text.startswith("[")):
                    try:
                        parsed = json.loads(text)
                    except (ValueError, TypeError, json.JSONDecodeError):
                        return data

                    # If parsed payload itself looks like an envelope, respect it
                    if isinstance(parsed, dict) and "data" in parsed:
                        looks_like_envelope = any(
                            key in parsed for key in ("successfull", "successful", "auth_refresh_required", "log_id")
                        )
                        if looks_like_envelope:
                            s1 = parsed.get("successfull")
                            s2 = parsed.get("successful")
                            if is_error_flag or (s1 is False) or (s2 is False):
                                return parsed
                            if (s1 is not False) and (s2 is not False):
                                return parsed.get("data")
                        return parsed
                    return parsed
        return data

    # --- Public operations ---

    def is_success(self) -> bool:
        """Determine success using common MCP/Composio fields and error flags."""
        source = self.raw
        top_success = source.get("successful")
        if top_success is None:
            top_success = source.get("success")
        if top_success is None:
            top_success = source.get("successfull")

        top_error = source.get("error")

        nested_success = None
        nested_error = None
        data_field = source.get("data")
        if isinstance(data_field, dict):
            if "successful" in data_field:
                nested_success = data_field.get("successful")
            elif "successfull" in data_field:
                nested_success = data_field.get("successfull")
            if "error" in data_field:
                nested_error = data_field.get("error")

        # Composio explicit error flag overrides optimistic defaults
        if source.get("isError") is True:
            return False
        if top_success is False:
            return False
        if nested_success is False:
            return False
        if nested_error not in (None, "", False) and nested_error is not None:
            return False
        if top_error not in (None, "", False):
            return False

        if nested_success is True:
            return True
        if top_success is True:
            return True

        if top_success is None and nested_success is None:
            return True
        return bool(top_success)

    def get_error(self) -> str | None:
        """Extract best-effort error message from known locations."""
        source = self.raw
        # 1) Top-level error field
        top_error = source.get("error")
        if top_error not in (None, ""):
            return str(top_error)

        # 2) Nested data.error
        data_field = source.get("data")
        if isinstance(data_field, dict):
            nested_error = data_field.get("error")
            if nested_error not in (None, ""):
                return str(nested_error)

        # 3) Composio encoded JSON error
        composio = self._unwrap_composio_content(data_field)
        if isinstance(composio, dict):
            parsed_err = composio.get("error") or composio.get("message")
            if parsed_err not in (None, ""):
                return str(parsed_err)

        return None

    def unwrap_data(self) -> Any:
        """Unwrap nested data and Composio content to the inner payload."""
        data_value = self.raw.get("data")
        if data_value is None:
            return {}

        data_value = MCPResponseOps.unwrap_nested_data(data_value)
        data_value = MCPResponseOps._unwrap_composio_content(data_value)
        return data_value

    def get_by_path(self, path: Iterable[str] | str, default: Any = None) -> Any:
        """
        Traverse nested dict/list using a path of keys/indexes.

        Args:
            path: iterable of keys or a dotted string (e.g., "a.b.c")
            default: value returned if path is missing
        """
        if isinstance(path, str):
            parts: List[str] = [p for p in path.split(".") if p]
        else:
            parts = list(path)

        current: Any = self.raw
        for key in parts:
            if isinstance(current, dict):
                if key not in current:
                    return default
                current = current[key]
                continue
            if isinstance(current, list):
                try:
                    idx = int(key)
                except (TypeError, ValueError):
                    return default
                if idx < 0 or idx >= len(current):
                    return default
                current = current[idx]
                continue
            return default
        return current

    def to_action_response(self) -> ActionResponse:
        """Produce canonical ActionResponse envelope."""
        successful = self.is_success()
        unwrapped_data = self.unwrap_data()
        data_payload: Dict[str, Any]
        if unwrapped_data is None:
            data_payload = {}
        elif isinstance(unwrapped_data, dict):
            data_payload = unwrapped_data
        else:
            data_payload = {"value": unwrapped_data}

        error_value = self.get_error()
        if error_value in (None, "") and not successful:
            error_value = "unknown_error"

        envelope: ActionResponse = ActionResponse(
            successful=successful,
            data=data_payload,
            error=error_value,
        )
        if self._had_raw_input:
            envelope["raw"] = self.raw
        return envelope

    # --- Convenience constructors ---

    @classmethod
    def from_mcp_client(cls, payload: Dict[str, Any] | None) -> "MCPResponseOps":
        """Build from raw MCP client payload."""
        return cls(payload or {})


__all__ = ["MCPResponseOps"]
