from __future__ import annotations

import os
from typing import Dict

from mcp_agent.user_identity import normalize_user_id


def _env_key(provider: str, suffix: str) -> str:
    return f"COMPOSIO_{provider.upper()}_{suffix}"


def ensure_env_for_provider(user_id: str, provider: str) -> None:
    """
    Populate COMPOSIO_* environment variables for a provider using DB-backed OAuth state.
    """

    try:
        from mcp_agent.oauth import OAuthManager  # local import to avoid optional deps in tests
    except ImportError:
        return

    normalized_user = normalize_user_id(user_id)
    url = OAuthManager.get_mcp_url(normalized_user, provider)
    if not url:
        return
    url_key = _env_key(provider, "URL")
    if os.environ.get(url_key) != url:
        os.environ[url_key] = url

    headers: Dict[str, str] = OAuthManager.get_headers(normalized_user, provider) or {}

    auth_header = headers.get("Authorization") or headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token_value = auth_header.split(" ", 1)[1]
        if token_value and not os.environ.get("COMPOSIO_TOKEN"):
            os.environ["COMPOSIO_TOKEN"] = token_value

    connected_account = headers.get("X-Connected-Account-Id") or headers.get("x-connected-account-id")
    if connected_account:
        env_key = _env_key(provider, "CONNECTED_ACCOUNT_ID")
        if os.environ.get(env_key) != connected_account:
            os.environ[env_key] = connected_account

    auth_config_id = headers.get("X-Auth-Config-Id") or headers.get("x-auth-config-id")
    if auth_config_id:
        env_key = _env_key(provider, "AUTH_CONFIG_ID")
        if os.environ.get(env_key) != auth_config_id:
            os.environ[env_key] = auth_config_id
