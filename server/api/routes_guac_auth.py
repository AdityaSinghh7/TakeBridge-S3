from __future__ import annotations

import base64
import json
import logging
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import text

from server.api.auth import CurrentUser, get_current_user
from shared.db.engine import SessionLocal
from shared.db.models import Workspace
from vm_manager.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/guac", tags=["guacamole"])


def _build_client_url(base_url: str, auth_token: str, connection_id: Optional[str]) -> Optional[str]:
    if not connection_id:
        return None
    raw = connection_id.strip()
    if not raw:
        return None
    if "/" not in raw:
        raw = f"c/{raw}"
    encoded = base64.b64encode(raw.encode("utf-8")).decode("ascii")
    return f"{base_url.rstrip('/')}/#/client/{encoded}?token={auth_token}"


@router.post("/runs/{run_id}/token")
def get_run_guac_token(
    run_id: str,
    payload: Dict[str, Any] = Body(default_factory=dict),
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Exchange Guacamole admin credentials for a short-lived auth token.

    Payload:
      - connection_id: Optional[str] (numeric id or "c/<id>")
    """
    if not (settings.GUAC_ADMIN_USER and settings.GUAC_ADMIN_PASS):
        raise HTTPException(status_code=500, detail="guac_admin_credentials_missing")

    db = SessionLocal()
    try:
        row = db.execute(
            text(
                """
                SELECT wr.user_id, wr.vm_id, wr.environment, vi.endpoint
                FROM workflow_runs wr
                LEFT JOIN vm_instances vi ON vi.id = wr.vm_id
                WHERE wr.id = :run_id
                """
            ),
            {"run_id": run_id},
        ).mappings().all()
    finally:
        db.close()

    match = next((dict(r) for r in row if str(r.get("user_id")) == current_user.sub), None)
    if not match:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run_not_found")

    endpoint = match.get("endpoint")
    env = match.get("environment")
    if env and not endpoint:
        try:
            env_json = json.loads(env) if isinstance(env, str) else env
            endpoint = env_json.get("endpoint")
        except Exception:
            endpoint = None

    if isinstance(endpoint, str):
        try:
            endpoint = json.loads(endpoint)
        except Exception:
            endpoint = {}

    endpoint = endpoint or {}
    guac_url = endpoint.get("vnc_url")
    if not guac_url:
        raise HTTPException(status_code=400, detail="guac_url_missing")

    parsed = urlparse(guac_url)
    if not parsed.scheme or not parsed.netloc:
        raise HTTPException(status_code=400, detail="guac_url_invalid")

    token_url = f"{guac_url.rstrip('/')}/api/tokens"
    try:
        resp = httpx.post(
            token_url,
            data={"username": settings.GUAC_ADMIN_USER, "password": settings.GUAC_ADMIN_PASS},
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        logger.error("Guacamole token request failed: %s", exc)
        raise HTTPException(status_code=502, detail="guac_token_upstream_error") from exc

    if resp.status_code >= 400:
        logger.warning(
            "Guacamole token request rejected status=%s body=%s",
            resp.status_code,
            resp.text[:200],
        )
        raise HTTPException(status_code=502, detail="guac_token_rejected")

    data = resp.json()
    auth_token = data.get("authToken")
    if not auth_token:
        raise HTTPException(status_code=502, detail="guac_token_missing")

    connection_id = payload.get("connection_id")
    client_url = _build_client_url(guac_url, auth_token, connection_id)

    return {
        "auth_token": auth_token,
        "data_source": data.get("dataSource"),
        "guac_url": guac_url,
        "client_url": client_url,
    }


@router.post("/workspace/token")
def get_workspace_guac_token(
    payload: Dict[str, Any] = Body(default_factory=dict),
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Exchange Guacamole admin credentials for a workspace auth token.

    Payload:
      - workspace_id: Optional[str]
      - connection_id: Optional[str] (numeric id or "c/<id>")
    """
    if not (settings.GUAC_ADMIN_USER and settings.GUAC_ADMIN_PASS):
        raise HTTPException(status_code=500, detail="guac_admin_credentials_missing")

    workspace_id = payload.get("workspace_id")

    db = SessionLocal()
    try:
        query = db.query(Workspace).filter(Workspace.user_id == current_user.sub)
        if workspace_id:
            query = query.filter(Workspace.id == workspace_id)
        ws = query.order_by(Workspace.created_at.desc()).first()
    finally:
        db.close()

    if not ws:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workspace_not_found")

    guac_url = ws.vnc_url
    if not guac_url:
        raise HTTPException(status_code=400, detail="guac_url_missing")

    parsed = urlparse(guac_url)
    if not parsed.scheme or not parsed.netloc:
        raise HTTPException(status_code=400, detail="guac_url_invalid")

    token_url = f"{guac_url.rstrip('/')}/api/tokens"
    try:
        resp = httpx.post(
            token_url,
            data={"username": settings.GUAC_ADMIN_USER, "password": settings.GUAC_ADMIN_PASS},
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        logger.error("Guacamole token request failed: %s", exc)
        raise HTTPException(status_code=502, detail="guac_token_upstream_error") from exc

    if resp.status_code >= 400:
        logger.warning(
            "Guacamole token request rejected status=%s body=%s",
            resp.status_code,
            resp.text[:200],
        )
        raise HTTPException(status_code=502, detail="guac_token_rejected")

    data = resp.json()
    auth_token = data.get("authToken")
    if not auth_token:
        raise HTTPException(status_code=502, detail="guac_token_missing")

    connection_id = payload.get("connection_id")
    client_url = _build_client_url(guac_url, auth_token, connection_id)

    return {
        "auth_token": auth_token,
        "data_source": data.get("dataSource"),
        "guac_url": guac_url,
        "client_url": client_url,
    }
