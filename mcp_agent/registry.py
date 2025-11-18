from __future__ import annotations

import os
from importlib import import_module
from threading import RLock
from typing import Dict, Tuple

from dotenv import load_dotenv

from mcp_agent.user_identity import ensure_user_id, normalize_user_id

from .mcp_client import MCPClient
from .oauth import OAuthManager, COMPOSIO_KEY
from shared.db.engine import session_scope
from shared.db.crud import get_active_mcp_for_provider


MCP_BY_USER: Dict[str, Dict[str, MCPClient]] = {}
MCP: Dict[str, MCPClient] = {}
_REGISTRY_VERSION_BY_USER: Dict[str, int] = {}
_FAKE_FACTORY_ENV = "MCP_FAKE_CLIENT_FACTORY"
_REGISTRY_LOCK = RLock()


def _get_bucket_unlocked(uid: str) -> Dict[str, MCPClient]:
    bucket = MCP_BY_USER.setdefault(uid, {})
    global MCP
    MCP = bucket
    return bucket


def _get_bucket(user_id: str) -> Dict[str, MCPClient]:
    uid = normalize_user_id(user_id)
    with _REGISTRY_LOCK:
        return _get_bucket_unlocked(uid)


def _registry_snapshot_locked(uid: str) -> Tuple[Tuple[str, str | None, Tuple[Tuple[str, str], ...]], ...]:
    bucket = _get_bucket_unlocked(uid)
    snapshot = []
    for provider, client in sorted(bucket.items()):
        base_url = getattr(client, "base_url", None)
        headers = getattr(client, "headers", {}) or {}
        # Normalize header values to strings to keep snapshot hashable
        header_items = tuple(sorted((str(k), str(v)) for k, v in headers.items()))
        snapshot.append((provider, base_url, header_items))
    return tuple(snapshot)


def _registry_snapshot(user_id: str | None = None) -> Tuple[Tuple[str, str | None, Tuple[Tuple[str, str], ...]], ...]:
    uid = normalize_user_id(ensure_user_id(user_id))
    with _REGISTRY_LOCK:
        return _registry_snapshot_locked(uid)


def _install_fake_clients(user_id: str) -> bool:
    factory_path = os.getenv(_FAKE_FACTORY_ENV, "").strip()
    if not factory_path:
        return False
    try:
        module_name, func_name = factory_path.rsplit(":", 1)
        module = import_module(module_name)
        factory = getattr(module, func_name)
    except (ValueError, ImportError, AttributeError) as exc:
        raise RuntimeError(f"Invalid MCP fake client factory '{factory_path}': {exc}") from exc

    # Factories may or may not accept a user_id kwarg; prefer passing it and
    # fall back to a parameterless call for older implementations.
    try:
        clients = factory(user_id=user_id)
    except TypeError:
        clients = factory()
    if not isinstance(clients, dict):
        raise RuntimeError("Fake client factory must return a dict of provider -> client instances.")
    with _REGISTRY_LOCK:
        bucket = _get_bucket_unlocked(normalize_user_id(user_id))
        bucket.clear()
        for provider, client in clients.items():
            bucket[provider] = client
    return True


def _maybe_bump_version_locked(user_id: str, before: Tuple[Tuple[str, str | None, Tuple[Tuple[str, str], ...]], ...]) -> None:
    after = _registry_snapshot_locked(user_id)
    if after != before:
        _REGISTRY_VERSION_BY_USER[user_id] = _REGISTRY_VERSION_BY_USER.get(user_id, 0) + 1


def init_registry(user_id: str) -> None:
    load_dotenv()
    uid = normalize_user_id(user_id)
    with _REGISTRY_LOCK:
        bucket = _get_bucket_unlocked(uid)
        before = _registry_snapshot_locked(uid)

        # Rebuild known providers
        for prov in ["slack", "gmail"]:
            bucket.pop(prov, None)

        if _install_fake_clients(uid):
            _maybe_bump_version_locked(uid, before)
            return

        # DB-backed connections first (use OAuthManager.get_headers to merge x-api-key)
        with session_scope() as db:
            for prov in ("slack", "gmail"):
                url, _ = get_active_mcp_for_provider(db, uid, prov)
                if url:
                    bucket[prov] = MCPClient(url, headers=OAuthManager.get_headers(uid, prov))

        # env fallback
        token = os.getenv("COMPOSIO_TOKEN", "")

        def _env_headers(prov: str) -> Dict[str, str]:
            prov_upper = prov.upper()
            hdrs: Dict[str, str] = {}
            if token:
                hdrs["Authorization"] = f"Bearer {token}"
            connected_account = os.getenv(f"COMPOSIO_{prov_upper}_CONNECTED_ACCOUNT_ID")
            if connected_account:
                hdrs["X-Connected-Account-Id"] = connected_account
            auth_config_id = os.getenv(f"COMPOSIO_{prov_upper}_AUTH_CONFIG_ID")
            if auth_config_id:
                hdrs["X-Auth-Config-Id"] = auth_config_id
            if COMPOSIO_KEY and not hdrs.get("x-api-key"):
                hdrs["x-api-key"] = COMPOSIO_KEY
            return hdrs

        slack_url_env = os.getenv("COMPOSIO_SLACK_URL")
        gmail_url_env = os.getenv("COMPOSIO_GMAIL_URL")
        if "slack" not in bucket and slack_url_env:
            bucket["slack"] = MCPClient(slack_url_env, headers=_env_headers("slack"))
        if "gmail" not in bucket and gmail_url_env:
            bucket["gmail"] = MCPClient(gmail_url_env, headers=_env_headers("gmail"))
        _maybe_bump_version_locked(uid, before)


def get_configured_providers(user_id: str) -> set[str]:
    """
    Return the set of MCP providers that are configured for the given user.

    This reflects the current contents of the per-user MCP client bucket after
    applying DB-backed connections, environment overrides, or fake clients.
    """
    uid = normalize_user_id(user_id)
    # Ensure the registry is initialized for this user so the bucket is up to date.
    init_registry(uid)
    with _REGISTRY_LOCK:
        bucket = _get_bucket_unlocked(uid)
        return set(bucket.keys())


def get_client(provider: str, user_id: str) -> MCPClient | None:
    """Return the MCP client for a provider/user, if registered."""
    uid = normalize_user_id(user_id)
    with _REGISTRY_LOCK:
        bucket = _get_bucket_unlocked(uid)
        return bucket.get(provider)


def is_registered(provider: str, user_id: str) -> bool:
    """Return True if a provider is present in the MCP registry."""
    uid = normalize_user_id(user_id)
    with _REGISTRY_LOCK:
        bucket = _get_bucket_unlocked(uid)
        return provider in bucket


def refresh_registry_from_oauth(user_id: str) -> None:
    """Refresh MCP clients based on stored OAuth connections."""
    init_registry(user_id)


def registry_version(user_id: str) -> int:
    uid = normalize_user_id(user_id)
    with _REGISTRY_LOCK:
        return _REGISTRY_VERSION_BY_USER.get(uid, 0)
