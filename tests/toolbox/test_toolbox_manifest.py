from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mcp_agent.toolbox import builder as builder_module
from mcp_agent.toolbox.builder import ToolboxBuilder, invalidate_manifest_cache
from mcp_agent.toolbox.models import ParameterSpec, ProviderSpec, ToolSpec, ToolboxManifest
from mcp_agent.toolbox import search as search_module


@pytest.fixture(autouse=True)
def clear_manifest_cache():
    invalidate_manifest_cache()
    yield
    invalidate_manifest_cache()


def test_toolbox_builder_persists_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(builder_module, "init_registry", lambda user_id: None)
    monkeypatch.setattr(builder_module, "is_registered", lambda provider, user_id: True)
    monkeypatch.setattr(builder_module, "registry_version", lambda user_id: 1)
    monkeypatch.setattr(
        builder_module.OAuthManager,
        "is_authorized",
        classmethod(lambda cls, provider, user_id: provider == "slack"),
    )
    monkeypatch.setattr(
        builder_module.OAuthManager,
        "get_mcp_url",
        classmethod(lambda cls, user_id, provider: f"https://{provider}.example.com"),
    )

    builder = ToolboxBuilder(user_id="tester", base_dir=tmp_path)
    manifest = builder.build()

    providers = {prov.provider: prov for prov in manifest.providers}
    assert "slack" in providers
    assert "gmail" in providers
    slack = providers["slack"]
    slack_actions = {tool.name: tool for tool in slack.actions}
    assert "slack_post_message" in slack_actions
    post_message = slack_actions["slack_post_message"]
    param_names = [param.name for param in post_message.parameters]
    assert "channel" in param_names

    stats = builder.persist(manifest)

    manifest_path = tmp_path / "manifest.json"
    slack_tool_path = (
        tmp_path / "providers" / "slack" / "tools" / "slack_post_message.json"
    )
    assert manifest_path.exists()
    assert slack_tool_path.exists()
    assert stats["manifest"] == 1
    assert stats.get("py_files", 0) >= 1

    sandbox = tmp_path / "sandbox_py"
    client_py = sandbox / "client.py"
    slack_py = sandbox / "servers" / "slack" / "slack_post_message.py"
    gmail_py = sandbox / "servers" / "gmail" / "gmail_send_email.py"
    assert client_py.exists()
    assert "async def call_tool" in client_py.read_text()
    assert slack_py.exists()
    slack_source = slack_py.read_text()
    assert "async def slack_post_message" in slack_source
    assert "await call_tool('slack'" in slack_source
    assert gmail_py.exists()
    assert "recipient_email" in gmail_py.read_text()


def test_get_manifest_caches_by_registry_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    state = {"version": 1, "builds": 0}

    class StubBuilder:
        def __init__(self, *, user_id=None, base_dir=None):
            self.user_id = user_id
            self.base_dir = base_dir

        def build(self) -> ToolboxManifest:
            state["builds"] += 1
            return ToolboxManifest(
                user_id=self.user_id,
                generated_at="2025-01-01T00:00:00+00:00",
                registry_version=state["version"],
                fingerprint=f"fp-{state['builds']}",
                providers=[],
            )

        def persist(self, manifest: ToolboxManifest) -> dict[str, Any]:
            return {"manifest": 1}

    monkeypatch.setattr(builder_module, "ToolboxBuilder", StubBuilder)
    monkeypatch.setattr(builder_module, "registry_version", lambda user_id: state["version"])

    manifest1 = builder_module.get_manifest(
        user_id="tester", persist=False, base_dir=tmp_path
    )
    assert state["builds"] == 1
    manifest2 = builder_module.get_manifest(
        user_id="tester", persist=False, base_dir=tmp_path
    )
    assert manifest2 is manifest1
    assert state["builds"] == 1
    state["version"] = 2
    manifest3 = builder_module.get_manifest(
        user_id="tester", persist=False, base_dir=tmp_path
    )
    assert state["builds"] == 2
    assert manifest3.registry_version == 2


def test_search_tools_respects_detail_levels(monkeypatch: pytest.MonkeyPatch):
    parameter = ParameterSpec(
        name="channel",
        kind="positional_or_keyword",
        required=True,
        has_default=False,
        annotation="str",
        description="Channel id",
    )
    tool = ToolSpec(
        provider="slack",
        name="send_message",
        description="Send a message to Slack",
        short_description="Send message",
        docstring="Description:\n  Send messages\nArgs:\n  channel: channel id",
        python_name="send_message",
        python_signature="send_message(channel: str)",
        parameters=[parameter],
        mcp_tool_name="SLACK_SEND_MESSAGE",
        oauth_provider="slack",
        oauth_required=True,
        available=True,
    )
    provider = ProviderSpec(
        provider="slack",
        display_name="Slack",
        authorized=True,
        registered=True,
        configured=True,
        mcp_url="https://slack.example.com",
        actions=[tool],
        last_refreshed="2025-01-01T00:00:00+00:00",
    )
    manifest = ToolboxManifest(
        user_id="tester",
        generated_at="2025-01-01T00:00:00+00:00",
        registry_version=1,
        fingerprint="fp",
        providers=[provider],
    )

    from mcp_agent.toolbox.index import ToolboxIndex

    monkeypatch.setattr(
        search_module,
        "get_index",
        lambda **_: ToolboxIndex.from_manifest(manifest),
    )

    names = search_module.search_tools(query="slack", detail_level="names", user_id="u")
    assert names[0]["qualified_name"] == "slack.send_message"

    summary = search_module.search_tools(
        query="message", detail_level="summary", user_id="u"
    )[0]
    assert summary["qualified_name"] == "slack.send_message"
    assert summary["short_description"] == "Send message"
    assert summary["path"].endswith("sandbox_py/servers/slack/send_message.py")
    assert summary["tool_id"] == "slack.send_message"
    assert summary["server"] == "slack"
    assert summary["py_module"] == "sandbox_py.servers.slack"
    assert summary["py_name"] == "send_message"

    full = search_module.search_tools(
        query="message", detail_level="full", user_id="u"
    )[0]
    assert full["provider_status"]["provider"] == "slack"

    with pytest.raises(ValueError):
        search_module.search_tools(query=None, detail_level="invalid", user_id="u")
