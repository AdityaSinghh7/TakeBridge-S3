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
