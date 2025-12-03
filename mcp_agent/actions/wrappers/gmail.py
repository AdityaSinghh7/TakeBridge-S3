"""Gmail action wrappers (extracted from actions.py).

Handles parameter mapping and MCP tool invocation for Gmail.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from mcp_agent.types import ToolInvocationResult
from mcp_agent.user_identity import normalize_user_id
from ._common import ensure_authorized, _invoke_mcp_tool

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext


def _norm_recipients(x):
    """Normalize recipient list (string or list) to list of strings."""
    if x is None or x == "":
        return []
    if isinstance(x, list):
        return [s.strip() for s in x if isinstance(s, str) and s.strip()]
    if isinstance(x, str):
        return [p.strip() for p in x.replace(";", ",").split(",") if p.strip()]
    return []


def _primary_plus_rest(x):
    """Extract primary recipient and rest."""
    lst = _norm_recipients(x)
    if not lst:
        return "", []
    return lst[0], lst[1:]


def _norm_string_list(value: Any) -> list[str]:
    """Normalize iterable/string inputs into a list of trimmed strings."""
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return [p.strip() for p in value.replace(";", ",").split(",") if p.strip()]
    if hasattr(value, "__iter__"):
        items = []
        for item in value:
            if isinstance(item, str):
                trimmed = item.strip()
                if trimmed:
                    items.append(trimmed)
        return items
    return []


def _resolve_gmail_user_id(user_id: str | None) -> str:
    """
    Normalize Gmail API userId parameter.
    
    Gmail expects 'me' or a concrete Gmail address.
    TB user ids like 'dev-local' are not valid, so default to 'me'.
    """
    if not user_id:
        return "me"
    tb_user = os.getenv("TB_USER_ID")
    if tb_user and user_id == tb_user:
        return "me"
    return user_id


def gmail_send_email(
    context: AgentContext,
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    bcc: str = "",
    thread_id: str = "",
    is_html: bool = False,
) -> ToolInvocationResult:
    """
    Send an email via Gmail API.
    
    Args:
        context: Agent context with user_id
        to: Comma-separated recipients (first becomes primary)
        subject: Email subject
        body: Email body (plain text or HTML)
        cc: Optional comma-separated CC recipients
        bcc: Optional comma-separated BCC recipients
        thread_id: Optional Gmail thread ID for replies
        is_html: Whether body contains HTML
    
    Returns:
        Standardized tool result with messageId, threadId, etc.
    """
    tool_name = "GMAIL_SEND_EMAIL"
    ensure_authorized(context, "gmail")
    
    # Extract primary recipient and rest
    primary, extra_tos = _primary_plus_rest(to)
    cc_list = _norm_recipients(cc) + extra_tos
    bcc_list = _norm_recipients(bcc)
    
    payload = {
        "recipient_email": primary,  # Composio expects single recipient_email
        "subject": subject,
        "body": body,
        "cc": cc_list,
        "bcc": bcc_list,
        "is_html": bool(is_html),
    }
    if thread_id:
        payload["thread_id"] = thread_id
    
    return _invoke_mcp_tool(context, "gmail", tool_name, payload)


def gmail_search(
    context: AgentContext,
    query: str,
    max_results: int = 20,
    *,
    label_ids: Any | None = None,
    page_token: str | None = None,
    include_payload: bool | None = None,
    include_spam_trash: bool | None = None,
    ids_only: bool | None = None,
    verbose: bool | None = None,
    user_id: str = "me",
) -> ToolInvocationResult:
    """
    Search Gmail messages.
    
    Args:
        context: Agent context
        query: Gmail search query (e.g., 'from:alice has:attachment')
        max_results: Maximum number of results (default 20)
        label_ids: Optional comma-separated label IDs or list
        page_token: Optional pagination token
        include_payload: Optional flag to include full MIME payloads
        include_spam_trash: Optional flag to include spam/trash
        ids_only: Optional flag to return only message IDs
        verbose: Optional flag for verbose metadata
        user_id: Gmail user ID (default 'me')
    
    Returns:
        Standardized tool result with messages array
    """
    tool_name = "GMAIL_FETCH_EMAILS"
    gmail_user_id = _resolve_gmail_user_id(user_id)
    ensure_authorized(context, "gmail")
    
    payload: dict[str, Any] = {
        "query": query,
        "max_results": max_results,
        "user_id": gmail_user_id,
        "ids_only": False if ids_only is None else bool(ids_only),
    }

    norm_labels = _norm_string_list(label_ids)
    if norm_labels:
        payload["label_ids"] = norm_labels
    if page_token:
        payload["page_token"] = page_token
    if include_payload is not None:
        payload["include_payload"] = bool(include_payload)
    if include_spam_trash is not None:
        payload["include_spam_trash"] = bool(include_spam_trash)
    if verbose is not None:
        payload["verbose"] = bool(verbose)
    
    return _invoke_mcp_tool(context, "gmail", tool_name, payload)
