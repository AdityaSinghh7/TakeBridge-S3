from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

from mcp_agent.types import ToolInvocationResult

from ._common import _clean_payload, _invoke_mcp_tool, ensure_authorized

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext


def airtable_list_records(
    context: "AgentContext",
    baseId: str,
    tableIdOrName: str,
    cellFormat: str | None = "json",
    fields: List[str] | None = None,
    filterByFormula: str | None = None,
    maxRecords: int | None = None,
    offset: str | None = None,
    pageSize: int | None = 100,
    recordMetadata: List[Any] | None = None,
    returnFieldsByFieldId: bool | None = None,
    sort: List[Any] | None = None,
    timeZone: str | None = "utc",
    userLocale: str | None = None,
    view: str | None = None,
) -> ToolInvocationResult:
    """
    Retrieve records from an Airtable table with optional filters and pagination.

    Args:
        baseId: Airtable base ID.
        tableIdOrName: Table ID or name.
        cellFormat: Cell format (default json).
        fields: Fields to return.
        filterByFormula: Filter formula.
        maxRecords: Max records to return.
        offset: Pagination offset.
        pageSize: Page size (default 100).
        recordMetadata: Metadata fields to return.
        returnFieldsByFieldId: Whether to return fields by ID.
        sort: Sort configuration.
        timeZone: Timezone string (default utc).
        userLocale: User locale.
        view: View name or ID.
    """
    provider = "airtable"
    tool_name = "AIRTABLE_LIST_RECORDS"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "baseId": baseId,
            "tableIdOrName": tableIdOrName,
            "cellFormat": cellFormat,
            "fields": fields,
            "filterByFormula": filterByFormula,
            "maxRecords": maxRecords,
            "offset": offset,
            "pageSize": pageSize,
            "recordMetadata": recordMetadata,
            "returnFieldsByFieldId": returnFieldsByFieldId,
            "sort": sort,
            "timeZone": timeZone,
            "userLocale": userLocale,
            "view": view,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)


airtable_list_records.__tb_output_schema__ = {
  "properties": {
    "data": {
      "additionalProperties": False,
      "description": "Data from the action execution",
      "properties": {
        "response_data": {
          "additionalProperties": True,
          "description": "The raw JSON response from the Airtable API, containing the list of records and any pagination offset.",
          "title": "Response Data",
          "type": "object"
        }
      },
      "title": "Data",
      "type": "object"
    },
    "error": {
      "default": None,
      "description": "Error if any occurred during the execution of the action",
      "nullable": True,
      "title": "Error",
      "type": "string"
    },
    "successful": {
      "description": "Whether or not the action execution was successful or not",
      "title": "Successful",
      "type": "boolean"
    }
  },
  "required": [
    "data",
    "successful"
  ],
  "title": "ListRecordsResponseWrapper",
  "type": "object"
}
