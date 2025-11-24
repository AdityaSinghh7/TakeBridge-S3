"""
Compatibility shim for the legacy RegistryManager API.

The codebase now exposes functional helpers in `mcp_agent.registry.crud`,
but a few callers still import RegistryManager. This thin wrapper forwards
to the current CRUD + OAuth helpers.
"""

from __future__ import annotations

from mcp_agent.registry.crud import get_active_mcp_for_provider
from mcp_agent.registry.oauth import OAuthManager
from mcp_agent.mcp_client import MCPClient
from mcp_agent.user_identity import normalize_user_id


class RegistryManager:
    def __init__(self, context):
        self.context = context

    def get_mcp_client(self, provider: str):
        """Return an MCPClient for a provider if authorized, else None."""
        user_id = normalize_user_id(self.context.user_id)
        with self.context.get_db() as db:
            url, _ = get_active_mcp_for_provider(db, user_id, provider)
        if not url:
            return None
        headers = OAuthManager.get_headers(self.context, provider)
        return MCPClient(url, headers=headers)
