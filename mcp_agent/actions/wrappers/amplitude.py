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
