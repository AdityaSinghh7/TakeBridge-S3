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

googlesheets_batch_get.__tb_output_schema__ = {
  "properties": {
    "data": {
      "additionalProperties": False,
      "description": "Data from the action execution",
      "properties": {
        "spreadsheetId": {
          "description": "The ID of the spreadsheet from which the values were retrieved.",
          "title": "Spreadsheet Id",
          "type": "string"
        },
        "valueRanges": {
          "description": "An array of ValueRange objects, one for each requested range. The order of items matches the order of the ranges specified in the request.",
          "items": {
            "properties": {
              "majorDimension": {
                "default": None,
                "description": "Indicates whether the values are grouped by rows or by columns. The outer array of 'values' corresponds to this dimension ('ROWS' means each inner array is a row; 'COLUMNS' means each inner array is a column).",
                "nullable": True,
                "title": "Major Dimension",
                "type": "string"
              },
              "range": {
                "description": "The A1-notation of the range that the values cover, including the sheet name (e.g., 'Sheet1!A1:Z999'). On output, this reflects the full requested range, while the returned values omit trailing empty rows/columns.",
                "title": "Range",
                "type": "string"
              },
              "values": {
                "default": None,
                "description": "The data in the range. The outer array corresponds to the major dimension (rows if majorDimension=ROWS, columns if majorDimension=COLUMNS). Each inner array contains the cell values for that row or column. Trailing empty rows/columns are omitted. Returned value types depend on the valueRenderOption used in the request: formatted strings by default, or unformatted numbers/booleans if UNFORMATTED_VALUE is used. Depending on the data and client, empty rows/columns may appear as empty arrays, and empty cells may be omitted at the end, represented as empty strings, or as null.",
                "items": {
                  "items": {
                    "anyOf": [
                      {
                        "type": "string"
                      },
                      {
                        "type": "integer"
                      },
                      {
                        "type": "number"
                      },
                      {
                        "type": "boolean"
                      },
                      {
                        "type": "null"
                      }
                    ]
                  },
                  "properties": {},
                  "type": "array"
                },
                "nullable": True,
                "title": "Values",
                "type": "array"
              }
            },
            "required": [
              "range"
            ],
            "title": "ValueRange",
            "type": "object"
          },
          "title": "Value Ranges",
          "type": "array"
        }
      },
      "required": [
        "spreadsheetId",
        "valueRanges"
      ],
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
  "title": "BatchGetResponseWrapper",
  "type": "object"
}
