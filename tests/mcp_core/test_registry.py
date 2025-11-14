from __future__ import annotations

from contextlib import nullcontext
import importlib
from typing import Dict, Tuple
import pytest

import mcp_agent.registry as registry_module


def _reload_registry(monkeypatch: pytest.MonkeyPatch):
    module = importlib.reload(registry_module)

    def fake_session_scope():
        return nullcontext(object())

    monkeypatch.setattr(module, "session_scope", fake_session_scope)

    db_urls: Dict[str, str | None] = {"slack": None, "gmail": None}

    def fake_get_active_mcp_for_provider(db, user_id: str, provider: str) -> Tuple[str | None, None]:
        return db_urls.get(provider), None

    monkeypatch.setattr(module, "get_active_mcp_for_provider", fake_get_active_mcp_for_provider)

    def fake_get_headers(cls, user_id: str, provider: str) -> dict[str, str]:
        return {"Authorization": f"Bearer-{user_id}-{provider}"}

    monkeypatch.setattr(
        module.OAuthManager,
        "get_headers",
        classmethod(fake_get_headers),
    )

    return module, db_urls


def test_init_registry_uses_env_fallback(monkeypatch: pytest.MonkeyPatch):
    registry, _ = _reload_registry(monkeypatch)
    monkeypatch.setenv("COMPOSIO_SLACK_URL", "https://env.slack")
    monkeypatch.setenv("COMPOSIO_GMAIL_URL", "https://env.gmail")
    monkeypatch.setenv("COMPOSIO_TOKEN", "env-token")

    registry.init_registry("user-1")

    assert registry.is_registered("slack", "user-1")
    assert registry.is_registered("gmail", "user-1")
    assert registry.registry_version("user-1") == 1

    registry.init_registry("user-1")
    assert registry.registry_version("user-1") == 1


def test_refresh_registry_detects_new_db_connection(monkeypatch: pytest.MonkeyPatch):
    registry, db_urls = _reload_registry(monkeypatch)
    monkeypatch.delenv("COMPOSIO_SLACK_URL", raising=False)
    monkeypatch.delenv("COMPOSIO_GMAIL_URL", raising=False)
    monkeypatch.delenv("COMPOSIO_TOKEN", raising=False)

    registry.init_registry("user-1")
    assert registry.registry_version("user-1") == 0
    assert not registry.is_registered("slack", "user-1")

    db_urls["slack"] = "https://db.slack"
    registry.refresh_registry_from_oauth("user-1")

    assert registry.is_registered("slack", "user-1")
    assert registry.registry_version("user-1") == 1


def test_registry_isolated_per_user(monkeypatch: pytest.MonkeyPatch):
    registry, _ = _reload_registry(monkeypatch)

    def per_user_mcp(db, user_id: str, provider: str) -> Tuple[str | None, None]:
        lookup = {
            ("alpha", "slack"): "https://alpha.slack",
            ("beta", "slack"): "https://beta.slack",
        }
        return lookup.get((user_id, provider)), None

    monkeypatch.setattr(registry, "get_active_mcp_for_provider", per_user_mcp)

    registry.init_registry("alpha")
    registry.init_registry("beta")

    alpha_client = registry.get_client("slack", "alpha")
    beta_client = registry.get_client("slack", "beta")

    assert alpha_client is not None
    assert beta_client is not None
    assert alpha_client is not beta_client
    assert registry.is_registered("slack", "alpha")
    assert registry.is_registered("slack", "beta")
    assert registry.registry_version("alpha") == 1
    assert registry.registry_version("beta") == 1
