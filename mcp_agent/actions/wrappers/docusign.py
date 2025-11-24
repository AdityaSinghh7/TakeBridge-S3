from __future__ import annotations

from typing import TYPE_CHECKING

from mcp_agent.types import ToolInvocationResult

from ._common import _clean_payload, _invoke_mcp_tool, ensure_authorized

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext


def docusign_send_envelope(
    context: "AgentContext",
    account_id: str,
    envelope_id: str,
    status: str = "sent",
) -> ToolInvocationResult:
    """
    Send a draft DocuSign envelope by updating its status to 'sent'.

    Args:
        account_id: DocuSign account ID.
        envelope_id: Envelope ID.
        status: Desired status (default 'sent').
    """
    provider = "docusign"
    tool_name = "DOCUSIGN_SEND_ENVELOPE"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "account_id": account_id,
            "envelope_id": envelope_id,
            "status": status,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)
