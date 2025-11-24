from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

from mcp_agent.types import ToolInvocationResult

from ._common import _clean_payload, _invoke_mcp_tool, ensure_authorized

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext


def zendesk_reply_zendesk_ticket(
    context: "AgentContext",
    ticket_id: int,
    body: str = "",
    public: bool = True,
) -> ToolInvocationResult:
    """
    Reply to a Zendesk ticket by adding a comment.

    Args:
        ticket_id: Zendesk ticket ID.
        body: Comment body.
        public: Whether the comment is public.
    """
    provider = "zendesk"
    tool_name = "ZENDESK_REPLY_ZENDESK_TICKET"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "ticket_id": ticket_id,
            "body": body,
            "public": public,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)


def zendesk_update_zendesk_ticket(
    context: "AgentContext",
    ticket_id: int,
    additional_collaborators: List[Any] | None = None,
    collaborator_ids: List[int] | None = None,
    collaborators: List[Any] | None = None,
    comment_author_id: int | None = None,
    comment_body: str | None = None,
    comment_html_body: str | None = None,
    comment_public: bool | None = None,
    comment_uploads: List[Any] | None = None,
    custom_fields: List[Any] | None = None,
    data: Dict[str, Any] | None = None,
    due_at: str | None = None,
    email_ccs: List[Any] | None = None,
    followers: List[Any] | None = None,
    metadata: Dict[str, Any] | None = None,
    priority: str | None = None,
    safe_update: bool | None = None,
    status: str | None = None,
    subject: str | None = None,
    tags: List[Any] | None = None,
    updated_stamp: str | None = None,
) -> ToolInvocationResult:
    """
    Update a Zendesk ticket with new fields or comments.

    Args:
        ticket_id: Zendesk ticket ID to update.
        additional_collaborators: Additional collaborators.
        collaborator_ids: Collaborator IDs.
        collaborators: Collaborator objects.
        comment_author_id: ID for the comment author.
        comment_body: Plain text comment body.
        comment_html_body: HTML comment body.
        comment_public: Whether the comment is public.
        comment_uploads: Upload tokens for attachments.
        custom_fields: Custom fields payload.
        data: Arbitrary data object.
        due_at: Due date.
        email_ccs: Email CCs.
        followers: Followers list.
        metadata: Metadata payload.
        priority: Ticket priority.
        safe_update: Whether to use safe update mode.
        status: Ticket status.
        subject: Ticket subject.
        tags: Tag list.
        updated_stamp: Updated timestamp.
    """
    provider = "zendesk"
    tool_name = "ZENDESK_UPDATE_ZENDESK_TICKET"
    ensure_authorized(context, provider)
    payload = _clean_payload(
        {
            "ticket_id": ticket_id,
            "additional_collaborators": additional_collaborators,
            "collaborator_ids": collaborator_ids,
            "collaborators": collaborators,
            "comment_author_id": comment_author_id,
            "comment_body": comment_body,
            "comment_html_body": comment_html_body,
            "comment_public": comment_public,
            "comment_uploads": comment_uploads,
            "custom_fields": custom_fields,
            "data": data,
            "due_at": due_at,
            "email_ccs": email_ccs,
            "followers": followers,
            "metadata": metadata,
            "priority": priority,
            "safe_update": safe_update,
            "status": status,
            "subject": subject,
            "tags": tags,
            "updated_stamp": updated_stamp,
        }
    )
    return _invoke_mcp_tool(context, provider, tool_name, payload)
