from __future__ import annotations
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timezone

from sqlalchemy import select, update, insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from .models import User, AuthConfig, ConnectedAccount, MCPConnection
from .util import STATUS_DISCONNECTED
import os
IS_PG = os.getenv("DB_URL","").startswith("postgres")

def upsert_user(db: Session, user_id: str) -> User:
    existing = db.get(User, user_id)
    if existing:
        return existing
    u = User(id=user_id)
    db.add(u)
    db.flush()
    return u

def upsert_auth_config(db: Session, ac_id: str, provider: str, name: str | None) -> AuthConfig:
    existing = db.get(AuthConfig, ac_id)
    if existing:
        # keep name/provider in sync
        existing.provider = provider
        if name:
            existing.name = name
        db.flush()
        return existing
    ac = AuthConfig(id=ac_id, provider=provider, name=name)
    db.add(ac)
    db.flush()
    return ac

def upsert_connected_account(
    db: Session,
    ca_id: str,
    user_id: str,
    auth_config_id: str,
    provider: str,
    status: str,
    provider_uid: str | None = None,
) -> ConnectedAccount:
    # 1) If row exists by primary key, update and return
    obj = db.get(ConnectedAccount, ca_id)
    if obj:
        obj.status = status
        obj.provider = provider
        obj.provider_uid = provider_uid
        db.flush()
        return obj

    # 2) Enforce unique (user_id, auth_config_id): if one exists, reuse it instead
    existing = db.execute(
        select(ConnectedAccount)
        .where(
            ConnectedAccount.user_id == user_id,
            ConnectedAccount.auth_config_id == auth_config_id,
        )
        .limit(1)
    ).scalar_one_or_none()
    if existing:
        # If Composio issued a new connected_account_id, replace the old row so
        # foreign keys remain valid and we stay aligned with upstream ids.
        if existing.id != ca_id:
            # Delete the old row (cascades to MCPConnection), then recreate with new id.
            db.delete(existing)
            db.flush()
            ca = ConnectedAccount(
                id=ca_id,
                user_id=user_id,
                auth_config_id=auth_config_id,
                provider=provider,
                status=status,
                provider_uid=provider_uid,
            )
            db.add(ca)
            db.flush()
            return ca

        existing.status = status
        existing.provider = provider
        existing.provider_uid = provider_uid
        db.flush()
        return existing

    # 3) No conflicts; create new row with provided id
    ca = ConnectedAccount(
        id=ca_id,
        user_id=user_id,
        auth_config_id=auth_config_id,
        provider=provider,
        status=status,
        provider_uid=provider_uid,
    )
    db.add(ca)
    db.flush()
    return ca

def upsert_mcp_connection(
    db: Session,
    connected_account_id: str,
    mcp_url: str | None,
    headers: Dict[str, Any] | None,
    last_error: str | None = None,
) -> MCPConnection:
    # one row per CA (latest), simplest is: find existing; else insert
    stmt = select(MCPConnection).where(MCPConnection.connected_account_id == connected_account_id).limit(1)
    row = db.execute(stmt).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if row:
        row.mcp_url = mcp_url
        row.headers_json = headers or {}
        row.last_synced_at = now
        row.last_error = last_error
        db.flush()
        return row
    new = MCPConnection(
        connected_account_id=connected_account_id,
        mcp_url=mcp_url,
        headers_json=headers or {},
        last_synced_at=now,
        last_error=last_error,
    )
    db.add(new)
    db.flush()
    return new

def get_active_mcp_for_provider(db: Session, user_id: str, provider: str) -> Tuple[Optional[str], Dict[str, Any]]:
    """
    Return (mcp_url, headers) iff the user has an ACTIVE connected account
    with a stored MCP connection URL.
    """
    stmt = (
        select(MCPConnection.mcp_url, MCPConnection.headers_json)
        .join(ConnectedAccount, MCPConnection.connected_account_id == ConnectedAccount.id)
        .where(
            ConnectedAccount.user_id == user_id,
            ConnectedAccount.provider == provider,
            ConnectedAccount.status == "ACTIVE",
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
    Return (connected_account_id, auth_config_id, mcp_url, headers) for the active
    provider for this user, if any. Otherwise returns (None, None, None, {}).
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
            ConnectedAccount.status == "ACTIVE",
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
    url, _ = get_active_mcp_for_provider(db, user_id, provider)
    return bool(url)


def disconnect_provider(db: Session, user_id: str, provider: str) -> dict:
    """
    Soft-deactivate ALL connected accounts for (user_id, provider):
      - set connected_accounts.status = 'DISCONNECTED'
      - null out mcp_connections.mcp_url and headers_json
      - stamp last_error for audit
    Returns a summary {updated_accounts, cleared_connections}
    """
    now = datetime.now(timezone.utc)

    # Grab all CA ids first (only those we own)
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

    # 1) Deactivate accounts
    acc_res = db.execute(
        update(ConnectedAccount)
        .where(ConnectedAccount.id.in_(ca_ids))
        .values(status=STATUS_DISCONNECTED)
    )

    # 2) Clear MCP connection endpoints
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
    Soft-deactivate a SINGLE Connected Account by id. Optional guards:
    - if user_id is provided, require it matches
    - if provider is provided, require it matches
    """
    q = select(ConnectedAccount).where(ConnectedAccount.id == connected_account_id)
    if user_id:
        q = q.where(ConnectedAccount.user_id == user_id)
    if provider:
        q = q.where(ConnectedAccount.provider == provider)

    ca = db.execute(q).scalar_one_or_none()
    if not ca:
        return {"updated_accounts": 0, "cleared_connections": 0, "note": "no matching connected_account"}

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
    return {"updated_accounts": 1, "cleared_connections": con_res.rowcount or 0}
