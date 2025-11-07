import json
from typing import Any, Iterable

from .registry import init_registry, is_registered
from .oauth import OAuthManager
from .mcp_agent import MCPAgent
from framework.utils.streaming import emit_event
from framework.grounding.grounding_agent import ACI
init_registry()

def _sleep_snippet(sec: float = 0.5) -> str:
    return f"import time; time.sleep({sec})"

def mcp_action(func):
    func.is_mcp_action = True
    return func

def _serialize_structured_param(value: Any) -> str | None:
    """Return a JSON string for dict/list inputs while accepting pre-serialized strings."""
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Structured Slack parameters must be JSON-serializable.") from exc


def _norm_string_list(value: Any) -> list[str]:
    """Normalize iterable/string inputs into a list of trimmed strings."""
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return [p.strip() for p in value.replace(";", ",").split(",") if p.strip()]
    if isinstance(value, Iterable):
        items = []
        for item in value:
            if isinstance(item, str):
                trimmed = item.strip()
                if trimmed:
                    items.append(trimmed)
        return items
    return []

@mcp_action
def slack_post_message(
    self,
    channel: str,
    text: str = "",
    *,
    markdown_text: str = "",
    blocks: Any | None = None,
    attachments: Any | None = None,
    thread_ts: str | None = None,
    reply_broadcast: bool | None = None,
    as_user: bool | None = None,
    username: str | None = None,
    icon_emoji: str | None = None,
    icon_url: str | None = None,
    link_names: bool | None = None,
    parse: str | None = None,
    mrkdwn: bool | None = None,
    unfurl_links: bool | None = None,
    unfurl_media: bool | None = None,
):
    """
    Description:
        Posts a message to a Slack channel, direct message, or private group; requires content via `text`, `blocks`, or `attachments`.
    Args:
        channel: Required channel ID or name (e.g., '#ops').
        text: Optional plain-text body for the message.
        markdown_text: Optional markdown-formatted body (`markdown_text` field).
        blocks: Optional Block Kit payload as JSON string or serializable object.
        attachments: Optional legacy attachments JSON string or serializable object.
        thread_ts: Optional parent message timestamp for threaded replies.
        reply_broadcast: Optional flag to broadcast the thread reply back to the channel.
        as_user: Optional flag to post as the authenticated Slack user.
        username: Optional bot username override (requires `as_user=False`).
        icon_emoji: Optional emoji icon string (e.g., ':robot_face:').
        icon_url: Optional image URL to use as the icon.
        link_names: Optional flag to expand channel/user mentions in `text`.
        parse: Optional Slack parse mode ('none' or 'full').
        mrkdwn: Optional flag to enable markdown parsing within blocks.
        unfurl_links: Optional flag to unfurl links contained in attachments.
        unfurl_media: Optional flag to unfurl media content contained in attachments.
    """
    if getattr(self, "_validation_only", False):
        return _sleep_snippet(0.0)
    if not OAuthManager.is_authorized("slack"):
        emit_event("mcp.call.skipped", {"server": "slack", "reason": "unauthorized"})
        return _sleep_snippet(0.2)

    content_provided = any([text, markdown_text, blocks, attachments])
    if not content_provided:
        raise ValueError("Slack send message requires at least one of text, markdown_text, blocks, or attachments.")

    payload: dict[str, Any] = {"channel": channel}
    if text:
        payload["text"] = text
    if markdown_text:
        payload["markdown_text"] = markdown_text
    blocks_payload = _serialize_structured_param(blocks)
    if blocks_payload:
        payload["blocks"] = blocks_payload
    attachments_payload = _serialize_structured_param(attachments)
    if attachments_payload:
        payload["attachments"] = attachments_payload

    if thread_ts:
        payload["thread_ts"] = thread_ts
    if reply_broadcast is not None:
        payload["reply_broadcast"] = bool(reply_broadcast)
    if as_user is not None:
        payload["as_user"] = bool(as_user)
    if username:
        payload["username"] = username
    if icon_emoji:
        payload["icon_emoji"] = icon_emoji
    if icon_url:
        payload["icon_url"] = icon_url
    if link_names is not None:
        payload["link_names"] = bool(link_names)
    if parse:
        payload["parse"] = parse
    if mrkdwn is not None:
        payload["mrkdwn"] = bool(mrkdwn)
    if unfurl_links is not None:
        payload["unfurl_links"] = bool(unfurl_links)
    if unfurl_media is not None:
        payload["unfurl_media"] = bool(unfurl_media)

    try:
        MCPAgent.current().call_tool("slack", "SLACK_SEND_MESSAGE", payload)
    except RuntimeError:
        return _sleep_snippet(0.2)
    return _sleep_snippet(0.2)

