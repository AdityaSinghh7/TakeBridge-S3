from __future__ import annotations

from typing import TYPE_CHECKING, List

from mcp_agent.types import ToolInvocationResult

from ._common import _clean_payload, _invoke_mcp_tool, ensure_authorized

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext


def intercom_reply_to_conversation(
    context: "AgentContext",
    admin_id: str,
    conversation_id: str,
    message_body: str,
    attachment_urls: List[str] | None = None,
    message_type: str = "comment",
) -> ToolInvocationResult:
    """
    Send a reply to an existing Intercom conversation.

    Args:
        admin_id: Intercom admin ID sending the reply.
        conversation_id: Conversation identifier.
        message_body: Reply text.
        attachment_urls: Optional attachment URLs.
        message_type: Message type (default comment).
    """
    provider = "intercom"
    tool_name = "INTERCOM_REPLY_TO_CONVERSATION"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "admin_id": admin_id,
            "conversation_id": conversation_id,
            "message_body": message_body,
            "attachment_urls": attachment_urls,
            "message_type": message_type,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)
