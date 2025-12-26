"""
Deprecated shim for MCP registry CRUD.

Canonical implementation lives in `mcp_agent.registry.crud`.
"""

from __future__ import annotations

from mcp_agent.registry.crud import (  # noqa: F401
    disconnect_account,
    disconnect_provider,
    get_active_context_for_provider,
    get_active_contexts_for_all_providers,
    get_active_mcp_for_provider,
    is_authorized,
    upsert_auth_config,
    upsert_connected_account,
    upsert_mcp_connection,
    upsert_user,
)

__all__ = [
    "disconnect_account",
    "disconnect_provider",
    "get_active_context_for_provider",
    "get_active_contexts_for_all_providers",
    "get_active_mcp_for_provider",
    "is_authorized",
    "upsert_auth_config",
    "upsert_connected_account",
    "upsert_mcp_connection",
    "upsert_user",
]
