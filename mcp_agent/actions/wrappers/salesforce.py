from __future__ import annotations

from typing import TYPE_CHECKING

from mcp_agent.types import ToolInvocationResult

from ._common import _clean_payload, _invoke_mcp_tool, ensure_authorized

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext


def salesforce_update_opportunity(
    context: "AgentContext",
    opportunity_id: str,
    account_id: str | None = None,
    amount: float | None = -1,
    close_date: str | None = None,
    contact_id: str | None = None,
    description: str | None = None,
    lead_source: str | None = None,
    name: str | None = None,
    next_step: str | None = None,
    probability: float | None = -1,
    stage_name: str | None = None,
    type: str | None = None,
) -> ToolInvocationResult:
    """
    Update an existing Salesforce opportunity with provided fields.
    """
    provider = "salesforce"
    tool_name = "SALESFORCE_UPDATE_OPPORTUNITY"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "opportunity_id": opportunity_id,
            "account_id": account_id,
            "amount": amount,
            "close_date": close_date,
            "contact_id": contact_id,
            "description": description,
            "lead_source": lead_source,
            "name": name,
            "next_step": next_step,
            "probability": probability,
            "stage_name": stage_name,
            "type": type,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)
