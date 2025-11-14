from __future__ import annotations

from typing import Any, Optional, TypedDict


class ToolInvocationResult(TypedDict, total=False):
    successful: bool
    error: Optional[str]
    data: Any
    logs: Any
    provider: str
    tool: str
    payload_keys: list[str]
