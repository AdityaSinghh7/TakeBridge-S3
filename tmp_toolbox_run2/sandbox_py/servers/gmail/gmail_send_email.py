from __future__ import annotations

from typing import Any

from ...client import ToolCallResult, call_tool, merge_recipient_lists, normalize_string_list, sanitize_payload

"""
Sends an email via Gmail API using the authenticated user's Google profile display name. At least one of recipient_email, cc, or bcc must be provided. Atleast one of subject or body must be provided. Requires `is_html=True` if the body contains HTML and valid `s3key`, `mimetype`, `name` for any attachment.

Provider: Gmail
Tool: GMAIL_SEND_EMAIL

Args:
    to (str): Comma-separated recipients.
    subject (str): Subject line text.
    body (str): Plain text or simple HTML body.
    cc (str): Optional comma-separated CC recipients.
    bcc (str): Optional comma-separated BCC recipients.
    thread_id (str): Optional Gmail thread to reply into.
    is_html (bool): Optional boolean indicating if the body contains HTML.
"""
async def gmail_send_email(to: str, subject: str, body: str, cc: str = '', bcc: str = '', thread_id: str = '', is_html: bool = False) -> ToolCallResult[Any]:
    to_list = normalize_string_list(to) or []
    if not to_list:
        raise ValueError('gmail_send_email requires at least one recipient in `to`.')
    primary_recipient = to_list[0]
    extra_recipients = to_list[1:]
    cc_list = merge_recipient_lists(cc, extra_recipients)
    bcc_list = normalize_string_list(bcc)
    payload: dict[str, Any] = {
        'recipient_email': primary_recipient,
        'subject': subject,
        'body': body,
        'is_html': bool(is_html),
    }
    if cc_list:
        payload['cc'] = cc_list
    if bcc_list:
        payload['bcc'] = bcc_list
    if thread_id is not None:
        payload['thread_id'] = thread_id
    sanitize_payload(payload)
    return await call_tool('gmail', 'GMAIL_SEND_EMAIL', payload)

gmailSendEmail = gmail_send_email
