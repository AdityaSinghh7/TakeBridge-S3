from __future__ import annotations

import importlib
import json

import pytest

from mcp_agent.planner import Budget, BudgetSnapshot, execute_mcp_task


class FinishLLM:
    def __init__(self, summary: str) -> None:
        self.summary = summary

    def generate_plan(self, context):
        return {
            "text": json.dumps({"type": "finish", "summary": self.summary}),
            "response": None,
        }


def test_budget_defaults_and_snapshot():
    budget = Budget()
    tracker_snapshot = BudgetSnapshot()
    assert budget.max_steps == 10
    assert budget.max_tool_calls == 30
    assert tracker_snapshot.max_llm_cost_usd == pytest.approx(0.50, rel=1e-3)


def test_execute_mcp_task_returns_structured_result(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("mcp_agent.planner.discovery.search_tools", lambda **kwargs: [])
    result = execute_mcp_task("noop task", llm=FinishLLM("All done."))
    assert result["success"] is True
    assert result["final_summary"] == "All done."
    assert result["budget_usage"]["max_steps"] == 10


def test_planner_module_exports_contract():
    module = importlib.import_module("mcp_agent.planner")
    assert hasattr(module, "execute_mcp_task")
    assert hasattr(module, "Budget")
    assert hasattr(module, "BudgetSnapshot")


def test_execute_mcp_task_runs_tool_search(monkeypatch: pytest.MonkeyPatch):
    captured = {}

    def fake_search(**kwargs):
        captured.update(kwargs)
        return [{"provider": "slack", "tool": "send_message", "short_description": "foo", "available": True}]

    monkeypatch.setattr("mcp_agent.planner.discovery.search_tools", fake_search)
    result = execute_mcp_task("send slack update", user_id="tester", llm=FinishLLM("done"))
    assert captured["query"] == "send slack update"
    assert result["logs"][0]["event"] == "mcp.planner.started"
    event_names = [log["event"] for log in result["logs"]]
    assert "mcp.search.run" in event_names


def test_execute_mcp_task_accepts_custom_llm(monkeypatch: pytest.MonkeyPatch):
    class StubLLM:
        def generate_plan(self, context):
            context.record_event("custom.llm.called", {})
            return {"messages": [], "text": "done", "response": None}

    monkeypatch.setattr("mcp_agent.planner.discovery.search_tools", lambda **kwargs: [])
    result = execute_mcp_task("task", llm=StubLLM())
    assert "custom.llm.called" in [log["event"] for log in result["logs"]]


def test_execute_mcp_task_without_llm_returns_parse_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("mcp_agent.planner.discovery.search_tools", lambda **kwargs: [])
    result = execute_mcp_task("task without llm")
    assert result["success"] is False
    assert result["error"] == "planner_parse_error"


def test_execute_tool_command(monkeypatch: pytest.MonkeyPatch):
    class ToolLLM:
        def __init__(self):
            self.calls = 0

        def generate_plan(self, context):
            self.calls += 1
            if self.calls == 1:
                return {
                    "text": json.dumps(
                        {
                            "type": "tool",
                            "provider": "slack",
                            "tool": "SLACK_SEND_MESSAGE",
                            "payload": {"channel": "#general", "text": "hi"},
                        }
                    )
                }
            return {"text": json.dumps({"type": "finish", "summary": "done"})}

    tool_llm = ToolLLM()

    monkeypatch.setattr("mcp_agent.planner.discovery.search_tools", lambda **kwargs: [])

    def fake_call_direct_tool(context, provider, tool, payload):
        context.record_event("test.tool.called", {"payload": payload})
        context.summarize_tool_output(f"{provider}.{tool}", {"payload": payload}, force=True)
        return {"successful": True, "data": payload}

    monkeypatch.setattr("mcp_agent.planner.runtime.call_direct_tool", fake_call_direct_tool)

    result = execute_mcp_task("tool command", llm=tool_llm)
    assert result["success"] is True
    assert "test.tool.called" in [log["event"] for log in result["logs"]]
    assert "mcp.summary.created" in [log["event"] for log in result["logs"]]


def test_execute_sandbox_command(monkeypatch: pytest.MonkeyPatch):
    class SandboxLLM:
        def __init__(self):
            self.calls = 0

        def generate_plan(self, context):
            self.calls += 1
            if self.calls == 1:
                return {"text": json.dumps({"type": "sandbox", "code": "return {'status': 'ok'}"})}
            return {"text": json.dumps({"type": "finish", "summary": "sandbox done"})}

    monkeypatch.setattr("mcp_agent.planner.discovery.search_tools", lambda **kwargs: [])

    def fake_run_sandbox_plan(context, code_body, label="sandbox"):
        context.record_event("test.sandbox.called", {})
        result = type(
            "fake",
            (),
            {
                "result": type(
                    "sandbox",
                    (),
                    {
                        "success": True,
                        "result": {"status": "ok"},
                        "logs": [],
                        "error": None,
                        "timed_out": False,
                    },
                )()
            },
        )()
        context.raw_outputs[f"sandbox.{label}"] = {
            "type": "sandbox",
            "label": label,
            "success": True,
            "result": {"status": "ok"},
            "logs": [],
            "error": None,
            "timed_out": False,
        }
        context.summarize_sandbox_output("sandbox_test", {"status": "ok"}, force=True)
        return result

    monkeypatch.setattr("mcp_agent.planner.runtime.run_sandbox_plan", fake_run_sandbox_plan)

    result = execute_mcp_task("sandbox command", llm=SandboxLLM())
    assert result["success"] is True
    assert "test.sandbox.called" in [log["event"] for log in result["logs"]]
    assert "mcp.summary.created" in [log["event"] for log in result["logs"]]


def test_budget_exceeded_stops_loop(monkeypatch: pytest.MonkeyPatch):
    class LoopLLM:
        def generate_plan(self, context):
            return {
                "text": json.dumps(
                    {
                        "type": "tool",
                        "provider": "slack",
                        "tool": "SLACK_SEND_MESSAGE",
                        "payload": {"channel": "#general", "text": "loop"},
                    }
                )
            }

    monkeypatch.setattr("mcp_agent.planner.discovery.search_tools", lambda **kwargs: [])
    monkeypatch.setattr(
        "mcp_agent.planner.runtime.call_direct_tool",
        lambda context, provider, tool, payload: {"successful": True},
    )

    result = execute_mcp_task("budget loop", llm=LoopLLM(), budget=Budget(max_steps=1))
    assert result["success"] is False
    assert result["error"] == "budget_exceeded"
