from __future__ import annotations

from typing import Any

from ...client import ToolCallResult, call_tool, sanitize_payload, serialize_structured_param

"""
Posts a message to a Slack channel, direct message, or private group; requires content via `text`, `blocks`, or `attachments`.

Provider: Slack
Tool: SLACK_SEND_MESSAGE

Args:
    channel (str): Required channel ID or name (e.g., '#ops').
    text (str): Optional plain-text body for the message.
    markdown_text (str): Optional markdown-formatted body (`markdown_text` field).
    blocks (Any | None): Optional Block Kit payload as JSON string or serializable object.
    attachments (Any | None): Optional legacy attachments JSON string or serializable object.
    thread_ts (str | None): Optional parent message timestamp for threaded replies.
    reply_broadcast (bool | None): Optional flag to broadcast the thread reply back to the channel.
    as_user (bool | None): Optional flag to post as the authenticated Slack user.
    username (str | None): Optional bot username override (requires `as_user=False`).
    icon_emoji (str | None): Optional emoji icon string (e.g., ':robot_face:').
    icon_url (str | None): Optional image URL to use as the icon.
    link_names (bool | None): Optional flag to expand channel/user mentions in `text`.
    parse (str | None): Optional Slack parse mode ('none' or 'full').
    mrkdwn (bool | None): Optional flag to enable markdown parsing within blocks.
    unfurl_links (bool | None): Optional flag to unfurl links contained in attachments.
    unfurl_media (bool | None): Optional flag to unfurl media content contained in attachments.
"""
async def slack_post_message(channel: str, text: str = '', *, markdown_text: str = '', blocks: Any | None = None, attachments: Any | None = None, thread_ts: str | None = None, reply_broadcast: bool | None = None, as_user: bool | None = None, username: str | None = None, icon_emoji: str | None = None, icon_url: str | None = None, link_names: bool | None = None, parse: str | None = None, mrkdwn: bool | None = None, unfurl_links: bool | None = None, unfurl_media: bool | None = None) -> ToolCallResult[Any]:
    payload: dict[str, Any] = {}
    payload["channel"] = channel
    if text is not None:
        payload["text"] = text
    if markdown_text is not None:
        payload["markdown_text"] = markdown_text
    blocks_serialized = serialize_structured_param(blocks)
    if blocks_serialized is not None:
        payload["blocks"] = blocks_serialized
    attachments_serialized = serialize_structured_param(attachments)
    if attachments_serialized is not None:
        payload["attachments"] = attachments_serialized
    if thread_ts is not None:
        payload["thread_ts"] = thread_ts
    if reply_broadcast is not None:
        payload["reply_broadcast"] = bool(reply_broadcast)
    if as_user is not None:
        payload["as_user"] = bool(as_user)
    if username is not None:
        payload["username"] = username
    if icon_emoji is not None:
        payload["icon_emoji"] = icon_emoji
    if icon_url is not None:
        payload["icon_url"] = icon_url
    if link_names is not None:
        payload["link_names"] = bool(link_names)
    if parse is not None:
        payload["parse"] = parse
    if mrkdwn is not None:
        payload["mrkdwn"] = bool(mrkdwn)
    if unfurl_links is not None:
        payload["unfurl_links"] = bool(unfurl_links)
    if unfurl_media is not None:
        payload["unfurl_media"] = bool(unfurl_media)
    sanitize_payload(payload)
    return await call_tool('slack', 'SLACK_SEND_MESSAGE', payload)

slackPostMessage = slack_post_message
