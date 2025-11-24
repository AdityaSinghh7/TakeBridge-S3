from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mcp_agent.types import ToolInvocationResult

from ._common import _clean_payload, _invoke_mcp_tool, ensure_authorized

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext


def googledrive_upload_file(
    context: "AgentContext",
    file_to_upload: Any,
    folder_to_upload_to: str | None = None,
) -> ToolInvocationResult:
    """
    Upload a file to Google Drive, optionally into a specific folder.

    Args:
        file_to_upload: File payload (max 5MB).
        folder_to_upload_to: Folder ID to upload into; uploads to root if omitted.
    """
    provider = "googledrive"
    tool_name = "GOOGLEDRIVE_UPLOAD_FILE"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "file_to_upload": file_to_upload,
            "folder_to_upload_to": folder_to_upload_to,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)
