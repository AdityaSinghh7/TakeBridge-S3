from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from mcp_agent.registry.db_models import ConnectedAccount
from mcp_agent.registry.oauth import COMPOSIO_API_V3, _headers
from mcp_agent.user_identity import normalize_user_id

logger = logging.getLogger(__name__)

_STATUS_ACTIVE = "ACTIVE"


def _normalize_provider_key(value: str | None) -> str:
    return (value or "").strip().lower().replace("-", "_").replace(" ", "_")


def resolve_tool_constraint_providers(
    tool_constraints: Optional[Dict[str, Any]],
) -> Optional[List[str]]:
    if not tool_constraints or not isinstance(tool_constraints, dict):
        return None

    providers: List[str] = []
    for raw in tool_constraints.get("providers") or []:
        key = _normalize_provider_key(str(raw))
        if key:
            providers.append(key)

    for raw in tool_constraints.get("tools") or []:
        if not isinstance(raw, str) or not raw:
            continue
        provider = raw.split(".", 1)[0]
        key = _normalize_provider_key(provider)
        if key:
            providers.append(key)

    seen: set[str] = set()
    ordered: List[str] = []
    for provider in providers:
        if provider not in seen:
            ordered.append(provider)
            seen.add(provider)

    return ordered


def list_active_connected_accounts(
    db: Session,
    user_id: str,
    providers: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    normalized_user = normalize_user_id(user_id)
    stmt = (
        select(
            ConnectedAccount.id,
            ConnectedAccount.provider,
            ConnectedAccount.auth_config_id,
            ConnectedAccount.status,
        )
        .where(ConnectedAccount.user_id == normalized_user)
        .where(ConnectedAccount.status == _STATUS_ACTIVE)
    )
    rows = db.execute(stmt).all()
    accounts = [
        {
            "connected_account_id": row[0],
            "provider": row[1],
            "provider_key": _normalize_provider_key(row[1]),
            "auth_config_id": row[2],
            "status": row[3],
        }
        for row in rows
    ]

    if providers is None:
        return accounts

    provider_keys = {_normalize_provider_key(p) for p in providers if p}
    if not provider_keys:
        return []

    return [acc for acc in accounts if acc["provider_key"] in provider_keys]


def _build_list_params(
    *,
    user_ids: Sequence[str],
    cursor: Optional[str],
    limit: Optional[int],
    toolkit_slugs: Optional[Sequence[str]],
    connected_account_ids: Optional[Sequence[str]],
) -> List[Tuple[str, str]]:
    params: List[Tuple[str, str]] = []
    for uid in user_ids:
        params.append(("user_ids", uid))
    if toolkit_slugs:
        for slug in toolkit_slugs:
            if slug:
                params.append(("toolkit_slugs", slug))
    if connected_account_ids:
        for ca_id in connected_account_ids:
            if ca_id:
                params.append(("connected_account_ids", ca_id))
    if cursor:
        params.append(("cursor", cursor))
    if limit:
        params.append(("limit", str(limit)))
    return params


def _list_connected_accounts_page(
    *,
    user_ids: Sequence[str],
    cursor: Optional[str],
    limit: int,
    timeout: int,
    toolkit_slugs: Optional[Sequence[str]] = None,
    connected_account_ids: Optional[Sequence[str]] = None,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    url = f"{COMPOSIO_API_V3}/connected_accounts"
    params = _build_list_params(
        user_ids=user_ids,
        cursor=cursor,
        limit=limit,
        toolkit_slugs=toolkit_slugs,
        connected_account_ids=connected_account_ids,
    )
    resp = requests.get(
        url,
        headers={**_headers(), "accept": "application/json"},
        params=params,
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}

    items = data.get("items") or data.get("data") or []
    if isinstance(items, dict):
        items = items.get("items") or items.get("data") or []
    if not isinstance(items, list):
        items = []

    next_cursor = data.get("next_cursor") or data.get("nextCursor")
    return items, next_cursor


def fetch_connected_accounts_for_user(
    user_id: str,
    *,
    timeout: int = 15,
    limit: int = 100,
    toolkit_slugs: Optional[Sequence[str]] = None,
    connected_account_ids: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    normalized_user = normalize_user_id(user_id)
    items: List[Dict[str, Any]] = []
    cursor: Optional[str] = None
    seen: set[str] = set()

    while True:
        page_items, cursor = _list_connected_accounts_page(
            user_ids=[normalized_user],
            cursor=cursor,
            limit=limit,
            timeout=timeout,
            toolkit_slugs=toolkit_slugs,
            connected_account_ids=connected_account_ids,
        )
        items.extend(page_items)
        if not cursor or cursor in seen:
            break
        seen.add(cursor)

    return items


def _parse_connected_account_item(item: Dict[str, Any]) -> Dict[str, Any]:
    toolkit = item.get("toolkit") or {}
    toolkit_slug = (
        toolkit.get("slug")
        or item.get("toolkit_slug")
        or item.get("toolkitSlug")
    )
    status = (item.get("status") or "").upper()
    data = item.get("data") or {}
    auth_refresh_required = bool(
        item.get("auth_refresh_required")
        or item.get("authRefreshRequired")
        or data.get("auth_refresh_required")
        or data.get("authRefreshRequired")
    )
    return {
        "id": item.get("id"),
        "status": status,
        "auth_refresh_required": auth_refresh_required,
        "toolkit_slug": toolkit_slug,
        "user_id": item.get("user_id") or item.get("userId"),
    }


def build_connected_account_index(items: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        parsed = _parse_connected_account_item(item)
        ca_id = parsed.get("id")
        if ca_id:
            parsed["source"] = "list"
            index[str(ca_id)] = parsed
    return index


def _fetch_connected_accounts_by_id_parallel(
    connected_account_ids: Sequence[str],
    *,
    timeout: int = 15,
) -> Dict[str, Dict[str, Any]]:
    results: Dict[str, Dict[str, Any]] = {}
    if not connected_account_ids:
        return results

    max_workers = max(1, min(len(connected_account_ids), 16))

    def _fetch(ca_id: str) -> Tuple[str, Optional[Dict[str, Any]]]:
        try:
            resp = requests.get(
                f"{COMPOSIO_API_V3}/connected_accounts/{ca_id}",
                headers=_headers(),
                timeout=timeout,
            )
            resp.raise_for_status()
            detail = resp.json()
        except Exception as exc:
            logger.warning("Failed to fetch connected account %s: %s", ca_id, exc)
            return ca_id, None
        parsed = _parse_connected_account_item(detail)
        parsed["id"] = parsed.get("id") or ca_id
        parsed["source"] = "detail"
        return ca_id, parsed

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_fetch, ca_id): ca_id for ca_id in connected_account_ids}
        for future in as_completed(futures):
            ca_id, parsed = future.result()
            if parsed:
                results[str(ca_id)] = parsed
    return results


def _evaluate_refresh_required(info: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    status = (info.get("status") or "").upper()
    if status and status != _STATUS_ACTIVE:
        return True, f"connected_account_status={status}"
    if info.get("auth_refresh_required"):
        return True, "auth_refresh_required"
    return False, None


def check_connected_account_statuses(
    user_id: str,
    *,
    providers: Optional[Iterable[str]] = None,
    db_session: Optional[Session] = None,
    timeout: int = 15,
) -> Dict[str, Any]:
    normalized_user = normalize_user_id(user_id)
    accounts: List[Dict[str, Any]] = []

    if db_session is not None:
        accounts = list_active_connected_accounts(db_session, normalized_user, providers)
    else:
        from mcp_agent.core.context import AgentContext

        context = AgentContext.create(normalized_user)
        with context.get_db() as db:
            accounts = list_active_connected_accounts(db, normalized_user, providers)

    if not accounts:
        return {
            "blocked_providers": [],
            "reasons": {},
            "details": [],
            "checked_accounts": 0,
            "list_error": None,
        }

    list_error = None
    index: Dict[str, Dict[str, Any]] = {}
    try:
        items = fetch_connected_accounts_for_user(normalized_user, timeout=timeout)
        index = build_connected_account_index(items)
    except Exception as exc:
        list_error = str(exc)
        logger.warning("Connected account list fetch failed user_id=%s error=%s", normalized_user, exc)

    missing_ids = [acc["connected_account_id"] for acc in accounts if acc["connected_account_id"] not in index]
    if missing_ids:
        fallback = _fetch_connected_accounts_by_id_parallel(missing_ids, timeout=timeout)
        index.update(fallback)

    blocked_providers: List[str] = []
    reasons: Dict[str, str] = {}
    details: List[Dict[str, Any]] = []

    for acc in accounts:
        ca_id = acc["connected_account_id"]
        info = index.get(ca_id)
        if not info:
            continue
        refresh_required, reason = _evaluate_refresh_required(info)
        details.append(
            {
                "provider": acc["provider"],
                "connected_account_id": ca_id,
                "status": info.get("status"),
                "auth_refresh_required": info.get("auth_refresh_required", False),
                "reason": reason,
                "source": info.get("source"),
            }
        )
        if refresh_required:
            provider = acc["provider"]
            if provider not in blocked_providers:
                blocked_providers.append(provider)
            if reason:
                reasons.setdefault(provider, reason)

    return {
        "blocked_providers": blocked_providers,
        "reasons": reasons,
        "details": details,
        "checked_accounts": len(accounts),
        "list_error": list_error,
    }


__all__ = [
    "resolve_tool_constraint_providers",
    "list_active_connected_accounts",
    "fetch_connected_accounts_for_user",
    "build_connected_account_index",
    "check_connected_account_statuses",
]
