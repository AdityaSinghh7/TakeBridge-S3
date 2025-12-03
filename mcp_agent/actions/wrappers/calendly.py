from __future__ import annotations

from typing import TYPE_CHECKING

from mcp_agent.types import ToolInvocationResult

from ._common import _clean_payload, _invoke_mcp_tool, ensure_authorized

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext


def calendly_create_scheduling_link(
    context: "AgentContext",
    owner: str,
    max_event_count: int = 1,
    owner_type: str = "EventType",
) -> ToolInvocationResult:
    """
    Create a single-use scheduling link in Calendly.

    Args:
        owner: Owner resource URI.
        max_event_count: Maximum event count (default 1).
        owner_type: Owner type (default EventType).
    """
    provider = "calendly"
    tool_name = "CALENDLY_CREATE_SCHEDULING_LINK"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "owner": owner,
            "max_event_count": max_event_count,
            "owner_type": owner_type,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)

calendly_create_scheduling_link.__tb_output_schema__ = {
  "properties": {
    "data": {
      "additionalProperties": True,
      "description": "Scheduling link resource containing the generated booking link",
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
  "title": "CreateSchedulingLinkResponseWrapper",
  "type": "object"
}
