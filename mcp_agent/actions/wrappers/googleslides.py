from __future__ import annotations

from typing import TYPE_CHECKING

from mcp_agent.types import ToolInvocationResult

from ._common import _clean_payload, _invoke_mcp_tool, ensure_authorized

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext


def googleslides_create_slides_markdown(
    context: "AgentContext",
    markdown_text: str,
    title: str,
) -> ToolInvocationResult:
    """
    Create a Google Slides presentation from Markdown text.

    Args:
        markdown_text: Markdown content to convert.
        title: Presentation title.
    """
    provider = "googleslides"
    tool_name = "GOOGLESLIDES_CREATE_SLIDES_MARKDOWN"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "markdown_text": markdown_text,
            "title": title,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)

googleslides_create_slides_markdown.__tb_output_schema__ = {
  "properties": {
    "data": {
      "additionalProperties": False,
      "description": "Data from the action execution",
      "properties": {
        "presentation_id": {
          "description": "The unique identifier of the newly created Google Slides presentation.",
          "title": "Presentation Id",
          "type": "string"
        },
        "request_data": {
          "description": "Google Slides API request objects generated from markdown_text for batchUpdate.",
          "items": {
            "additionalProperties": True,
            "properties": {},
            "type": "object"
          },
          "title": "Request Data",
          "type": "array"
        },
        "slide_count": {
          "description": "The number of slides created in the presentation.",
          "title": "Slide Count",
          "type": "integer"
        }
      },
      "required": [
        "presentation_id",
        "slide_count"
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
  "title": "CreateSlidesMarkdownResponseWrapper",
  "type": "object"
}