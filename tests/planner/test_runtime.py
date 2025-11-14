from __future__ import annotations

import json
from types import SimpleNamespace
from typing import List

from mcp_agent.planner.actions import call_direct_tool
from mcp_agent.planner.budget import Budget
from mcp_agent.planner.context import PlannerContext
from mcp_agent.planner.runtime import PlannerRuntime


class FakeLLM:
    def __init__(self, commands: List[dict]) -> None:
        self._commands = commands
        self.calls = 0

    def generate_plan(self, context: PlannerContext) -> dict:
        if self.calls >= len(self._commands):
            raise AssertionError("LLM called more times than scripted.")
        command = self._commands[self.calls]
        self.calls += 1
        return {"text": json.dumps(command), "messages": [], "response": None}


def test_planner_runtime_executes_tool_then_finishes(monkeypatch, tmp_path):
    context = PlannerContext(task="Send update", user_id="tester", budget=Budget())
    context.summary_root = tmp_path
    llm = FakeLLM(
        [
            {"type": "tool", "provider": "slack", "tool": "SLACK_SEND_MESSAGE", "payload": {"text": "hi"}},
            {"type": "finish", "summary": "done"},
        ]
    )

    monkeypatch.setattr("mcp_agent.planner.runtime.perform_initial_discovery", lambda ctx: None)

    captured = {}

    def fake_call_direct_tool(context, provider, tool, payload):
        captured["provider"] = provider
        captured["tool"] = tool
        captured["payload"] = payload

    monkeypatch.setattr("mcp_agent.planner.runtime.call_direct_tool", fake_call_direct_tool)

    runtime = PlannerRuntime(context, llm=llm)
    result = runtime.run()

    assert result["success"] is True
    assert result["final_summary"] == "done"
    assert captured["provider"] == "slack"
    assert captured["tool"] == "SLACK_SEND_MESSAGE"
    assert captured["payload"] == {"text": "hi"}
    assert llm.calls == 2


def test_planner_runtime_runs_sandbox_and_summarizes(monkeypatch, tmp_path):
    context = PlannerContext(task="Process data", user_id="tester", budget=Budget())
    context.summary_root = tmp_path
    llm = FakeLLM(
        [
            {"type": "sandbox", "code": "result = {'ok': True}"},
            {"type": "finish", "summary": "complete"},
        ]
    )

    monkeypatch.setattr("mcp_agent.planner.runtime.perform_initial_discovery", lambda ctx: None)

    sandbox_calls = []

    def fake_run_sandbox_plan(context, code_body, **kwargs):
        sandbox_calls.append((code_body, kwargs.get("label")))
        sandbox_result = SimpleNamespace(
            success=True,
            result={"ok": True},
            logs=["log line"],
            error=None,
            timed_out=False,
        )
        label = kwargs.get("label", "sandbox")
        context.raw_outputs[f"sandbox.{label}"] = {
            "type": "sandbox",
            "label": label,
            "success": True,
            "result": sandbox_result.result,
            "logs": sandbox_result.logs,
            "error": sandbox_result.error,
            "timed_out": sandbox_result.timed_out,
        }
        context.summarize_sandbox_output(label, sandbox_result.result)
        return SimpleNamespace(result=sandbox_result, code_body=code_body)

    monkeypatch.setattr("mcp_agent.planner.runtime.run_sandbox_plan", fake_run_sandbox_plan)

    summaries = []

    def fake_summarize(self, label, payload, **kwargs):
        summaries.append((label, payload))
        return {}

    monkeypatch.setattr(PlannerContext, "summarize_sandbox_output", fake_summarize)

    runtime = PlannerRuntime(context, llm=llm)
    result = runtime.run()

    assert result["success"] is True
    assert sandbox_calls == [("result = {'ok': True}", "sandbox")]
    assert summaries == [("sandbox", {"ok": True})]


def test_planner_runtime_stops_when_budget_exceeded(monkeypatch):
    budget = Budget(max_steps=1)
    context = PlannerContext(task="Over budget", user_id="tester", budget=budget)
    context.budget_tracker.steps_taken = budget.max_steps

    monkeypatch.setattr("mcp_agent.planner.runtime.perform_initial_discovery", lambda ctx: None)

    runtime = PlannerRuntime(context, llm=FakeLLM(commands=[]))
    result = runtime.run()

    assert result["success"] is False
    assert result["error"] == "budget_exceeded"
    assert "Budget exceeded" in result["final_summary"]


def test_planner_runtime_handles_search_command(monkeypatch, tmp_path):
    context = PlannerContext(task="Need tools", user_id="tester", budget=Budget())
    context.summary_root = tmp_path
    llm = FakeLLM(
        [
            {"type": "search", "query": "gmail attachments", "detail_level": "full", "limit": 3},
            {"type": "finish", "summary": "done"},
        ]
    )

    monkeypatch.setattr("mcp_agent.planner.runtime.perform_initial_discovery", lambda ctx: None)

    performed = {}

    def fake_refined(context, query, detail_level, limit):
        performed["query"] = query
        context.add_search_results(
            [
                {
                    "provider": "gmail",
                    "tool": "GMAIL_SEARCH",
                    "available": True,
                    "short_description": query,
                    "score": 50,
                }
            ]
        )
        return context.search_results

    monkeypatch.setattr("mcp_agent.planner.runtime.perform_refined_discovery", fake_refined)

    runtime = PlannerRuntime(context, llm=llm)
    result = runtime.run()

    assert result["success"] is True
    assert performed["query"] == "gmail attachments"
    assert context.tool_menu[0]["qualified_name"] == "gmail.gmail_search"


def test_call_direct_tool_records_structured_output(monkeypatch, tmp_path):
    context = PlannerContext(task="Send update", user_id="tester", budget=Budget())
    context.summary_root = tmp_path

    class StubAgent:
        def call_tool(self, provider, tool, payload):
            return {"successful": True, "data": {"ok": True}}

    monkeypatch.setattr(
        "mcp_agent.planner.actions.MCPAgent.current",
        classmethod(lambda cls, user_id=None: StubAgent()),
    )

    response = call_direct_tool(
        context,
        provider="slack",
        tool="SLACK_SEND_MESSAGE",
        payload={"text": "hello"},
    )

    key = "tool.slack.SLACK_SEND_MESSAGE"
    assert key in context.raw_outputs
    entry = context.raw_outputs[key]
    assert entry["response"]["data"]["ok"] is True
    assert entry["payload"] == {"text": "hello"}
    assert response["successful"] is True
