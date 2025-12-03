"""Response normalization for MCP tool outputs.

Delegates core logic to MCPResponseOps (single source of truth).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

from mcp_agent.execution.response_ops import MCPResponseOps

if TYPE_CHECKING:
    from mcp_agent.types import ActionResponse


def unwrap_nested_data(value: Any) -> Any:
    """Compatibility wrapper: delegate to MCPResponseOps."""
    return MCPResponseOps.unwrap_nested_data(value)


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
    ops = MCPResponseOps(raw or {})
    return ops.to_action_response()


# Backwards-compatible alias; kept for existing imports that expect the function name.
unwrap_composio_content = MCPResponseOps._unwrap_composio_content

__all__ = ["normalize_action_response", "unwrap_nested_data", "unwrap_composio_content"]
