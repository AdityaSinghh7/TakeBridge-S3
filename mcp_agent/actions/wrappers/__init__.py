"""Action wrappers for individual providers."""

from .gmail import gmail_search, gmail_send_email
from .slack import slack_post_message, slack_search_messages

__all__ = [
    "gmail_search",
    "gmail_send_email",
    "slack_post_message",
    "slack_search_messages",
]

