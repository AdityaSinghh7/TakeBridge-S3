from __future__ import annotations

from typing import TYPE_CHECKING

from mcp_agent.types import ToolInvocationResult

from ._common import _clean_payload, _invoke_mcp_tool, ensure_authorized

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext


def figma_get_file_json(
    context: "AgentContext",
    file_key: str,
    branch_data: bool | None = None,
    depth: int | None = None,
    geometry: str | None = None,
    ids: str | None = None,
    include_raw: bool | None = None,
    plugin_data: str | None = None,
    simplify: bool = True,
    version: str | None = None,
) -> ToolInvocationResult:
    """
    Retrieve Figma file data with optional simplification.

    Args:
        file_key: Figma file key.
        branch_data: Include branch data.
        depth: Node depth.
        geometry: Geometry filter.
        ids: Specific node IDs.
        include_raw: Include raw response.
        plugin_data: Plugin data filter.
        simplify: Whether to simplify the response (default True).
        version: Version ID.
    """
    provider = "figma"
    tool_name = "FIGMA_GET_FILE_JSON"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "file_key": file_key,
            "branch_data": branch_data,
            "depth": depth,
            "geometry": geometry,
            "ids": ids,
            "include_raw": include_raw,
            "plugin_data": plugin_data,
            "simplify": simplify,
            "version": version,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)
