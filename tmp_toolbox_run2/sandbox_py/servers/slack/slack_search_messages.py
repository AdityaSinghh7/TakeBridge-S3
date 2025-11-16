from __future__ import annotations

from typing import Any

from ...client import ToolCallResult, call_tool, sanitize_payload

"""
Workspace-wide Slack message search with query modifiers (e.g., `in:#channel`, `from:@user`, `before:YYYY-MM-DD`) plus pagination and sorting controls.

Provider: Slack
Tool: SLACK_SEARCH_MESSAGES

Args:
    query (str): Required Slack search query string.
    count (int): Optional number of results per page (defaults to 20, Slack default 1).
    page (int | None): Optional page index for paginated results.
    sort (str | None): Optional sort field ('score' or 'timestamp').
    sort_dir (str | None): Optional direction ('asc' or 'desc').
    highlight (bool | None): Optional flag to return highlighted contexts.
    auto_paginate (bool | None): Optional flag to iterate through all result pages.
"""
async def slack_search_messages(query: str, *, count: int = 20, page: int | None = None, sort: str | None = None, sort_dir: str | None = None, highlight: bool | None = None, auto_paginate: bool | None = None) -> ToolCallResult[Any]:
    payload: dict[str, Any] = {}
    payload["query"] = query
    if count is not None:
        payload["count"] = count
    if page is not None:
        payload["page"] = page
    if sort is not None:
        payload["sort"] = sort
    if sort_dir is not None:
        payload["sort_dir"] = sort_dir
    if highlight is not None:
        payload["highlight"] = bool(highlight)
    if auto_paginate is not None:
        payload["auto_paginate"] = bool(auto_paginate)
    sanitize_payload(payload)
    return await call_tool('slack', 'SLACK_SEARCH_MESSAGES', payload)

slackSearchMessages = slack_search_messages
