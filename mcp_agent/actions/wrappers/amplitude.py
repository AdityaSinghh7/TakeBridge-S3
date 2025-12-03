from __future__ import annotations

from typing import TYPE_CHECKING, Any, List

from mcp_agent.types import ToolInvocationResult

from ._common import _clean_payload, _invoke_mcp_tool, ensure_authorized

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext


def amplitude_update_cohort_membership(
    context: "AgentContext",
    cohort_id: str,
    memberships: List[Any],
    count_group: str | None = None,
    skip_invalid_ids: bool = True,
) -> ToolInvocationResult:
    """
    Incrementally update Amplitude cohort membership by adding or removing IDs.

    Args:
        cohort_id: Cohort identifier.
        memberships: Membership operations payload.
        count_group: Optional count group.
        skip_invalid_ids: Whether to skip invalid IDs (default True).
    """
    provider = "amplitude"
    tool_name = "AMPLITUDE_UPDATE_COHORT_MEMBERSHIP"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "cohort_id": cohort_id,
            "memberships": memberships,
            "count_group": count_group,
            "skip_invalid_ids": skip_invalid_ids,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)


amplitude_update_cohort_membership.__tb_output_schema__ = {
  "properties": {
    "data": {
      "additionalProperties": False,
      "description": "Data from the action execution",
      "properties": {
        "cohort_id": {
          "description": "Cohort ID",
          "title": "Cohort Id",
          "type": "string"
        },
        "memberships_result": {
          "description": "Results of membership operations",
          "items": {
            "additionalProperties": True,
            "properties": {},
            "type": "object"
          },
          "title": "Memberships Result",
          "type": "array"
        }
      },
      "required": [
        "cohort_id",
        "memberships_result"
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
  "title": "UpdateCohortMembershipResponseWrapper",
  "type": "object"
}