@mcp_action
def slack_search_messages(
    self,
    query: str,
    *,
    count: int = 20,
    page: int | None = None,
    sort: str | None = None,
    sort_dir: str | None = None,
    highlight: bool | None = None,
    auto_paginate: bool | None = None,
):
    """
    Description:
        Workspace-wide Slack message search with query modifiers (e.g., `in:#channel`, `from:@user`, `before:YYYY-MM-DD`) plus pagination and sorting controls.
    Args:
        query: Required Slack search query string.
        count: Optional number of results per page (defaults to 20, Slack default 1).
        page: Optional page index for paginated results.
        sort: Optional sort field ('score' or 'timestamp').
        sort_dir: Optional direction ('asc' or 'desc').
        highlight: Optional flag to return highlighted contexts.
        auto_paginate: Optional flag to iterate through all result pages.
    """
    if getattr(self, "_validation_only", False):
        return _sleep_snippet(0.0)
    if not OAuthManager.is_authorized("slack"):
        emit_event("mcp.call.skipped", {"server": "slack", "reason": "unauthorized"})
        return _sleep_snippet(0.2)

    payload: dict[str, Any] = {"query": query}
    if count is not None:
        payload["count"] = count
    if page is not None:
        payload["page"] = page
    if sort:
        payload["sort"] = sort
    if sort_dir:
        payload["sort_dir"] = sort_dir
    if highlight is not None:
        payload["highlight"] = bool(highlight)
    if auto_paginate is not None:
        payload["auto_paginate"] = bool(auto_paginate)

    try:
        MCPAgent.current().call_tool("slack", "SLACK_SEARCH_MESSAGES", payload)
    except RuntimeError:
        return _sleep_snippet(0.2)
    return _sleep_snippet(0.2)

def _norm_recipients(x):
    if x is None or x == "":
        return []
    if isinstance(x, list):
        return [s.strip() for s in x if isinstance(s, str) and s.strip()]
    if isinstance(x, str):
        return [p.strip() for p in x.replace(";", ",").split(",") if p.strip()]
    return []

def _primary_plus_rest(x):
    lst = _norm_recipients(x)
    if not lst:
        return "", []
    return lst[0], lst[1:]

@mcp_action
def gmail_send_email(
    self,
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    bcc: str = "",
    thread_id: str = "",
    is_html: bool = False,
):
    """
    Description:
        Sends an email via Gmail API using the authenticated user's Google profile display name. At least one of recipient_email, cc, or bcc must be provided. Atleast one of subject or body must be provided. Requires `is_html=True` if the body contains HTML and valid `s3key`, `mimetype`, `name` for any attachment.
    Args:
        to: Comma-separated recipients.
        subject: Subject line text.
        body: Plain text or simple HTML body.
        cc: Optional comma-separated CC recipients.
        bcc: Optional comma-separated BCC recipients.
        thread_id: Optional Gmail thread to reply into.
        is_html: Optional boolean indicating if the body contains HTML.
    """
    if getattr(self, "_validation_only", False):
        return _sleep_snippet(0.0)
    if not OAuthManager.is_authorized("gmail"):
        emit_event("mcp.call.skipped", {"server":"gmail","reason":"unauthorized"})
        return _sleep_snippet(0.2)
    primary, extra_tos = _primary_plus_rest(to)
    cc_list = _norm_recipients(cc) + extra_tos
    bcc_list = _norm_recipients(bcc)

    args = {
        # Composio expects 'recipient_email' as a single string
        "recipient_email": primary,
        "subject": subject,
        "body": body,
        "cc": cc_list,
        "bcc": bcc_list,
        "is_html": bool(is_html),
    }
    if thread_id:
        args["thread_id"] = thread_id
    # Composio tool name is provider-prefixed
    try:
        MCPAgent.current().call_tool("gmail", "GMAIL_SEND_EMAIL", args)
    except RuntimeError:
        return _sleep_snippet(0.2)
    return _sleep_snippet(0.2)

