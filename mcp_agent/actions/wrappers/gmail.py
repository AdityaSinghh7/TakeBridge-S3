"""Gmail action wrappers (extracted from actions.py).

Handles parameter mapping and MCP tool invocation for Gmail.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from mcp_agent.types import ToolInvocationResult
from mcp_agent.user_identity import normalize_user_id
from ._common import _clean_payload, ensure_authorized, _invoke_mcp_tool

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

gmail_send_email.__tb_output_schema__ = {
    "properties": {
        "data": {
        "additionalProperties": False,
        "description": "Data from the action execution",
        "properties": {
            "historyId": {
            "default": None,
            "description": "The ID of the last history record that modified this message.",
            "nullable": True,
            "title": "History Id",
            "type": "string"
            },
            "id": {
            "default": None,
            "description": "The immutable ID of the sent message.",
            "nullable": True,
            "title": "Id",
            "type": "string"
            },
            "internalDate": {
            "default": None,
            "description": "The internal timestamp of the message in milliseconds since epoch.",
            "nullable": True,
            "title": "Internal Date",
            "type": "string"
            },
            "labelIds": {
            "default": None,
            "description": "List of IDs of labels applied to this message.",
            "items": {
                "properties": {},
                "type": "string"
            },
            "nullable": True,
            "title": "Label Ids",
            "type": "array"
            },
            "payload": {
            "additionalProperties": True,
            "default": None,
            "description": "The parsed email structure, including headers and body parts.",
            "nullable": True,
            "title": "Payload",
            "type": "object"
            },
            "raw": {
            "default": None,
            "description": "The entire email message in RFC 2822 format, base64url-encoded.",
            "nullable": True,
            "title": "Raw",
            "type": "string"
            },
            "sizeEstimate": {
            "default": None,
            "description": "Estimated size of the message in bytes.",
            "nullable": True,
            "title": "Size Estimate",
            "type": "integer"
            },
            "snippet": {
            "default": None,
            "description": "A short extract of the message text.",
            "nullable": True,
            "title": "Snippet",
            "type": "string"
            },
            "threadId": {
            "default": None,
            "description": "The ID of the thread the message belongs to.",
            "nullable": True,
            "title": "Thread Id",
            "type": "string"
            }
        },
        "title": "Data",
        "type": "object"
        },
        "error": {
        "default": None,
        "description": "Error if any occurred during the execution of the action",
        "nullable": True,
        "title": "Error",
        "type": "string"
        },
        "successful": {
        "description": "Whether or not the action execution was successful or not",
        "title": "Successful",
        "type": "boolean"
        }
    },
    "required": [
        "data",
        "successful"
    ],
    "title": "GmailMessageResponseWrapper",
    "type": "object"
    }


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


# Attach structured output schema for gmail_search so downstream search can surface output_fields
gmail_search.__tb_output_schema__ = {
    "properties": {
        "data": {
            "additionalProperties": False,
            "description": "Data from the action execution",
            "properties": {
                "messages": {
                    "description": (
                        "List of retrieved email messages. Includes full content if `include_payload` was true, "
                        "otherwise metadata."
                    ),
                    "items": {
                        "description": "This model represents the body a Gmail message.",
                        "properties": {
                            "attachmentList": {
                                "description": "The list of attachments",
                                "items": {"properties": {}},
                                "nullable": True,
                                "title": "Attachment List",
                                "type": "array",
                            },
                            "labelIds": {
                                "description": "The label IDs of the message",
                                "items": {"properties": {}},
                                "nullable": True,
                                "title": "Label Ids",
                                "type": "array",
                            },
                            "messageId": {
                                "description": "The message ID of the message",
                                "nullable": True,
                                "title": "Message Id",
                                "type": "string",
                            },
                            "messageText": {
                                "description": "The text of the message",
                                "nullable": True,
                                "title": "Message Text",
                                "type": "string",
                            },
                            "messageTimestamp": {
                                "description": "The timestamp of the message",
                                "nullable": True,
                                "title": "Message Timestamp",
                                "type": "string",
                            },
                            "payload": {
                                "additionalProperties": True,
                                "description": "The payload of the message",
                                "nullable": True,
                                "title": "Payload",
                                "type": "object",
                            },
                            "preview": {
                                "additionalProperties": True,
                                "description": "The preview of the message",
                                "nullable": True,
                                "title": "Preview",
                                "type": "object",
                            },
                            "sender": {
                                "description": "The sender of the message",
                                "nullable": True,
                                "title": "Sender",
                                "type": "string",
                            },
                            "subject": {
                                "description": "The subject of the message",
                                "nullable": True,
                                "title": "Subject",
                                "type": "string",
                            },
                            "threadId": {
                                "description": "The thread ID of the message",
                                "nullable": True,
                                "title": "Thread Id",
                                "type": "string",
                            },
                            "to": {
                                "description": "The recipient of the message",
                                "nullable": True,
                                "title": "To",
                                "type": "string",
                            },
                        },
                        "title": "MessageBody",
                        "type": "object",
                    },
                    "title": "Messages",
                    "type": "array",
                },
                "nextPageToken": {
                    "description": "Token for the next page of results; use in subsequent `page_token` request. Empty if no more results.",
                    "title": "Next Page Token",
                    "type": "string",
                },
                "resultSizeEstimate": {
                    "description": "Estimated total messages matching the query (not just this page).",
                    "title": "Result Size Estimate",
                    "type": "integer",
                },
            },
            "required": ["nextPageToken", "resultSizeEstimate", "messages"],
            "title": "Data",
            "type": "object",
        },
        "error": {
            "default": None,
            "description": "Error if any occurred during the execution of the action",
            "nullable": True,
            "title": "Error",
            "type": "string",
        },
        "successful": {
            "description": "Whether or not the action execution was successful or not",
            "title": "Successful",
            "type": "boolean",
        },
    },
    "required": ["data", "successful"],
    "title": "FetchEmailsResponseWrapper",
    "type": "object",
}


def gmail_create_email_draft(
    context: AgentContext,
    *,
    recipient_email: str | None = None,
    body: str | None = None,
    subject: str | None = None,
    attachment: dict | None = None,
    bcc: list[str] | str | None = None,
    cc: list[str] | str | None = None,
    extra_recipients: list[str] | str | None = None,
    is_html: bool | None = False,
    thread_id: str | None = None,
    user_id: str = "me",
) -> ToolInvocationResult:
    """
    Create a Gmail draft with optional recipients, body, subject, and attachment.

    At least one of recipient_email, cc, or bcc must be provided. Subject or body must be supplied.
    """
    tool_name = "GMAIL_CREATE_EMAIL_DRAFT"
    ensure_authorized(context, "gmail")

    gmail_user_id = _resolve_gmail_user_id(user_id)
    to_primary = (recipient_email or "").strip() or None
    cc_list = _norm_string_list(cc)
    bcc_list = _norm_string_list(bcc)
    extra_list = _norm_string_list(extra_recipients)

    if extra_list and not to_primary:
        raise ValueError("extra_recipients requires recipient_email to be provided.")

    if not (to_primary or cc_list or bcc_list):
        raise ValueError("Provide at least one recipient via recipient_email, cc, or bcc.")

    if not (subject or body):
        raise ValueError("Either subject or body must be provided.")

    payload = _clean_payload(
        {
            "user_id": gmail_user_id,
            "recipient_email": to_primary,
            "subject": subject,
            "body": body,
            "is_html": bool(is_html) if is_html is not None else None,
            "cc": cc_list or None,
            "bcc": bcc_list or None,
            "extra_recipients": extra_list or None,
            "thread_id": thread_id,
            "attachment": attachment,
        }
    )

    return _invoke_mcp_tool(context, "gmail", tool_name, payload)


gmail_create_email_draft.__tb_output_schema__ = {
  "properties": {
    "data": {
      "additionalProperties": False,
      "description": "Data from the action execution",
      "properties": {
        "id": {
          "description": "Immutable ID of the draft.",
          "title": "Id",
          "type": "string"
        },
        "message": {
          "additionalProperties": False,
          "description": "The created draft message resource.",
          "properties": {
            "historyId": {
              "default": None,
              "description": "The ID of the last history record that modified this message.",
              "nullable": True,
              "title": "History Id",
              "type": "string"
            },
            "id": {
              "default": None,
              "description": "The immutable ID of the sent message.",
              "nullable": True,
              "title": "Id",
              "type": "string"
            },
            "internalDate": {
              "default": None,
              "description": "The internal timestamp of the message in milliseconds since epoch.",
              "nullable": True,
              "title": "Internal Date",
              "type": "string"
            },
            "labelIds": {
              "default": None,
              "description": "List of IDs of labels applied to this message.",
              "items": {
                "properties": {},
                "type": "string"
              },
              "nullable": True,
              "title": "Label Ids",
              "type": "array"
            },
            "payload": {
              "additionalProperties": True,
              "default": None,
              "description": "The parsed email structure, including headers and body parts.",
              "nullable": True,
              "title": "Payload",
              "type": "object"
            },
            "raw": {
              "default": None,
              "description": "The entire email message in RFC 2822 format, base64url-encoded.",
              "nullable": True,
              "title": "Raw",
              "type": "string"
            },
            "sizeEstimate": {
              "default": None,
              "description": "Estimated size of the message in bytes.",
              "nullable": True,
              "title": "Size Estimate",
              "type": "integer"
            },
            "snippet": {
              "default": None,
              "description": "A short extract of the message text.",
              "nullable": True,
              "title": "Snippet",
              "type": "string"
            },
            "threadId": {
              "default": None,
              "description": "The ID of the thread the message belongs to.",
              "nullable": True,
              "title": "Thread Id",
              "type": "string"
            }
          },
          "title": "Message",
          "type": "object"
        }
      },
      "required": [
        "id",
        "message"
      ],
      "title": "Data",
      "type": "object"
    },
    "error": {
      "default": None,
      "description": "Error if any occurred during the execution of the action",
      "nullable": True,
      "title": "Error",
      "type": "string"
    },
    "successful": {
      "description": "Whether or not the action execution was successful or not",
      "title": "Successful",
      "type": "boolean"
    }
  },
  "required": [
    "data",
    "successful"
  ],
  "title": "CreateEmailDraftResponseWrapper",
  "type": "object"
}


def gmail_send_draft(
    context: AgentContext,
    draft_id: str,
    user_id: str = "me",
) -> ToolInvocationResult:
    """
    Send an existing Gmail draft by ID.
    """
    tool_name = "GMAIL_SEND_DRAFT"
    ensure_authorized(context, "gmail")

    gmail_user_id = _resolve_gmail_user_id(user_id)
    payload = _clean_payload(
        {
            "draft_id": draft_id,
            "user_id": gmail_user_id,
        }
    )
    return _invoke_mcp_tool(context, "gmail", tool_name, payload)


gmail_send_draft.__tb_output_schema__ = {
  "properties": {
    "data": {
      "additionalProperties": False,
      "description": "Data from the action execution",
      "properties": {
        "historyId": {
          "default": None,
          "description": "The ID of the last history record that modified this message.",
          "nullable": True,
          "title": "History Id",
          "type": "string"
        },
        "id": {
          "default": None,
          "description": "The immutable ID of the sent message.",
          "nullable": True,
          "title": "Id",
          "type": "string"
        },
        "internalDate": {
          "default": None,
          "description": "The internal timestamp of the message in milliseconds since epoch.",
          "nullable": True,
          "title": "Internal Date",
          "type": "string"
        },
        "labelIds": {
          "default": None,
          "description": "List of IDs of labels applied to this message.",
          "items": {
            "properties": {},
            "type": "string"
          },
          "nullable": True,
          "title": "Label Ids",
          "type": "array"
        },
        "payload": {
          "additionalProperties": True,
          "default": None,
          "description": "The parsed email structure, including headers and body parts.",
          "nullable": True,
          "title": "Payload",
          "type": "object"
        },
        "raw": {
          "default": None,
          "description": "The entire email message in RFC 2822 format, base64url-encoded.",
          "nullable": True,
          "title": "Raw",
          "type": "string"
        },
        "sizeEstimate": {
          "default": None,
          "description": "Estimated size of the message in bytes.",
          "nullable": True,
          "title": "Size Estimate",
          "type": "integer"
        },
        "snippet": {
          "default": None,
          "description": "A short extract of the message text.",
          "nullable": True,
          "title": "Snippet",
          "type": "string"
        },
        "threadId": {
          "default": None,
          "description": "The ID of the thread the message belongs to.",
          "nullable": True,
          "title": "Thread Id",
          "type": "string"
        }
      },
      "title": "Data",
      "type": "object"
    },
    "error": {
      "default": None,
      "description": "Error if any occurred during the execution of the action",
      "nullable": True,
      "title": "Error",
      "type": "string"
    },
    "successful": {
      "description": "Whether or not the action execution was successful or not",
      "title": "Successful",
      "type": "boolean"
    }
  },
  "required": [
    "data",
    "successful"
  ],
  "title": "GmailMessageResponseWrapper",
  "type": "object"
}
