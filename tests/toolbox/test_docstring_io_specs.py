from __future__ import annotations

from mcp_agent.knowledge.registry import get_tool_spec
from mcp_agent.knowledge.load_io_specs import ensure_io_specs_loaded
from mcp_agent.knowledge.search import search_tools
from mcp_agent.knowledge.models import ParameterSpec, ProviderSpec, ToolSpec, ToolboxManifest
from mcp_agent.knowledge.index import ToolboxIndex


def test_gmail_send_email_iospec_from_docstring():
    # Ensure IoToolSpecs are registered from action docstrings.
    ensure_io_specs_loaded()

    spec = get_tool_spec("gmail", "gmail_send_email")
    assert spec is not None

    pretty = spec.input_spec.pretty()
    assert "Input parameters:" in pretty
    # Basic sanity: key arguments appear in the pretty string.
    assert "to:" in pretty
    assert "subject:" in pretty
    assert "body:" in pretty
    # At least one parameter should be required.
    assert any(p.required for p in spec.input_spec.params)


def test_search_tools_uses_iospec_for_input_params(monkeypatch):
    # search_tools should surface IoToolSpec-derived input_params_pretty.
    ensure_io_specs_loaded()

    # Build a minimal manifest/index with a single gmail_send_email tool.
    parameter = ParameterSpec(
        name="to",
        kind="positional_or_keyword",
        required=True,
        has_default=False,
        annotation="str",
        description=None,
    )
    tool = ToolSpec(
        provider="gmail",
        name="gmail_send_email",
        description="Send gmail email",
        short_description="Send gmail email",
        docstring="",
        python_name="gmail_send_email",
        python_signature="gmail_send_email()",
        parameters=[parameter],
        mcp_tool_name="GMAIL_SEND_EMAIL",
        oauth_provider="gmail",
        oauth_required=True,
        available=True,
    )
    provider = ProviderSpec(
        provider="gmail",
        display_name="Gmail",
        authorized=True,
        registered=True,
        configured=True,
        mcp_url="https://gmail.example.com",
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
    index = ToolboxIndex.from_manifest(manifest)
    monkeypatch.setattr("mcp_agent.knowledge.search.get_index", lambda *args, **kwargs: index)

    results = search_tools(query="gmail_send_email", user_id="tester")
    assert results

    entry = next(r for r in results if r["tool_id"].endswith("gmail_send_email"))
    ip = entry.get("input_params_pretty")
    assert ip
    assert any("to:" in line for line in ip)
    assert any("subject:" in line for line in ip)
