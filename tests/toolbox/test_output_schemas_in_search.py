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


def test_gmail_schemas_have_expected_shapes(monkeypatch, tmp_path):
    """Test that Gmail schemas have the expected inner Gmail payload shapes."""
    # Use the actual generated schema file if it exists, otherwise use a fixture
    schema_path = Path(__file__).resolve().parents[2] / "tool_output_schemas.generated.json"
    if not schema_path.exists():
        # Create a fixture with the expected structure
        fake_schema_path = tmp_path / "tool_output_schemas.generated.json"
        fake_schema_path.write_text(
            json.dumps(
                {
                    "gmail.gmail_search": {
                        "success": {
                            "type": "object",
                            "properties": {
                                "messages": {"type": "array"},
                                "nextPageToken": {"type": "string"},
                                "resultSizeEstimate": {"type": "integer"},
                            },
                            "required": [],
                        }
                    },
                    "gmail.gmail_send_email": {
                        "success": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "threadId": {"type": "string"},
                                "labelIds": {"type": "array"},
                            },
                            "required": ["id", "threadId", "labelIds"],
                        }
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("TB_TOOL_OUTPUT_SCHEMAS_PATH", str(fake_schema_path))
    else:
        monkeypatch.setenv("TB_TOOL_OUTPUT_SCHEMAS_PATH", str(schema_path))

    # Ensure IoToolSpecs are registered and schemas are loaded
    ensure_io_specs_loaded()

    # Test gmail_search schema
    spec = get_tool_spec("gmail", "gmail_search")
    assert spec is not None, "gmail.gmail_search spec should exist"
    assert spec.output_spec.data_schema_success is not None, "gmail_search should have output schema"
    props = spec.output_spec.data_schema_success["properties"]
    assert "messages" in props, "gmail_search schema should have 'messages' property"
    assert "nextPageToken" in props, "gmail_search schema should have 'nextPageToken' property"
    assert "resultSizeEstimate" in props, "gmail_search schema should have 'resultSizeEstimate' property"

    # Test gmail_send_email schema
    spec = get_tool_spec("gmail", "gmail_send_email")
    assert spec is not None, "gmail.gmail_send_email spec should exist"
    assert spec.output_spec.data_schema_success is not None, "gmail_send_email should have output schema"
    props = spec.output_spec.data_schema_success["properties"]
    assert "id" in props, "gmail_send_email schema should have 'id' property"
    assert "threadId" in props, "gmail_send_email schema should have 'threadId' property"
    assert "labelIds" in props, "gmail_send_email schema should have 'labelIds' property"


def test_search_tools_shows_gmail_schema_to_planner(monkeypatch, tmp_path):
    """Test that search_tools returns correct output_schema and output_schema_pretty for planner."""
    fake_schema_path = tmp_path / "tool_output_schemas.generated.json"
    fake_schema_path.write_text(
        json.dumps(
            {
                "gmail.gmail_search": {
                    "success": {
                        "type": "object",
                        "properties": {
                            "messages": {"type": "array"},
                            "nextPageToken": {"type": "string"},
                            "resultSizeEstimate": {"type": "integer"},
                        },
                        "required": [],
                    }
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("TB_TOOL_OUTPUT_SCHEMAS_PATH", str(fake_schema_path))

    # Trigger IO spec loading and schema merge
    ensure_io_specs_loaded()
    output_schema_loader.load_output_schemas()

    _install_minimal_gmail_search_index(monkeypatch)

    results = search_tools(query="gmail_search", user_id="dev-local")
    assert results, "search_tools should return results"

    entry = next((r for r in results if r["tool_id"].endswith("gmail_search")), None)
    assert entry is not None, "Should find gmail_search in results"

    # Verify output_schema structure
    output_schema = entry.get("output_schema")
    assert output_schema is not None, "entry should have output_schema"
    assert "properties" in output_schema, "output_schema should have properties"
    assert "messages" in output_schema["properties"], "output_schema should have messages property"
    assert "nextPageToken" in output_schema["properties"], "output_schema should have nextPageToken property"
    assert "resultSizeEstimate" in output_schema["properties"], "output_schema should have resultSizeEstimate property"

    # Verify output_schema_pretty contains expected fields
    pretty = entry.get("output_schema_pretty")
    assert pretty is not None, "entry should have output_schema_pretty"
    assert isinstance(pretty, list), "output_schema_pretty should be a list"
    pretty_text = "\n".join(pretty)
    assert "messages" in pretty_text, "output_schema_pretty should mention 'messages'"
    assert "nextPageToken" in pretty_text or "nextPageToken" in str(pretty), "output_schema_pretty should mention 'nextPageToken'"
