from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mcp_agent.types import ToolInvocationResult

from ._common import _clean_payload, _invoke_mcp_tool, ensure_authorized

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext


def dropbox_upload_file(
    context: "AgentContext",
    path: str,
    content: Any,
    autorename: bool | None = None,
    mode: str = "add",
    mute: bool | None = None,
    strict_conflict: bool | None = None,
) -> ToolInvocationResult:
    """
    Upload a file to Dropbox at a specified path.

    Args:
        path: Destination path in Dropbox.
        content: File content payload.
        autorename: Whether to autorename on conflict.
        mode: Upload mode (default add).
        mute: Whether to mute notifications.
        strict_conflict: Whether to enforce strict conflict handling.
    """
    provider = "dropbox"
    tool_name = "DROPBOX_UPLOAD_FILE"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "path": path,
            "content": content,
            "autorename": autorename,
            "mode": mode,
            "mute": mute,
            "strict_conflict": strict_conflict,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)
