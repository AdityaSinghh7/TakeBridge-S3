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

    # Add a search result entry that would come from search_tools
    gmail_search_entry = {
        "provider": "gmail",
        "tool": "gmail_search",
        "tool_id": "gmail.gmail_search",
        "server": "gmail",
        "module": "sandbox_py.servers.gmail",
        "function": "gmail_search",
        "description": "Search Gmail inbox",
        "short_description": "Search Gmail",
        "available": True,
        "output_schema": {
            "type": "object",
            "properties": {
                "messages": {"type": "array"},
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

    # Verify output_schema is present and correct
    assert "output_schema" in gmail_entry, "gmail_search entry should have output_schema"
    output_schema = gmail_entry["output_schema"]
    assert "properties" in output_schema, "output_schema should have properties"
    assert "messages" in output_schema["properties"], "output_schema should have messages property"
    assert "nextPageToken" in output_schema["properties"], "output_schema should have nextPageToken property"
    assert "resultSizeEstimate" in output_schema["properties"], "output_schema should have resultSizeEstimate property"
