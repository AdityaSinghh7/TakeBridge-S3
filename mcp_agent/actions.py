import inspect
import json
import os
from typing import Any, Callable, Iterable, Tuple, cast

from .registry import init_registry, is_registered
from .oauth import OAuthManager
from .mcp_agent import MCPAgent
from .types import ToolInvocationResult
from shared.streaming import emit_event
init_registry()

SUPPORTED_PROVIDERS: tuple[str, ...] = ("slack", "gmail")

_ALLOWED_PROVIDERS: set[str] | None = None
_ALLOWED_TOOLS: set[str] | None = None

def _payload_key_list(payload: dict[str, Any] | None) -> list[str]:
    if not payload:
        return []
    return sorted(str(key) for key in payload.keys())


def _current_user_id() -> str:
    return (os.getenv("TB_USER_ID") or "singleton").strip() or "singleton"


def _structured_result(
    provider: str,
    tool: str,
    *,
    successful: bool,
    error: str | None = None,
    data: Any = None,
    logs: Any = None,
    payload_keys: Iterable[str] | None = None,
) -> ToolInvocationResult:
    keys = sorted([str(key) for key in payload_keys] if payload_keys else [])
    return cast(
        ToolInvocationResult,
        {
            "successful": bool(successful),
            "error": error,
            "data": data,
            "logs": logs,
            "provider": provider,
            "tool": tool,
            "payload_keys": keys,
        },
    )


def _normalize_tool_response(
    provider: str,
    tool: str,
    payload_keys: list[str],
    response: dict[str, Any] | None,
) -> ToolInvocationResult:
    normalized: dict[str, Any] = dict(response or {})
    success = normalized.get("successful")
    if success is None:
        success = normalized.get("successfull")
    if success is None and "error" in normalized:
        success = normalized["error"] in (None, "", False)
    if success is None:
        success = True
    normalized["successful"] = bool(success)
    normalized.setdefault("error", normalized.get("error"))
    normalized.setdefault("data", normalized.get("data"))
    normalized.setdefault("logs", normalized.get("logs"))
    normalized["provider"] = provider
    normalized["tool"] = tool
    normalized["payload_keys"] = payload_keys
    return cast(ToolInvocationResult, normalized)

def _emit_action_event(
    event: str,
    provider: str,
    tool: str,
    *,
    payload: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
    user_id: str | None = None,
) -> None:
    """Emit telemetry for wrapper activity while redacting payload details."""
    data: dict[str, Any] = {"server": provider, "tool": tool}
    if payload:
        data["payload_keys"] = sorted(payload.keys())
    if extra:
        data.update(extra)
    if user_id:
        data["user_id"] = user_id
    emit_event(event, data)

def _invoke_mcp_tool(provider: str, tool: str, payload: dict[str, Any]) -> ToolInvocationResult:
    """Call an MCP tool via MCPAgent and return a normalized result dict."""
    payload_keys = _payload_key_list(payload)
    user_id = _current_user_id()
    _emit_action_event("mcp.action.started", provider, tool, payload=payload, user_id=user_id)
    try:
        response = MCPAgent.current(user_id).call_tool(provider, tool, payload)
    except Exception as exc:
        error_message = str(exc)
        _emit_action_event(
            "mcp.action.failed",
            provider,
            tool,
            extra={"error": error_message},
            user_id=user_id,
        )
        return _structured_result(
            provider,
            tool,
            successful=False,
            error=error_message,
            payload_keys=payload_keys,
        )
    _emit_action_event("mcp.action.completed", provider, tool, user_id=user_id)
    return _normalize_tool_response(provider, tool, payload_keys, response)

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
    tool_name = "SLACK_SEND_MESSAGE"
    user_id = _current_user_id()
    if getattr(self, "_validation_only", False):
        return _structured_result(
            "slack",
            tool_name,
            successful=True,
            data={"skipped": "validation_only"},
            payload_keys=[],
        )
    if not OAuthManager.is_authorized("slack", user_id=user_id):
        emit_event(
            "mcp.call.skipped",
            {"server": "slack", "tool": tool_name, "reason": "unauthorized", "user_id": user_id},
        )
        return _structured_result(
            "slack",
            tool_name,
            successful=False,
            error="unauthorized",
            payload_keys=[],
        )

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

    return _invoke_mcp_tool("slack", tool_name, payload)

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
    tool_name = "SLACK_SEARCH_MESSAGES"
    user_id = _current_user_id()
    if getattr(self, "_validation_only", False):
        return _structured_result(
            "slack",
            tool_name,
            successful=True,
            data={"skipped": "validation_only"},
            payload_keys=[],
        )
    if not OAuthManager.is_authorized("slack", user_id=user_id):
        emit_event(
            "mcp.call.skipped",
            {"server": "slack", "tool": tool_name, "reason": "unauthorized", "user_id": user_id},
        )
        return _structured_result(
            "slack",
            tool_name,
            successful=False,
            error="unauthorized",
            payload_keys=[],
        )

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

    return _invoke_mcp_tool("slack", tool_name, payload)

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
    tool_name = "GMAIL_SEND_EMAIL"
    user_id = _current_user_id()
    if getattr(self, "_validation_only", False):
        return _structured_result(
            "gmail",
            tool_name,
            successful=True,
            data={"skipped": "validation_only"},
            payload_keys=[],
        )
    if not OAuthManager.is_authorized("gmail", user_id=user_id):
        emit_event(
            "mcp.call.skipped",
            {"server": "gmail", "tool": tool_name, "reason": "unauthorized", "user_id": user_id},
        )
        return _structured_result(
            "gmail",
            tool_name,
            successful=False,
            error="unauthorized",
            payload_keys=[],
        )
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
    return _invoke_mcp_tool("gmail", tool_name, args)

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
    tool_name = "GMAIL_FETCH_EMAILS"
    user_id = _current_user_id()
    if getattr(self, "_validation_only", False):
        return _structured_result(
            "gmail",
            tool_name,
            successful=True,
            data={"skipped": "validation_only"},
            payload_keys=[],
        )
    if not OAuthManager.is_authorized("gmail", user_id=user_id):
        emit_event(
            "mcp.call.skipped",
            {"server": "gmail", "tool": tool_name, "reason": "unauthorized", "user_id": user_id},
        )
        return _structured_result(
            "gmail",
            tool_name,
            successful=False,
            error="unauthorized",
            payload_keys=[],
        )

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

    return _invoke_mcp_tool("gmail", tool_name, payload)


