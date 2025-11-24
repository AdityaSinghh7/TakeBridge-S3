from __future__ import annotations

from typing import TYPE_CHECKING

from mcp_agent.types import ToolInvocationResult

from ._common import _clean_payload, _invoke_mcp_tool, ensure_authorized

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext


def mailchimp_create_a_survey_campaign(
    context: "AgentContext",
    list_id: str,
    survey_id: str,
) -> ToolInvocationResult:
    """
    Create a Mailchimp survey campaign using a list ID and survey ID.

    Args:
        list_id: Mailchimp list ID.
        survey_id: Survey ID.
    """
    provider = "mailchimp"
    tool_name = "MAILCHIMP_CREATE_A_SURVEY_CAMPAIGN"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "list_id": list_id,
            "survey_id": survey_id,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)
