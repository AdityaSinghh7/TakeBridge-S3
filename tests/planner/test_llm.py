from __future__ import annotations

from types import SimpleNamespace

from mcp_agent.planner.budget import Budget
from mcp_agent.planner.context import PlannerContext
from mcp_agent.planner.llm import PlannerLLM


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.output = [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            }
        ]
        self.usage = {"input_tokens": 100, "output_tokens": 20, "input_cached_tokens": 0}


class FakeClient:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls = []

    def create_response(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def test_planner_llm_calls_openai_and_records_cost(monkeypatch):
    context = PlannerContext(task="demo task", user_id="tester", budget=Budget())
    context.add_search_results(
        [{"provider": "slack", "tool": "send_message", "short_description": "post", "available": True}]
    )
    recorded = {}

    def fake_record(model, source, response, logger=None):
        recorded["model"] = model
        recorded["source"] = source

    context.token_tracker = SimpleNamespace(record_response=fake_record, total_cost_usd=0.0)
    client = FakeClient(FakeResponse("Plan actions now."))
    llm = PlannerLLM(client=client, enabled=True)

    result = llm.generate_plan(context)

    assert client.calls, "expected OpenAI client to be invoked"
    assert recorded["model"] == "o4-mini"
    assert "Plan actions now." in result["text"]
    assert "mcp.llm.completed" in [log["event"] for log in context.logs]


def test_planner_llm_respects_disabled_flag(monkeypatch):
    context = PlannerContext(task="demo task", user_id="tester", budget=Budget())
    llm = PlannerLLM(enabled=False)
    result = llm.generate_plan(context)
    assert result["response"] is None
    assert "mcp.llm.skipped" in [log["event"] for log in context.logs]


def test_planner_state_includes_gmail_search_schema(monkeypatch, tmp_path):
    """Test that PLANNER_STATE_JSON includes gmail.gmail_search with correct output_schema."""
    from mcp_agent.toolbox.load_io_specs import ensure_io_specs_loaded
    from mcp_agent.toolbox import output_schema_loader
    import json
    from pathlib import Path

    # Set up a fake schema file
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

    # Load IO specs and schemas
    ensure_io_specs_loaded()
    output_schema_loader.load_output_schemas()

    # Create PlannerContext and add search results with gmail_search
    context = PlannerContext(task="Search Gmail for emails", user_id="tester", budget=Budget())
    context.summary_root = tmp_path

    # Add a search result entry that would come from search_tools (full descriptor)
    gmail_search_entry = {
        "provider": "gmail",
        "tool": "gmail_search",
        "tool_id": "gmail.gmail_search",
        "server": "gmail",
        "module": "sandbox_py.servers.gmail",
        "function": "gmail_search",
        "py_module": "sandbox_py.servers.gmail",
        "py_name": "gmail_search",
        "call_signature": "gmail.gmail_search(query: str, ...)",
        "description": "Search Gmail inbox",
        "short_description": "Search Gmail",
        "available": True,
        "score": 5.0,
        "path": "sandbox_py/servers/gmail/gmail_search.py",
        "qualified_name": "gmail.gmail_search",
        "input_params": {
            "required": [{"name": "query", "type": "str"}],
            "optional": [],
        },
            "output_schema": {
                "type": "object",
                "properties": {
                    "messages": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "messageId": {"type": "string"},
                                "sender": {"type": "string"},
                            },
                        },
                    },
                    "nextPageToken": {"type": "string"},
                    "resultSizeEstimate": {"type": "integer"},
                },
                "required": [],
            },
        "output_schema_pretty": ["- messages: array", "- nextPageToken: string", "- resultSizeEstimate: integer"],
    }

    context.add_search_results([gmail_search_entry])

    # Build planner state
    from mcp_agent.planner.budget import BudgetSnapshot

    snapshot = context.budget_tracker.snapshot()
    state = context.build_planner_state(snapshot)

    # Verify search_results includes gmail.gmail_search with correct schema
    assert "search_results" in state, "planner state should have search_results"
    search_results = state["search_results"]
    assert isinstance(search_results, list), "search_results should be a list"

    gmail_entry = next((r for r in search_results if r.get("tool_id") == "gmail.gmail_search"), None)
    assert gmail_entry is not None, "search_results should include gmail.gmail_search"

    # Verify slim view: essential fields present
    assert "tool_id" in gmail_entry, "slim view should have tool_id"
    assert "provider" in gmail_entry, "slim view should have provider"
    assert "server" in gmail_entry, "slim view should have server"
    assert "py_module" in gmail_entry, "slim view should have py_module"
    assert "py_name" in gmail_entry, "slim view should have py_name"
    assert "call_signature" in gmail_entry, "slim view should have call_signature"
    assert "description" in gmail_entry, "slim view should have description"
    
    # Verify slim view: redundant fields dropped
    assert "path" not in gmail_entry, "slim view should not have path"
    assert "qualified_name" not in gmail_entry, "slim view should not have qualified_name"
    assert "short_description" not in gmail_entry, "slim view should not have short_description"
    assert "available" not in gmail_entry, "slim view should not have available"
    assert "score" not in gmail_entry, "slim view should not have score"
    assert "tool" not in gmail_entry, "slim view should not have tool"
    assert "module" not in gmail_entry, "slim view should not have module (use py_module)"
    assert "function" not in gmail_entry, "slim view should not have function (use py_name)"

    # Verify input_params_pretty is NOT present
    assert "input_params_pretty" not in gmail_entry, "slim view should not have input_params_pretty"
    # Verify input_params IS present
    assert "input_params" in gmail_entry, "slim view should have input_params"
    # Verify input_params is passed through correctly
    assert gmail_entry["input_params"]["required"][0]["name"] == "query"

    # Verify output_fields is present instead of output_schema
    assert "output_fields" in gmail_entry, "gmail_search entry should have output_fields"
    assert "output_schema" not in gmail_entry, "slim view should not have output_schema"
    assert "output_schema_pretty" not in gmail_entry, "slim view should not have output_schema_pretty"
    
    # Verify output_fields contains expected entries (leaf-level fields only)
    output_fields = gmail_entry["output_fields"]
    assert isinstance(output_fields, list), "output_fields should be a list"
    # Should have leaf-level fields, not intermediate objects
    assert any("messages" in f for f in output_fields), "output_fields should include messages fields"
    assert any("nextPageToken" in f for f in output_fields), "output_fields should include nextPageToken"
    assert any("resultSizeEstimate" in f for f in output_fields), "output_fields should include resultSizeEstimate"
    
    # Verify full descriptor still available internally
    full_entry = next((r for r in context.search_results if r.get("tool_id") == "gmail.gmail_search"), None)
    assert full_entry is not None, "Full descriptor should still be in context.search_results"
    assert "path" in full_entry, "Full descriptor should have path"
    assert "score" in full_entry, "Full descriptor should have score"
