from __future__ import annotations

from typing import Any

from ...client import ToolCallResult, call_tool, normalize_string_list, sanitize_payload

"""
Fetches a list of email messages from a Gmail account, supporting filtering, pagination, and optional full content retrieval.

Provider: Gmail
Tool: GMAIL_FETCH_EMAILS

Args:
    query (str): Required Gmail search query (e.g., 'from:alice has:attachment').
    max_results (int): Optional maximum number of results to return (defaults to 20, API default 1).
    label_ids (Any | None): Optional comma-separated string or iterable of label IDs to include.
    page_token (str | None): Optional pagination token from a previous response.
    include_payload (bool | None): Optional flag to return full MIME payloads.
    include_spam_trash (bool | None): Optional flag to include spam and trash.
    ids_only (bool | None): Optional flag to return only message ids/snippets.
    verbose (bool | None): Optional flag for verbose response metadata.
    user_id (str): Optional Gmail user identifier (defaults to 'me').
"""
async def gmail_search(query: str, max_results: int = 20, *, label_ids: Any | None = None, page_token: str | None = None, include_payload: bool | None = None, include_spam_trash: bool | None = None, ids_only: bool | None = None, verbose: bool | None = None, user_id: str = 'me') -> ToolCallResult[Any]:
    payload: dict[str, Any] = {}
    payload["query"] = query
    if max_results is not None:
        payload["max_results"] = max_results
    label_ids_list = normalize_string_list(label_ids)
    if label_ids_list:
        payload["label_ids"] = label_ids_list
    if page_token is not None:
        payload["page_token"] = page_token
    if include_payload is not None:
        payload["include_payload"] = bool(include_payload)
    if include_spam_trash is not None:
        payload["include_spam_trash"] = bool(include_spam_trash)
    if ids_only is not None:
        payload["ids_only"] = bool(ids_only)
    if verbose is not None:
        payload["verbose"] = bool(verbose)
    if user_id is not None:
        payload["user_id"] = user_id
    sanitize_payload(payload)
    return await call_tool('gmail', 'GMAIL_FETCH_EMAILS', payload)

gmailSearch = gmail_search
