from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

from mcp_agent.types import ToolInvocationResult

from ._common import _clean_payload, _invoke_mcp_tool, ensure_authorized

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext


def gorgias_update_ticket(
    context: "AgentContext",
    ticket_id: int,
    assignee_team_id: int | None = None,
    assignee_user_id: int | None = None,
    customer_id: int | None = None,
    external_id: str | None = None,
    language: str | None = None,
    meta: Dict[str, Any] | None = None,
    priority: str | None = None,
    status: str | None = None,
    subject: str | None = None,
) -> ToolInvocationResult:
    """
    Update an existing Gorgias ticket.

    Args:
        ticket_id: Ticket ID to update.
        assignee_team_id: Team assignment.
        assignee_user_id: User assignment.
        customer_id: Customer ID.
        external_id: External identifier.
        language: Ticket language.
        meta: Metadata object.
        priority: Ticket priority.
        status: Ticket status.
        subject: Ticket subject.
    """
    provider = "gorgias"
    tool_name = "GORGIAS_UPDATE_TICKET"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "ticket_id": ticket_id,
            "assignee_team_id": assignee_team_id,
            "assignee_user_id": assignee_user_id,
            "customer_id": customer_id,
            "external_id": external_id,
            "language": language,
            "meta": meta,
            "priority": priority,
            "status": status,
            "subject": subject,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)
