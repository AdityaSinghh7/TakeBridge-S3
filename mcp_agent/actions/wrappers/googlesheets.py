from __future__ import annotations

from typing import TYPE_CHECKING, List

from mcp_agent.types import ToolInvocationResult

from ._common import _clean_payload, _invoke_mcp_tool, ensure_authorized

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext


def googlesheets_batch_get(
    context: "AgentContext",
    spreadsheet_id: str,
    ranges: List[str] | None = None,
    dateTimeRenderOption: str | None = "SERIAL_NUMBER",
    valueRenderOption: str | None = "FORMATTED_VALUE",
) -> ToolInvocationResult:
    """
    Retrieve data from specified ranges in a Google Spreadsheet.

    Args:
        spreadsheet_id: Spreadsheet ID.
        ranges: List of ranges to fetch.
        dateTimeRenderOption: Date/time render option.
        valueRenderOption: Value render option.
    """
    provider = "googlesheets"
    tool_name = "GOOGLESHEETS_BATCH_GET"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "spreadsheet_id": spreadsheet_id,
            "ranges": ranges,
            "dateTimeRenderOption": dateTimeRenderOption,
            "valueRenderOption": valueRenderOption,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)
