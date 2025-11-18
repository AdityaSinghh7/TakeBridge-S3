from __future__ import annotations

import json
from pathlib import Path

from mcp_agent.toolbox.load_io_specs import ensure_io_specs_loaded
from mcp_agent.toolbox.registry import get_tool_spec
from mcp_agent.toolbox.search import search_tools
from mcp_agent.toolbox import output_schema_loader
from mcp_agent.toolbox.models import ParameterSpec, ProviderSpec, ToolSpec, ToolboxManifest
from mcp_agent.toolbox.index import ToolboxIndex


def _install_minimal_gmail_search_index(monkeypatch):
    """Install a minimal ToolboxIndex with a single gmail_search tool."""
    parameter = ParameterSpec(
        name="query",
        kind="positional_or_keyword",
        required=True,
        has_default=False,
        annotation="str",
        description=None,
    )
    tool = ToolSpec(
        provider="gmail",
        name="gmail_search",
        description="Search gmail",
        short_description="Search gmail",
        docstring="",
        python_name="gmail_search",
        python_signature="gmail_search()",
        parameters=[parameter],
        mcp_tool_name="GMAIL_FETCH_EMAILS",
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
    monkeypatch.setattr("mcp_agent.toolbox.search.get_index", lambda *args, **kwargs: index)


def test_gmail_search_output_schema_loaded(monkeypatch, tmp_path):
    # Point the loader at a deterministic fake generated schema file.
    fake_schema_path = tmp_path / "tool_output_schemas.generated.json"
    fake_schema_path.write_text(
        json.dumps(
            {
                "gmail.gmail_search": {
                    "success": {
                        "type": "object",
                        "properties": {
                            "messages": {"type": "array"},
                        },
                        "required": ["messages"],
                    }
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("TB_TOOL_OUTPUT_SCHEMAS_PATH", str(fake_schema_path))

    # Register IoToolSpecs and then merge the fake output schema explicitly.
    ensure_io_specs_loaded()
    output_schema_loader.load_output_schemas()
    _install_minimal_gmail_search_index(monkeypatch)

    spec = get_tool_spec("gmail", "gmail_search")
    assert spec is not None
    schema = spec.output_spec.data_schema_success
    assert schema is not None
    assert schema["properties"]["messages"]["type"] == "array"


def test_search_tools_uses_iospec_for_output_schema(monkeypatch, tmp_path):
    fake_schema_path = tmp_path / "tool_output_schemas.generated.json"
    fake_schema_path.write_text(
        json.dumps(
            {
                "gmail.gmail_search": {
                    "success": {
                        "type": "object",
                        "properties": {"messages": {"type": "array"}},
                        "required": ["messages"],
                    }
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("TB_TOOL_OUTPUT_SCHEMAS_PATH", str(fake_schema_path))

    # Trigger IO spec loading and schema merge.
    ensure_io_specs_loaded()
    output_schema_loader.load_output_schemas()

    _install_minimal_gmail_search_index(monkeypatch)

    results = search_tools(query="gmail_search", user_id="test-user")
    assert results
    entry = next(r for r in results if r["tool_id"].endswith("gmail_search"))

    assert entry.get("output_schema")
    pretty = entry.get("output_schema_pretty")
    assert pretty
    assert any("messages" in line for line in pretty)
