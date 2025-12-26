from __future__ import annotations

import base64
import json
import logging
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, status

from server.api.auth import CurrentUser, get_current_user
from shared.db.engine import SessionLocal
from shared.db import workflow_runs
from shared.db.models import Workspace
from vm_manager.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/guac", tags=["guacamole"])


def _build_client_url(
    base_url: str,
    auth_token: str,
    connection_id: Optional[str],
    data_source: Optional[str],
) -> Optional[str]:
    if not connection_id or not data_source:
        return None
    raw = f"{connection_id}\x00c\x00{data_source}"
    encoded = base64.b64encode(raw.encode("utf-8")).decode("ascii")
    return f"{base_url.rstrip('/')}/#/client/{encoded}?token={auth_token}"


def _normalize_connection_id(connection_id: Optional[str]) -> Optional[str]:
    if not connection_id:
        return None
    raw = str(connection_id).strip()
    return raw or None


def _select_default_connection(data: Any) -> Optional[str]:
    if not isinstance(data, dict):
        return None
    for key in ("connections", "activeConnections"):
        connections = data.get(key)
        if isinstance(connections, dict):
            for name in sorted(connections.keys()):
                entry = connections.get(name)
                if isinstance(entry, dict):
                    ident = entry.get("identifier") or entry.get("id")
                    if ident:
                        return str(ident)
        if isinstance(connections, list):
            for entry in connections:
                if isinstance(entry, dict):
                    ident = entry.get("identifier") or entry.get("id")
                    if ident:
                        return str(ident)
    # Handle /connections endpoint which returns a map of connections directly.
    for entry in data.values():
        if isinstance(entry, dict):
            ident = entry.get("identifier") or entry.get("id")
            if ident:
                return str(ident)
    return None


def _extract_connection_ids(data: Any) -> list[str]:
    found: list[str] = []
    if isinstance(data, list):
        for entry in data:
            if isinstance(entry, dict):
                ident = entry.get("identifier") or entry.get("id")
                if ident:
                    found.append(str(ident))
        return found
    if not isinstance(data, dict):
        return []
    for key in ("connections", "activeConnections"):
        connections = data.get(key)
        if isinstance(connections, list):
            found.extend(_extract_connection_ids(connections))
        elif isinstance(connections, dict):
            for entry in connections.values():
                if isinstance(entry, dict):
                    ident = entry.get("identifier") or entry.get("id")
                    if ident:
                        found.append(str(ident))
    for entry in data.values():
        if isinstance(entry, dict):
            ident = entry.get("identifier") or entry.get("id")
            if ident:
                found.append(str(ident))
    return found


def _fetch_default_connection_id(
    guac_url: str, auth_token: str, data_source: Optional[str]
) -> tuple[Optional[str], list[str]]:
    token = auth_token
    base = guac_url.rstrip("/")
    candidates: list[str] = []

    def _get_json(url: str) -> Optional[Dict[str, Any]]:
        try:
            resp = httpx.get(url, params={"token": token}, timeout=10.0)
        except httpx.HTTPError as exc:
            logger.error("Guacamole session data request failed: %s", exc)
            return None
        if resp.status_code >= 400:
            logger.warning(
                "Guacamole session data rejected status=%s body=%s",
                resp.status_code,
                resp.text[:200],
            )
            return None
        try:
            return resp.json()
        except ValueError:
            return None

    paths: list[str] = []
    if data_source:
        paths.extend(
            [
                f"{base}/api/session/data/{data_source}",
                f"{base}/api/session/data/{data_source}/",
                f"{base}/api/session/data/{data_source}/connections",
                f"{base}/api/session/data/{data_source}/connections/",
            ]
        )
    paths.extend([f"{base}/api/session/data", f"{base}/api/session/data/"])

    root: Optional[Dict[str, Any]] = None
    for path in paths:
        data = _get_json(path)
        if not data:
            continue
        candidates.extend(_extract_connection_ids(data))
        ident = _select_default_connection(data)
        if ident:
            return ident, candidates
        if root is None:
            root = data

    if not root:
        return None, candidates

    data_sources = root.get("dataSources")
    if isinstance(data_sources, dict) and data_sources:
        chosen = data_source or next(iter(sorted(data_sources.keys())), None)
        if chosen:
            entry = data_sources.get(chosen)
            if isinstance(entry, dict):
                candidates.extend(_extract_connection_ids(entry))
                ident = _select_default_connection(entry)
                if ident:
                    return ident, candidates
            fallback = _get_json(f"{base}/api/session/data/{chosen}")
            if fallback:
                candidates.extend(_extract_connection_ids(fallback))
                return _select_default_connection(fallback), candidates

    candidates.extend(_extract_connection_ids(root))
    return _select_default_connection(root), candidates


@router.post("/runs/{run_id}/token")
def get_run_guac_token(
    run_id: str,
    payload: Dict[str, Any] = Body(default_factory=dict),
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Exchange Guacamole admin credentials for a short-lived auth token.

    Payload:
      - connection_id: Optional[str] (numeric id)
    """
    if not (settings.GUAC_ADMIN_USER and settings.GUAC_ADMIN_PASS):
        raise HTTPException(status_code=500, detail="guac_admin_credentials_missing")

    db = SessionLocal()
    try:
        endpoint = workflow_runs.get_run_vm_endpoint(db, run_id=run_id, user_id=current_user.sub)
    finally:
        db.close()

    if endpoint is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run_not_found")
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
    data_source = data.get("dataSource")

    connection_id = _normalize_connection_id(payload.get("connection_id"))
    if not connection_id:
        default_id, candidates = _fetch_default_connection_id(
            guac_url, auth_token, data_source
        )
        connection_id = _normalize_connection_id(default_id) or _normalize_connection_id(
            settings.GUAC_CONNECTION_ID
        )
    else:
        candidates = []
    client_url = _build_client_url(guac_url, auth_token, connection_id, data_source)

    response = {
        "auth_token": auth_token,
        "data_source": data_source,
        "guac_url": guac_url,
        "client_url": client_url,
    }
    if not client_url:
        response["connection_ids"] = candidates
    return response


@router.post("/workspace/token")
def get_workspace_guac_token(
    payload: Dict[str, Any] = Body(default_factory=dict),
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Exchange Guacamole admin credentials for a workspace auth token.

    Payload:
      - workspace_id: Optional[str]
      - connection_id: Optional[str] (numeric id)
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
    data_source = data.get("dataSource")

    connection_id = _normalize_connection_id(payload.get("connection_id"))
    if not connection_id:
        default_id, candidates = _fetch_default_connection_id(
            guac_url, auth_token, data_source
        )
        connection_id = _normalize_connection_id(default_id) or _normalize_connection_id(
            settings.GUAC_CONNECTION_ID
        )
    else:
        candidates = []
    client_url = _build_client_url(guac_url, auth_token, connection_id, data_source)

    response = {
        "auth_token": auth_token,
        "data_source": data_source,
        "guac_url": guac_url,
        "client_url": client_url,
    }
    if not client_url:
        response["connection_ids"] = candidates
    return response
