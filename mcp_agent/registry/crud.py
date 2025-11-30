"""CRUD operations for MCP registry models (migrated from shared/db/crud.py).

All functions now accept AgentContext for multi-tenant operations.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .db_models import AuthConfig, ConnectedAccount, MCPConnection, User

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext

# Status constants
STATUS_ACTIVE = "ACTIVE"
STATUS_DISCONNECTED = "DISCONNECTED"

IS_PG = os.getenv("DB_URL", "").startswith("postgres")


def upsert_user(db: Session, user_id: str) -> User:
    """
    Create or retrieve a user record.
    
    Args:
        db: Database session
        user_id: User/tenant identifier
    
    Returns:
        User model instance
    """
    existing = db.get(User, user_id)
    if existing:
        return existing
    user = User(id=user_id)
    db.add(user)
    db.flush()
    return user


def upsert_auth_config(db: Session, ac_id: str, provider: str, name: str | None) -> AuthConfig:
    """
    Create or update an auth config record.
    
    Args:
        db: Database session
        ac_id: Auth config ID (from Composio)
        provider: Provider name ("gmail", "slack")
        name: Human-readable name
    
    Returns:
        AuthConfig model instance
    """
    existing = db.get(AuthConfig, ac_id)
    if existing:
        # Keep provider/name in sync
        existing.provider = provider
        if name:
            existing.name = name
        db.flush()
        return existing
    
    auth_config = AuthConfig(id=ac_id, provider=provider, name=name)
    db.add(auth_config)
    db.flush()
    return auth_config


def upsert_connected_account(
    db: Session,
    ca_id: str,
    user_id: str,
    auth_config_id: str,
    provider: str,
    status: str,
    provider_uid: str | None = None,
) -> ConnectedAccount:
    """
    Create or update a connected account record.
    
    Enforces unique (user_id, auth_config_id) constraint by reusing
    existing rows when they exist.
    
    Args:
        db: Database session
        ca_id: Connected account ID (from Composio)
        user_id: User/tenant identifier
        auth_config_id: Auth config ID
        provider: Provider name
        status: Connection status ("ACTIVE", etc.)
        provider_uid: Provider-specific user ID (email, team ID)
    
    Returns:
        ConnectedAccount model instance
    """
    # Check if row exists by primary key
    obj = db.get(ConnectedAccount, ca_id)
    if obj:
        obj.status = status
        obj.provider = provider
        obj.provider_uid = provider_uid
        db.flush()
        return obj
    
    # Enforce unique (user_id, auth_config_id): reuse existing row if found
    existing = db.execute(
        select(ConnectedAccount)
        .where(
            ConnectedAccount.user_id == user_id,
            ConnectedAccount.auth_config_id == auth_config_id,
        )
        .limit(1)
    ).scalar_one_or_none()
    
    if existing:
        # If Composio rotated the CA id, migrate to new ID
        if existing.id != ca_id:
            # Delete the old ConnectedAccount first (cascades to delete MCPConnection)
            # This frees up the unique constraint on (user_id, auth_config_id)
            # The caller will recreate MCPConnection with fresh data anyway
            db.delete(existing)
            db.flush()  # Flush to ensure old account is deleted before creating new one
            
            # Now create the new ConnectedAccount with the new ca_id
            new_account = ConnectedAccount(
                id=ca_id,
                user_id=user_id,
                auth_config_id=auth_config_id,
                provider=provider,
                status=status,
                provider_uid=provider_uid,
            )
            db.add(new_account)
            db.flush()  # Flush to ensure new account exists in DB
            return new_account
        
        # Same ID, just update fields
        existing.status = status
        existing.provider = provider
        existing.provider_uid = provider_uid
        db.flush()
        return existing
    
    # Create new row
    connected_account = ConnectedAccount(
        id=ca_id,
        user_id=user_id,
        auth_config_id=auth_config_id,
        provider=provider,
        status=status,
        provider_uid=provider_uid,
    )
    db.add(connected_account)
    db.flush()
    return connected_account


def upsert_mcp_connection(
    db: Session,
    connected_account_id: str,
    mcp_url: str | None,
    headers: Dict[str, Any] | None,
    last_error: str | None = None,
) -> MCPConnection:
    """
    Create or update an MCP connection record.
    
    One row per connected account (latest connection details).
    
    Args:
        db: Database session
        connected_account_id: Connected account ID
        mcp_url: MCP HTTP server URL
        headers: HTTP headers (including auth tokens)
        last_error: Last sync error message
    
    Returns:
        MCPConnection model instance
    """
    stmt = select(MCPConnection).where(
        MCPConnection.connected_account_id == connected_account_id
    ).limit(1)
    row = db.execute(stmt).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    
    if row:
        row.mcp_url = mcp_url
        row.headers_json = headers or {}
        row.last_synced_at = now
        row.last_error = last_error
        db.flush()
        return row
    
    connection = MCPConnection(
        connected_account_id=connected_account_id,
        mcp_url=mcp_url,
        headers_json=headers or {},
        last_synced_at=now,
        last_error=last_error,
    )
    db.add(connection)
    db.flush()
    return connection


def get_active_mcp_for_provider(
    db: Session, user_id: str, provider: str
) -> Tuple[Optional[str], Dict[str, Any]]:
    """
    Get MCP URL and headers for an active provider connection.
    
    Args:
        db: Database session
        user_id: User/tenant identifier
        provider: Provider name
    
    Returns:
        Tuple of (mcp_url, headers) or (None, {}) if not connected
    """
    stmt = (
        select(MCPConnection.mcp_url, MCPConnection.headers_json)
        .join(ConnectedAccount, MCPConnection.connected_account_id == ConnectedAccount.id)
        .where(
            ConnectedAccount.user_id == user_id,
            ConnectedAccount.provider == provider,
            ConnectedAccount.status == STATUS_ACTIVE,
            MCPConnection.mcp_url.is_not(None),
        )
        .order_by(
            ConnectedAccount.updated_at.desc(),
            ConnectedAccount.created_at.desc(),
            MCPConnection.id.desc(),
        )
        .limit(1)
    )
    row = db.execute(stmt).first()
    if not row:
        return None, {}
    return row[0], row[1] or {}


def get_active_context_for_provider(
    db: Session, user_id: str, provider: str
) -> Tuple[Optional[str], Optional[str], Optional[str], Dict[str, Any]]:
    """
    Get full context for an active provider connection.
    
    Args:
        db: Database session
        user_id: User/tenant identifier
        provider: Provider name
    
    Returns:
        Tuple of (connected_account_id, auth_config_id, mcp_url, headers)
        or (None, None, None, {}) if not connected
    """
    stmt = (
        select(
            ConnectedAccount.id,
            ConnectedAccount.auth_config_id,
            MCPConnection.mcp_url,
            MCPConnection.headers_json,
        )
        .join(MCPConnection, MCPConnection.connected_account_id == ConnectedAccount.id)
        .where(
            ConnectedAccount.user_id == user_id,
            ConnectedAccount.provider == provider,
            ConnectedAccount.status == STATUS_ACTIVE,
            MCPConnection.mcp_url.is_not(None),
        )
        .order_by(
            ConnectedAccount.updated_at.desc(),
            ConnectedAccount.created_at.desc(),
            MCPConnection.id.desc(),
        )
        .limit(1)
    )
    row = db.execute(stmt).first()
    if not row:
        return None, None, None, {}
    return row[0], row[1], row[2], row[3] or {}


def is_authorized(db: Session, user_id: str, provider: str) -> bool:
    """
    Check if a user is authorized for a provider.

    Uses OAuthManager.auth_status() to ensure consistent authorization logic
    that includes refresh_required checks.

    Args:
        db: Database session
        user_id: User/tenant identifier
        provider: Provider name

    Returns:
        True if user has active MCP connection with no refresh required
    """
    from mcp_agent.core.context import AgentContext
    from mcp_agent.registry.oauth import OAuthManager

    context = AgentContext.create(user_id)
    status = OAuthManager.auth_status(context, provider)
    return status.get("authorized", False)


def disconnect_provider(db: Session, user_id: str, provider: str) -> dict:
    """
    Disconnect all connections for a user/provider pair.
    
    Soft-delete by setting status to DISCONNECTED and clearing MCP URLs.
    
    Args:
        db: Database session
        user_id: User/tenant identifier
        provider: Provider name
    
    Returns:
        Dict with updated_accounts and cleared_connections counts
    """
    now = datetime.now(timezone.utc)
    
    # Get all connected account IDs for this user/provider
    ca_ids = [
        r[0]
        for r in db.execute(
            select(ConnectedAccount.id)
            .where(
                ConnectedAccount.user_id == user_id,
                ConnectedAccount.provider == provider,
            )
        ).all()
    ]
    
    if not ca_ids:
        return {"updated_accounts": 0, "cleared_connections": 0}
    
    # Deactivate accounts
    acc_res = db.execute(
        update(ConnectedAccount)
        .where(ConnectedAccount.id.in_(ca_ids))
        .values(status=STATUS_DISCONNECTED)
    )
    
    # Clear MCP connections
    con_res = db.execute(
        update(MCPConnection)
        .where(MCPConnection.connected_account_id.in_(ca_ids))
        .values(
            mcp_url=None,
            headers_json={},
            last_error="manually disconnected",
            last_synced_at=now,
        )
    )
    
    return {
        "updated_accounts": acc_res.rowcount or 0,
        "cleared_connections": con_res.rowcount or 0,
    }


def disconnect_account(
    db: Session,
    connected_account_id: str,
    *,
    user_id: Optional[str] = None,
    provider: Optional[str] = None,
) -> dict:
    """
    Disconnect a single connected account.
    
    Optional guards to verify ownership and provider.
    
    Args:
        db: Database session
        connected_account_id: Connected account ID
        user_id: Optional user ID guard
        provider: Optional provider name guard
    
    Returns:
        Dict with updated_accounts and cleared_connections counts
    """
    q = select(ConnectedAccount).where(ConnectedAccount.id == connected_account_id)
    if user_id:
        q = q.where(ConnectedAccount.user_id == user_id)
    if provider:
        q = q.where(ConnectedAccount.provider == provider)
    
    ca = db.execute(q).scalar_one_or_none()
    if not ca:
        return {
            "updated_accounts": 0,
            "cleared_connections": 0,
            "note": "no matching connected_account",
        }
    
    ca.status = STATUS_DISCONNECTED
    
    con_res = db.execute(
        update(MCPConnection)
        .where(MCPConnection.connected_account_id == connected_account_id)
        .values(
            mcp_url=None,
            headers_json={},
            last_error="manually disconnected",
            last_synced_at=datetime.now(timezone.utc),
        )
    )
    
    db.flush()
    return {
        "updated_accounts": 1,
        "cleared_connections": con_res.rowcount or 0,
    }


# --- High-level registry API (formerly RegistryManager) ---

def get_available_providers(context: AgentContext) -> list[dict]:
    """
    Get list of available providers for the current user.

    Uses OAuthManager.auth_status() to ensure consistent authorization logic
    that includes refresh_required checks, matching the inventory view.

    Args:
        context: Agent context with user_id and db_session

    Returns:
        List of provider info dicts with keys: provider, authorized, configured, mcp_url
    """
    from mcp_agent.actions import SUPPORTED_PROVIDERS
    from mcp_agent.registry.oauth import OAuthManager

    providers = []

    for provider in SUPPORTED_PROVIDERS:
        status = OAuthManager.auth_status(context, provider)
        authorized = status.get("authorized", False)
        mcp_url = status.get("mcp_url")
        configured = bool(mcp_url)  # Keep backwards compatibility

        providers.append({
            "provider": provider,
            "authorized": authorized,
            "configured": configured,
            "mcp_url": mcp_url,
        })

    return providers


def get_provider_tools(context: AgentContext, provider: str) -> list[dict]:
    """
    Get list of tools for a provider.

    Args:
        context: Agent context
        provider: Provider name

    Returns:
        List of tool info dicts with keys: provider, name, available, reason
    """
    from mcp_agent.actions import get_provider_action_map

    action_map = get_provider_action_map()
    funcs = action_map.get(provider, ())

    is_available, reason = check_availability(context, provider)

    tools = []
    for func in funcs:
        tools.append({
            "provider": provider,
            "name": func.__name__,
            "available": is_available,
            "reason": reason if not is_available else None,
        })

    return tools


def check_availability(context: AgentContext, provider: str, tool: str | None = None) -> tuple[bool, str]:
    """
    Check if a provider (and optionally tool) is available.

    Args:
        context: Agent context
        provider: Provider name
        tool: Optional tool name

    Returns:
        Tuple of (is_available, reason)
        - is_available: True if provider/tool is usable
        - reason: Human-readable explanation if not available
    """
    from mcp_agent.user_identity import normalize_user_id

    user_id = normalize_user_id(context.user_id)

    # Check if provider is authorized
    with context.get_db() as db:
        authorized = is_authorized(db, user_id, provider)

    if not authorized:
        return False, f"Provider '{provider}' is not authorized for user '{user_id}'"

    # Check if tool exists (if specified)
    if tool:
        from mcp_agent.actions import get_provider_action_map

        action_map = get_provider_action_map()
        funcs = action_map.get(provider, ())
        tool_exists = any(f.__name__ == tool for f in funcs)

        if not tool_exists:
            return False, f"Tool '{tool}' not found for provider '{provider}'"

    return True, "available"


def get_mcp_client(context: AgentContext, provider: str):
    """
    Get an MCP client for a provider.

    Args:
        context: Agent context
        provider: Provider name

    Returns:
        Configured MCPClient instance

    Raises:
        ProviderNotFoundError: If provider is not configured
        UnauthorizedError: If user is not authorized
    """
    from mcp_agent.core.exceptions import ProviderNotFoundError, UnauthorizedError
    from mcp_agent.mcp_client import MCPClient
    from mcp_agent.user_identity import normalize_user_id
    from .oauth import OAuthManager

    user_id = normalize_user_id(context.user_id)

    with context.get_db() as db:
        mcp_url, _ = get_active_mcp_for_provider(db, user_id, provider)

    if not mcp_url:
        # Check if provider exists at all
        from mcp_agent.actions import SUPPORTED_PROVIDERS

        if provider not in SUPPORTED_PROVIDERS:
            raise ProviderNotFoundError(
                provider,
                details={"user_id": user_id},
            )

        # Provider exists but not authorized
        raise UnauthorizedError(
            provider,
            user_id,
            details={"message": "OAuth connection required"},
        )

    # Get headers from OAuth manager
    headers = OAuthManager.get_headers(context, provider)

    return MCPClient(mcp_url, headers=headers)


def is_provider_available(context: AgentContext, provider: str) -> bool:
    """
    Quick check if a provider is available.

    Args:
        context: Agent context
        provider: Provider name

    Returns:
        True if provider is authorized and configured
    """
    from mcp_agent.user_identity import normalize_user_id

    user_id = normalize_user_id(context.user_id)

    with context.get_db() as db:
        return is_authorized(db, user_id, provider)
