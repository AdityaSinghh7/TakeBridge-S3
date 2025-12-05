"""Slack action wrappers (extracted from actions.py).

Handles parameter mapping and MCP tool invocation for Slack.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from mcp_agent.types import ToolInvocationResult
from ._common import ensure_authorized, _invoke_mcp_tool

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext
from ..slack_output_helper import slack_post_message_output_schema, slack_search_messages_output_schema

def _serialize_structured_param(value: Any) -> str | None:
    """
    Serialize structured parameters (blocks, attachments) to JSON.
    
    Accepts pre-serialized strings or JSON-serializable objects.
    """
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Structured Slack parameters must be JSON-serializable.") from exc

    
def slack_post_message(
    context: AgentContext,
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
) -> ToolInvocationResult:
    """
    Post a message to Slack.
    
    Args:
        context: Agent context with user_id
        channel: Channel ID or name (e.g., '#ops')
        text: Plain text message body
        markdown_text: Markdown-formatted message body
        blocks: Block Kit payload (JSON string or object)
        attachments: Legacy attachments (JSON string or object)
        thread_ts: Parent message timestamp for threaded replies
        reply_broadcast: Broadcast thread reply to channel
        as_user: Post as authenticated user
        username: Bot username override
        icon_emoji: Emoji icon (e.g., ':robot_face:')
        icon_url: Image URL for icon
        link_names: Expand channel/user mentions
        parse: Slack parse mode ('none' or 'full')
        mrkdwn: Enable markdown parsing in blocks
        unfurl_links: Unfurl links in attachments
        unfurl_media: Unfurl media in attachments
    
    Returns:
        Standardized tool result with ok, channel, ts, message
    """
    tool_name = "SLACK_SEND_MESSAGE"
    ensure_authorized(context, "slack")
    
    # Require at least one content field
    content_provided = any([text, markdown_text, blocks, attachments])
    if not content_provided:
        raise ValueError(
            "Slack send message requires at least one of: text, markdown_text, blocks, or attachments."
        )
    
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
    
    return _invoke_mcp_tool(context, "slack", tool_name, payload)




def slack_search_messages(
    context: AgentContext,
    query: str,
    *,
    count: int = 20,
    page: int | None = None,
    sort: str | None = None,
    sort_dir: str | None = None,
    highlight: bool | None = None,
    auto_paginate: bool | None = None,
) -> ToolInvocationResult:
    """
    Search Slack messages workspace-wide.
    
    Args:
        context: Agent context with user_id
        query: Slack search query (supports modifiers: in:#channel, from:@user, before:YYYY-MM-DD)
        count: Results per page (default 20, Slack default 1)
        page: Page index for pagination
        sort: Sort field ('score' or 'timestamp')
        sort_dir: Sort direction ('asc' or 'desc')
        highlight: Return highlighted contexts
        auto_paginate: Iterate through all result pages
    
    Returns:
        Standardized tool result with matches, query, total, pagination
    """
    tool_name = "SLACK_SEARCH_MESSAGES"
    ensure_authorized(context, "slack")
    
    
    
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
    
    return _invoke_mcp_tool(context, "slack", tool_name, payload)


slack_search_messages.__tb_output_schema__ = slack_search_messages_output_schema
slack_post_message.__tb_output_schema__ = slack_post_message_output_schema
