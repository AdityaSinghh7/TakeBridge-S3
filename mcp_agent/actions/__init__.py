"""Actions layer: Raw MCP tool wrappers.

Provides standardized wrappers for all MCP tools across providers.
"""

from .wrappers.gmail import gmail_search, gmail_send_email
from .wrappers.slack import slack_post_message, slack_search_messages

# Provider -> tools mapping
SUPPORTED_PROVIDERS = ("slack", "gmail")

PROVIDER_ACTIONS = {
    "slack": (slack_post_message, slack_search_messages),
    "gmail": (gmail_send_email, gmail_search),
}


def get_provider_action_map():
    """
    Get mapping of provider -> action functions.
    
    Returns:
        Dict mapping provider name to tuple of action functions
    """
    return {
        provider: tuple(funcs)
        for provider, funcs in PROVIDER_ACTIONS.items()
    }


__all__ = [
    "SUPPORTED_PROVIDERS",
    "PROVIDER_ACTIONS",
    "get_provider_action_map",
    "gmail_search",
    "gmail_send_email",
    "slack_post_message",
    "slack_search_messages",
]