@mcp_action
def gmail_search(
    self,
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
):
    """
    Description:
        Fetches a list of email messages from a Gmail account, supporting filtering, pagination, and optional full content retrieval.
    Args:
        query: Required Gmail search query (e.g., 'from:alice has:attachment').
        max_results: Optional maximum number of results to return (defaults to 20, API default 1).
        label_ids: Optional comma-separated string or iterable of label IDs to include.
        page_token: Optional pagination token from a previous response.
        include_payload: Optional flag to return full MIME payloads.
        include_spam_trash: Optional flag to include spam and trash.
        ids_only: Optional flag to return only message ids/snippets.
        verbose: Optional flag for verbose response metadata.
        user_id: Optional Gmail user identifier (defaults to 'me').
    """
    if getattr(self, "_validation_only", False):
        return _sleep_snippet(0.0)
    if not OAuthManager.is_authorized("gmail"):
        emit_event("mcp.call.skipped", {"server": "gmail", "reason": "unauthorized"})
        return _sleep_snippet(0.2)

    payload: dict[str, Any] = {
        "query": query,
        "max_results": max_results,
        "user_id": user_id or "me",
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
    if ids_only is not None:
        payload["ids_only"] = bool(ids_only)
    if verbose is not None:
        payload["verbose"] = bool(verbose)

    try:
        MCPAgent.current().call_tool("gmail", "GMAIL_FETCH_EMAILS", payload)
    except RuntimeError:
        return _sleep_snippet(0.2)
    return _sleep_snippet(0.2)

# Register these MCP actions onto the base ACI so Worker can discover
# them when it introspects the grounding agent class/type.
def _provider_actions_map():
    return {
        "slack": (slack_post_message, slack_search_messages),
        "gmail": (gmail_send_email, gmail_search),
    }


def _reset_mcp_actions_on_aci() -> None:
    """Remove all MCP action methods from ACI so we can rebuild accurately."""
    provider_actions = _provider_actions_map()
    for fns in provider_actions.values():
        for fn in fns:
            if hasattr(ACI, fn.__name__):
                try:
                    delattr(ACI, fn.__name__)
                except Exception:
                    pass


def _register_mcp_actions_on_aci() -> None:
    """Register MCP actions only for providers that are OAuth-authorized and registered.

    This prevents unavailable actions from being interpolated into the worker
    system prompt before the user connects providers via OAuth.
    """
    provider_actions = _provider_actions_map()
    for provider, fns in provider_actions.items():
        if not OAuthManager.is_authorized(provider):
            emit_event(
                "mcp.actions.registration.skipped",
                {"server": provider, "reason": "unauthorized"},
            )
            continue
        if not is_registered(provider):
            emit_event(
                "mcp.actions.registration.skipped",
                {"server": provider, "reason": "unconfigured"},
            )
            continue
        for fn in fns:
            setattr(ACI, fn.__name__, fn)
        emit_event(
            "mcp.actions.registration.completed",
            {"server": provider, "actions": [fn.__name__ for fn in fns]},
        )

def register_mcp_actions() -> None:
    """Public, idempotent registration entry point.

    Call this after completing OAuth to expose newly available MCP actions
    to the Worker prompt. Safe to call multiple times.
    """
    _reset_mcp_actions_on_aci()
    _register_mcp_actions_on_aci()

_register_mcp_actions_on_aci()
