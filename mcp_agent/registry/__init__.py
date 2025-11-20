"""Registry layer - Provider/tool metadata and OAuth management."""

from .manager import RegistryManager
from .oauth import OAuthManager
from .models import User, AuthConfig, ConnectedAccount, MCPConnection
from .crud import (
    upsert_user,
    upsert_auth_config,
    upsert_connected_account,
    upsert_mcp_connection,
    get_active_mcp_for_provider,
    disconnect_provider,
    is_authorized,
)

__all__ = [
    "RegistryManager",
    "OAuthManager",
    "User",
    "AuthConfig",
    "ConnectedAccount",
    "MCPConnection",
    "upsert_user",
    "upsert_auth_config",
    "upsert_connected_account",
    "upsert_mcp_connection",
    "get_active_mcp_for_provider",
    "disconnect_provider",
    "is_authorized",
]
