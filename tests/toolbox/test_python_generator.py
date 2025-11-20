from __future__ import annotations

from pathlib import Path

from mcp_agent.knowledge.models import ParameterSpec, ProviderSpec, ToolSpec, ToolboxManifest
from mcp_agent.knowledge.python_generator import PythonGenerator


def _build_manifest() -> ToolboxManifest:
    params = [
        ParameterSpec(
            name="channel",
            kind="positional_or_keyword",
            required=True,
            annotation="str",
            description="Slack channel (e.g., #ops).",
        ),
        ParameterSpec(
            name="text",
            kind="positional_or_keyword",
            required=False,
            has_default=True,
            default="",
            annotation="str",
            description="Primary message body.",
        ),
    ]
    tool = ToolSpec(
        provider="slack",
        name="slack_post_message",
        description="Post a message into Slack.",
        short_description="Send Slack message.",
        docstring="Send a message via Slack.",
        python_name="slack_post_message",
        python_signature="(channel: str, text: str = '')",
        parameters=params,
        mcp_tool_name="SLACK_SEND_MESSAGE",
        available=True,
        structured_params=[],
        list_params={},
    )
    provider = ProviderSpec(
        provider="slack",
        display_name="Slack",
        authorized=True,
        registered=True,
        configured=True,
        mcp_url="https://fake/slack",
        actions=[tool],
        last_refreshed="2024-01-01T00:00:00Z",
    )
    manifest = ToolboxManifest(
        user_id="tester",
        generated_at="2024-01-01T00:00:00Z",
        registry_version=1,
        fingerprint="abc123",
        providers=[provider],
    )
    return manifest


def test_python_generator_produces_async_wrappers(tmp_path: Path):
    manifest = _build_manifest()
    generator = PythonGenerator(manifest, tmp_path)
    stats = generator.write()
    assert stats["py_files"] >= 3  # package init + client + provider module

    wrapper_path = tmp_path / "sandbox_py" / "servers" / "slack" / "slack_post_message.py"
    content = wrapper_path.read_text(encoding="utf-8")
    assert "async def slack_post_message" in content
    assert "return await call_tool('slack', 'SLACK_SEND_MESSAGE', payload)" in content
    assert '"""' in content
    assert "channel (str): Slack channel (e.g., #ops)." in content


def test_client_template_exposes_registration(tmp_path: Path):
    manifest = _build_manifest()
    generator = PythonGenerator(manifest, tmp_path)
    generator.write()
    client_path = tmp_path / "sandbox_py" / "client.py"
    content = client_path.read_text(encoding="utf-8")
    assert "def register_tool_caller" in content
    assert "async def call_tool" in content
    assert "sanitize_payload" in content
