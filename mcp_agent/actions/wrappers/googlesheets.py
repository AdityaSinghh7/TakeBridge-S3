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


def googlesheets_spreadsheets_values_append(
    context: "AgentContext",
    spreadsheetId: str,
    range: str,
    valueInputOption: str,
    values: list[list[str | int | float | bool]],
    includeValuesInResponse: bool | None = None,
    insertDataOption: str | None = None,
    majorDimension: str | None = None,
    responseDateTimeRenderOption: str | None = None,
    responseValueRenderOption: str | None = None,
) -> ToolInvocationResult:
    """
    Append values to a Google Sheet with optional formatting and response options.

    Args:
        spreadsheetId: Spreadsheet ID to update.
        range: A1 notation range to append after.
        valueInputOption: How the input data should be interpreted (RAW or USER_ENTERED).
        values: 2D array of values to append.
        includeValuesInResponse: Whether to include updated values in the response.
        insertDataOption: How input data should be inserted (OVERWRITE or INSERT_ROWS).
        majorDimension: Major dimension of values (ROWS or COLUMNS).
        responseDateTimeRenderOption: How dates/times are rendered in the response.
        responseValueRenderOption: How values are rendered in the response.
    """
    provider = "googlesheets"
    tool_name = "GOOGLESHEETS_SPREADSHEETS_VALUES_APPEND"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "spreadsheetId": spreadsheetId,
            "range": range,
            "valueInputOption": valueInputOption,
            "values": values,
            "includeValuesInResponse": includeValuesInResponse,
            "insertDataOption": insertDataOption,
            "majorDimension": majorDimension,
            "responseDateTimeRenderOption": responseDateTimeRenderOption,
            "responseValueRenderOption": responseValueRenderOption,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)


