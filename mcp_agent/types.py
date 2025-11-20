from __future__ import annotations

from typing import Any, Optional, TypedDict


class ActionResponse(TypedDict, total=False):
    """
    Canonical wrapper for Composio/MCP tool responses.

    Fields:
      - successful: True when the tool completed successfully.
      - data: Tool-specific payload (always a dict in normalized responses).
      - error: Optional, human-readable error message when unsuccessful.
      - raw: Optional, original provider payload (for debugging/inspection).

    Internally, additional fields (e.g. logs, provider, tool) may be present,
    but callers should always be able to rely on this core contract.
    """

    successful: bool
    data: dict[str, Any]
    error: Optional[str]
    raw: Any | None


class ToolInvocationResult(TypedDict, total=False):
    successful: bool
    error: Optional[str]
    data: Any
    logs: Any
    provider: str
    tool: str
    payload_keys: list[str]
