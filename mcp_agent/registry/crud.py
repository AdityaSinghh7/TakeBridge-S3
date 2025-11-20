"""CRUD operations for MCP registry models (migrated from shared/db/crud.py).

All functions now accept AgentContext for multi-tenant operations.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .models import AuthConfig, ConnectedAccount, MCPConnection, User

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
        .order_by(MCPConnection.id.desc())
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
        .order_by(MCPConnection.id.desc())
        .limit(1)
    )
    row = db.execute(stmt).first()
    if not row:
        return None, None, None, {}
    return row[0], row[1], row[2], row[3] or {}


def is_authorized(db: Session, user_id: str, provider: str) -> bool:
    """
    Check if a user is authorized for a provider.
    
    Args:
        db: Database session
        user_id: User/tenant identifier
        provider: Provider name
    
    Returns:
        True if user has active MCP connection for provider
    """
    url, _ = get_active_mcp_for_provider(db, user_id, provider)
    return bool(url)


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

