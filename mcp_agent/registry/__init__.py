"""Registry layer - Provider/tool metadata and OAuth management."""

from .oauth import OAuthManager
from .db_models import User, AuthConfig, ConnectedAccount, MCPConnection
from .crud import (
    # Low-level CRUD operations
    upsert_user,
    upsert_auth_config,
    upsert_connected_account,
    upsert_mcp_connection,
    get_active_mcp_for_provider,
    disconnect_provider,
    is_authorized,
    # High-level registry API (functional, replaces RegistryManager)
    get_available_providers,
    get_provider_tools,
    check_availability,
    get_mcp_client,
    is_provider_available,
)

__all__ = [
    # OAuth
    "OAuthManager",
    # Database models
    "User",
    "AuthConfig",
    "ConnectedAccount",
    "MCPConnection",
    # Low-level CRUD
    "upsert_user",
    "upsert_auth_config",
    "upsert_connected_account",
    "upsert_mcp_connection",
    "get_active_mcp_for_provider",
    "disconnect_provider",
    "is_authorized",
    # High-level API (functional, replaces RegistryManager)
    "get_available_providers",
    "get_provider_tools",
    "check_availability",
    "get_mcp_client",
    "is_provider_available",
]