googlesheets_spreadsheets_values_append.__tb_output_schema__ = {
  "properties": {
    "data": {
      "additionalProperties": False,
      "description": "Data from the action execution",
      "properties": {
        "spreadsheetId": {
          "description": "The ID of the spreadsheet to which values were appended.",
          "title": "Spreadsheet Id",
          "type": "string"
        },
        "tableRange": {
          "default": None,
          "description": "The A1-notation range of the table that values were appended to (before the append), for example 'Sheet1!A1:D10'. Empty if no table was found. This field may be omitted if no table range is detected.",
          "nullable": True,
          "title": "Table Range",
          "type": "string"
        },
        "updates": {
          "additionalProperties": False,
          "description": "Information about the updates that were applied (UpdateValuesResponse).",
          "properties": {
            "spreadsheetId": {
              "description": "The ID of the spreadsheet where the update occurred (typically the same as the top-level spreadsheetId).",
              "title": "Spreadsheet Id",
              "type": "string"
            },
            "updatedCells": {
              "default": None,
              "description": "The total number of cells updated. May be omitted if not returned by the API.",
              "nullable": True,
              "title": "Updated Cells",
              "type": "integer"
            },
            "updatedColumns": {
              "default": None,
              "description": "The number of columns in the updated range that changed (columns where at least one cell was updated). May be omitted if not returned by the API.",
              "nullable": True,
              "title": "Updated Columns",
              "type": "integer"
            },
            "updatedData": {
              "additionalProperties": False,
              "default": None,
              "description": "Response ValueRange for updatedData in UpdateValuesResponse.\nSeparate from request ValueRange to enforce required fields per API docs:\nrange, majorDimension, and values are required when returned.",
              "nullable": True,
              "properties": {
                "majorDimension": {
                  "description": "The major dimension of the values. ROWS means each inner array represents a row; COLUMNS means each inner array represents a column.",
                  "enum": [
                    "ROWS",
                    "COLUMNS"
                  ],
                  "title": "Major Dimension",
                  "type": "string"
                },
                "range": {
                  "description": "The A1-notation range that the returned values cover.",
                  "title": "Range",
                  "type": "string"
                },
                "values": {
                  "description": "The values in the range. The outer array corresponds to majorDimension; each inner array contains cell values. In responses, trailing empty rows or columns are omitted. Cell values may be strings, numbers, booleans, or null depending on render options.",
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
                  "title": "Values",
                  "type": "array"
                }
              },
              "required": [
                "range",
                "majorDimension",
                "values"
              ],
              "title": "UpdatedDataValueRange",
              "type": "object"
            },
            "updatedRange": {
              "description": "The A1-notation of the range that was updated (e.g., 'Sheet1!A11:D11').",
              "title": "Updated Range",
              "type": "string"
            },
            "updatedRows": {
              "default": None,
              "description": "The number of rows in the updated range that changed (rows where at least one cell was updated). May be omitted if not returned by the API.",
              "nullable": True,
              "title": "Updated Rows",
              "type": "integer"
            }
          },
          "required": [
            "spreadsheetId",
            "updatedRange"
          ],
          "title": "Updates",
          "type": "object"
        }
      },
      "required": [
        "spreadsheetId",
        "updates"
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
  "title": "SpreadsheetsValuesAppendResponseWrapper",
  "type": "object"
}


def googlesheets_find_worksheet_by_title(
    context: "AgentContext",
    spreadsheet_id: str,
    title: str,
) -> ToolInvocationResult:
    """
    Find a worksheet (tab) in a spreadsheet by exact title.

    Args:
        spreadsheet_id: Spreadsheet ID (from URL).
        title: Exact, case-sensitive worksheet title to find.
    """
    provider = "googlesheets"
    tool_name = "GOOGLESHEETS_FIND_WORKSHEET_BY_TITLE"
    ensure_authorized(context, provider)
    payload = _clean_payload({"spreadsheet_id": spreadsheet_id, "title": title})
    return _invoke_mcp_tool(context, provider, tool_name, payload)


googlesheets_find_worksheet_by_title.__tb_output_schema__ = {
  "properties": {
    "data": {
      "additionalProperties": False,
      "description": "Data from the action execution",
      "properties": {
        "found": {
          "description": "True if a worksheet with the exact specified title was found within the spreadsheet; False otherwise.",
          "title": "Found",
          "type": "boolean"
        },
        "sheet_data": {
          "additionalProperties": True,
          "description": "Complete Spreadsheet metadata as returned by Google Sheets API v4 (Spreadsheet resource), including properties, sheets (with their properties), named ranges, developer metadata, and more. Provided regardless of whether the target worksheet is found.",
          "title": "Sheet Data",
          "type": "object"
        }
      },
      "required": [
        "found",
        "sheet_data"
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
  "title": "FindWorksheetByTitleResponseWrapper",
  "type": "object"
}


def googlesheets_add_sheet(
    context: "AgentContext",
    spreadsheetId: str,
    properties: dict | None = None,
) -> ToolInvocationResult:
    """
    Add a new sheet to a Google Spreadsheet.

    Args:
        spreadsheetId: ID of the spreadsheet to update.
        properties: Optional sheet properties; omit to use defaults.
    """
    provider = "googlesheets"
    tool_name = "GOOGLESHEETS_ADD_SHEET"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "spreadsheetId": spreadsheetId,
            "properties": properties,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)


googlesheets_add_sheet.__tb_output_schema__ = {
  "properties": {
    "data": {
      "additionalProperties": False,
      "description": "Data from the action execution",
      "properties": {
        "replies": {
          "description": "A list of replies to the batch update. For AddSheet, it contains the properties of the new sheet.",
          "items": {
            "properties": {
              "addSheet": {
                "additionalProperties": False,
                "properties": {
                  "dataSourceSheetProperties": {
                    "additionalProperties": True,
                    "default": None,
                    "description": "Additional properties for a DATA_SOURCE sheet. Output-only; present only when sheetType is DATA_SOURCE.",
                    "nullable": True,
                    "title": "Data Source Sheet Properties",
                    "type": "object"
                  },
                  "gridProperties": {
                    "additionalProperties": False,
                    "default": None,
                    "nullable": True,
                    "properties": {
                      "columnCount": {
                        "default": None,
                        "description": "The number of columns in the sheet.",
                        "minimum": 0,
                        "nullable": True,
                        "title": "Column Count",
                        "type": "integer"
                      },
                      "columnGroupControlAfter": {
                        "default": None,
                        "description": "True if the column group control toggle is shown after the group, false if before.",
                        "nullable": True,
                        "title": "Column Group Control After",
                        "type": "boolean"
                      },
                      "frozenColumnCount": {
                        "default": None,
                        "description": "The number of columns that are frozen in the sheet.",
                        "minimum": 0,
                        "nullable": True,
                        "title": "Frozen Column Count",
                        "type": "integer"
                      },
                      "frozenRowCount": {
                        "default": None,
                        "description": "The number of rows that are frozen in the sheet.",
                        "minimum": 0,
                        "nullable": True,
                        "title": "Frozen Row Count",
                        "type": "integer"
                      },
                      "hideGridlines": {
                        "default": None,
                        "description": "True if the gridlines are hidden, false if they are shown.",
                        "nullable": True,
                        "title": "Hide Gridlines",
                        "type": "boolean"
                      },
                      "rowCount": {
                        "default": None,
                        "description": "The number of rows in the sheet.",
                        "minimum": 0,
                        "nullable": True,
                        "title": "Row Count",
                        "type": "integer"
                      },
                      "rowGroupControlAfter": {
                        "default": None,
                        "description": "True if the row group control toggle is shown after the group, false if before.",
                        "nullable": True,
                        "title": "Row Group Control After",
                        "type": "boolean"
                      }
                    },
                    "title": "GridProperties",
                    "type": "object"
                  },
                  "hidden": {
                    "default": None,
                    "nullable": True,
                    "title": "Hidden",
                    "type": "boolean"
                  },
                  "index": {
                    "title": "Index",
                    "type": "integer"
                  },
                  "rightToLeft": {
                    "default": None,
                    "nullable": True,
                    "title": "Right To Left",
                    "type": "boolean"
                  },
                  "sheetId": {
                    "title": "Sheet Id",
                    "type": "integer"
                  },
                  "sheetType": {
                    "enum": [
                      "GRID",
                      "OBJECT",
                      "DATA_SOURCE"
                    ],
                    "title": "Sheet Type",
                    "type": "string"
                  },
                  "tabColor": {
                    "additionalProperties": False,
                    "default": None,
                    "nullable": True,
                    "properties": {
                      "alpha": {
                        "default": None,
                        "description": "The fraction of this color that should be applied to the pixel. E.g. 0.5 for 50% transparent.",
                        "maximum": 1,
                        "minimum": 0,
                        "nullable": True,
                        "title": "Alpha",
                        "type": "number"
                      },
                      "blue": {
                        "default": None,
                        "description": "The amount of blue in the color as a value in the interval [0, 1].",
                        "maximum": 1,
                        "minimum": 0,
                        "nullable": True,
                        "title": "Blue",
                        "type": "number"
                      },
                      "green": {
                        "default": None,
                        "description": "The amount of green in the color as a value in the interval [0, 1].",
                        "maximum": 1,
                        "minimum": 0,
                        "nullable": True,
                        "title": "Green",
                        "type": "number"
                      },
                      "red": {
                        "default": None,
                        "description": "The amount of red in the color as a value in the interval [0, 1].",
                        "maximum": 1,
                        "minimum": 0,
                        "nullable": True,
                        "title": "Red",
                        "type": "number"
                      }
                    },
                    "title": "Color",
                    "type": "object"
                  },
                  "tabColorStyle": {
                    "additionalProperties": False,
                    "default": None,
                    "nullable": True,
                    "properties": {
                      "rgbColor": {
                        "additionalProperties": False,
                        "default": None,
                        "description": "RGB color. Specify EITHER rgbColor OR themeColor, but not both. If using rgbColor, provide values for red, green, blue (0.0-1.0).",
                        "nullable": True,
                        "properties": {
                          "alpha": {
                            "default": None,
                            "description": "The fraction of this color that should be applied to the pixel. E.g. 0.5 for 50% transparent.",
                            "maximum": 1,
                            "minimum": 0,
                            "nullable": True,
                            "title": "Alpha",
                            "type": "number"
                          },
                          "blue": {
                            "default": None,
                            "description": "The amount of blue in the color as a value in the interval [0, 1].",
                            "maximum": 1,
                            "minimum": 0,
                            "nullable": True,
                            "title": "Blue",
                            "type": "number"
                          },
                          "green": {
                            "default": None,
                            "description": "The amount of green in the color as a value in the interval [0, 1].",
                            "maximum": 1,
                            "minimum": 0,
                            "nullable": True,
                            "title": "Green",
                            "type": "number"
                          },
                          "red": {
                            "default": None,
                            "description": "The amount of red in the color as a value in the interval [0, 1].",
                            "maximum": 1,
                            "minimum": 0,
                            "nullable": True,
                            "title": "Red",
                            "type": "number"
                          }
                        },
                        "title": "Color",
                        "type": "object"
                      },
                      "themeColor": {
                        "default": None,
                        "description": "Theme color. Specify EITHER themeColor OR rgbColor, but not both. Use predefined theme colors like ACCENT1, TEXT, BACKGROUND, etc.",
                        "enum": [
                          "THEME_COLOR_TYPE_UNSPECIFIED",
                          "TEXT",
                          "BACKGROUND",
                          "ACCENT1",
                          "ACCENT2",
                          "ACCENT3",
                          "ACCENT4",
                          "ACCENT5",
                          "ACCENT6",
                          "LINK"
                        ],
                        "nullable": True,
                        "title": "ThemeColorType",
                        "type": "string"
                      }
                    },
                    "title": "ColorStyle",
                    "type": "object"
                  },
                  "title": {
                    "title": "Title",
                    "type": "string"
                  }
                },
                "required": [
                  "sheetId",
                  "title",
                  "index",
                  "sheetType"
                ],
                "title": "Add Sheet",
                "type": "object"
              }
            },
            "required": [
              "addSheet"
            ],
            "title": "AddSheetReply",
            "type": "object"
          },
          "title": "Replies",
          "type": "array"
        },
        "spreadsheetId": {
          "description": "The ID of the spreadsheet the sheet was added to.",
          "title": "Spreadsheet Id",
          "type": "string"
        }
      },
      "required": [
        "spreadsheetId",
        "replies"
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
  "title": "AddSheetResponseWrapper",
  "type": "object"
}