PROVIDER_ACTIONS: dict[str, Tuple[Callable[..., Any], ...]] = {
    "slack": (slack_post_message, slack_search_messages),
    "gmail": (gmail_send_email, gmail_search),
}

if set(PROVIDER_ACTIONS) != set(SUPPORTED_PROVIDERS):
    missing = set(SUPPORTED_PROVIDERS) - set(PROVIDER_ACTIONS)
    extra = set(PROVIDER_ACTIONS) - set(SUPPORTED_PROVIDERS)
    raise RuntimeError(
        "Provider inventory mismatch. Missing: "
        f"{sorted(missing)} Extra: {sorted(extra)}"
    )


def _provider_actions_map():
    return PROVIDER_ACTIONS


def get_provider_action_map() -> dict[str, Tuple[Callable[..., Any], ...]]:
    """Return a read-only mapping of provider -> MCP action callables."""
    return {
        provider: tuple(funcs)
        for provider, funcs in _provider_actions_map().items()
    }


def configure_mcp_action_filters(
    providers: Iterable[str] | None = None,
    tools: Iterable[str] | None = None,
) -> None:
    """Limit MCP actions registered on ACI to the provided providers/tools."""
    global _ALLOWED_PROVIDERS, _ALLOWED_TOOLS
    _ALLOWED_PROVIDERS = None
    _ALLOWED_TOOLS = None
    if providers:
        _ALLOWED_PROVIDERS = {p.lower() for p in providers if p}
    if tools:
        _ALLOWED_TOOLS = {t for t in tools if t}


def _provider_allowed(provider: str) -> bool:
    return _ALLOWED_PROVIDERS is None or provider in _ALLOWED_PROVIDERS


def _tool_allowed(tool: str) -> bool:
    return _ALLOWED_TOOLS is None or tool in _ALLOWED_TOOLS


def iter_available_action_functions():
    """Yield (provider, function) pairs for currently available MCP actions."""
    for provider, funcs in _provider_actions_map().items():
        if not _provider_allowed(provider):
            emit_event(
                "mcp.actions.registration.skipped",
                {"server": provider, "reason": "filtered"},
            )
            continue
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
        for fn in funcs:
            if not _tool_allowed(fn.__name__):
                continue
            yield provider, fn


def describe_provider_actions() -> dict[str, dict[str, Any]]:
    """Return structured metadata for available providers and their actions."""
    catalog: dict[str, dict[str, Any]] = {}
    for provider, funcs in _provider_actions_map().items():
        actions: list[dict[str, Any]] = []
        for fn in funcs:
            doc = inspect.getdoc(fn) or ""
            actions.append(
                {
                    "name": fn.__name__,
                    "doc": doc.strip(),
                    "provider": provider,
                }
            )
        catalog[provider] = {"provider": provider, "actions": actions}
    return catalog


def describe_available_actions() -> list[dict[str, Any]]:
    """Return metadata for MCP actions that are currently available."""
    catalog = describe_provider_actions()
    available: list[dict[str, Any]] = []
    allowed_names: dict[str, set[str]] = {}
    for provider, fn in iter_available_action_functions():
        allowed_names.setdefault(provider, set()).add(fn.__name__)
    for provider, names in allowed_names.items():
        provider_info = catalog.get(provider, {})
        for action in provider_info.get("actions", []):
            if action["name"] in names:
                available.append(
                    {
                        "provider": provider,
                        "name": action["name"],
                        "doc": action.get("doc", ""),
                    }
                )
    return available
