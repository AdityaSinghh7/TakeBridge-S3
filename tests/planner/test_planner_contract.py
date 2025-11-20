from __future__ import annotations

import importlib
import json

import pytest

from mcp_agent.agent import Budget, BudgetSnapshot, execute_mcp_task


TEST_USER = "test-user"


class FinishLLM:
    def __init__(self, summary: str) -> None:
        self.summary = summary

    def generate_plan(self, context):
        return {
            "text": json.dumps(
                {
                    "type": "finish",
                    "summary": self.summary,
                    "reasoning": "Task can be marked complete.",
                }
            ),
            "response": None,
        }


def test_budget_defaults_and_snapshot():
    budget = Budget()
    tracker_snapshot = BudgetSnapshot()
    assert budget.max_steps == 10
    assert budget.max_tool_calls == 30
    assert tracker_snapshot.max_llm_cost_usd == pytest.approx(0.50, rel=1e-3)


def test_execute_mcp_task_returns_structured_result(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("mcp_agent.knowledge.search.search_tools", lambda **kwargs: [])
    result = execute_mcp_task("noop task", user_id=TEST_USER, llm=FinishLLM("All done."))
    assert result["success"] is True
    assert result["final_summary"] == "All done."
    assert result["budget_usage"]["max_steps"] == 10


def test_planner_module_exports_contract():
    module = importlib.import_module("mcp_agent.agent")
    assert hasattr(module, "execute_mcp_task")
    assert hasattr(module, "Budget")
    assert hasattr(module, "BudgetSnapshot")


def test_execute_mcp_task_runs_tool_search(monkeypatch: pytest.MonkeyPatch):
    captured = {}

    def fake_search(**kwargs):
        captured.update(kwargs)
        return [{"provider": "slack", "tool": "send_message", "short_description": "foo", "available": True}]

    monkeypatch.setattr("mcp_agent.knowledge.search.search_tools", fake_search)
    result = execute_mcp_task("send slack update", user_id=TEST_USER, llm=FinishLLM("done"))
    assert captured["query"] == "send slack update"
    assert result["logs"][0]["event"] == "mcp.planner.started"
    event_names = [log["event"] for log in result["logs"]]
    assert "mcp.search.run" in event_names


def test_execute_mcp_task_accepts_custom_llm(monkeypatch: pytest.MonkeyPatch):
    class StubLLM:
        def generate_plan(self, context):
            context.record_event("custom.llm.called", {})
            return {"messages": [], "text": "done", "response": None}

    monkeypatch.setattr("mcp_agent.knowledge.search.search_tools", lambda **kwargs: [])
    result = execute_mcp_task("task", user_id=TEST_USER, llm=StubLLM())
    assert "custom.llm.called" in [log["event"] for log in result["logs"]]


def test_execute_mcp_task_without_llm_returns_parse_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("mcp_agent.knowledge.search.search_tools", lambda **kwargs: [])
    result = execute_mcp_task("task without llm", user_id=TEST_USER)
    assert result["success"] is False
    assert result["error"] == "planner_llm_disabled"
    assert result.get("error_code") == "planner_llm_disabled"


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
                            "reasoning": "Send a Slack message once.",
                        }
                    )
                }
            return {
                "text": json.dumps(
                    {
                        "type": "finish",
                        "summary": "done",
                        "reasoning": "Slack tool has been called.",
                    }
                )
            }

    tool_llm = ToolLLM()

    monkeypatch.setattr("mcp_agent.knowledge.search.search_tools", lambda **kwargs: [])

    def fake_call_direct_tool(context, provider, tool, payload):
        context.record_event("test.tool.called", {"payload": payload})
        context.summarize_tool_output(f"{provider}.{tool}", {"payload": payload}, force=True)
        return {"successful": True, "data": payload}

    monkeypatch.setattr("mcp_agent.agent.orchestrator.dispatch_tool", fake_call_direct_tool)

    # Provide minimal index so SLACK_SEND_MESSAGE passes validation.
    from mcp_agent.knowledge.models import ParameterSpec, ToolSpec
    from mcp_agent.knowledge.index import ToolboxIndex

    parameter = ParameterSpec(
        name="text",
        kind="positional_or_keyword",
        required=True,
        has_default=False,
        annotation="str",
        description=None,
    )
    tool = ToolSpec(
        provider="slack",
        name="SLACK_SEND_MESSAGE",
        description="Send slack message",
        short_description="Send slack message",
        docstring="",
        python_name="SLACK_SEND_MESSAGE",
        python_signature="SLACK_SEND_MESSAGE(text: str)",
        parameters=[parameter],
        mcp_tool_name="SLACK_SEND_MESSAGE",
        oauth_provider="slack",
        oauth_required=True,
        available=True,
    )
    index = ToolboxIndex(providers={}, tools_by_id={tool.tool_id: tool})
    monkeypatch.setattr("mcp_agent.knowledge.builder.get_index", lambda *args, **kwargs: index)

    result = execute_mcp_task("tool command", user_id=TEST_USER, llm=tool_llm)
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
                return {
                    "text": json.dumps(
                        {
                            "type": "sandbox",
                            "code": "return {'status': 'ok'}",
                            "reasoning": "Run simple sandbox to return ok.",
                        }
                    )
                }
            return {
                "text": json.dumps(
                    {
                        "type": "finish",
                        "summary": "sandbox done",
                        "reasoning": "Sandbox has completed.",
                    }
                )
            }

    monkeypatch.setattr("mcp_agent.knowledge.search.search_tools", lambda **kwargs: [])

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
        context.append_raw_output(
            f"sandbox.{label}",
            {
                "type": "sandbox",
                "label": label,
                "success": True,
                "result": {"status": "ok"},
                "logs": [],
                "error": None,
                "timed_out": False,
            },
        )
        context.summarize_sandbox_output("sandbox_test", {"status": "ok"}, force=True)
        return result

    monkeypatch.setattr("mcp_agent.execution.sandbox.run_python_plan", fake_run_sandbox_plan)

    result = execute_mcp_task("sandbox command", user_id=TEST_USER, llm=SandboxLLM())
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
                        "reasoning": "Looping tool call to test budget.",
                    }
                )
            }

    monkeypatch.setattr("mcp_agent.knowledge.search.search_tools", lambda **kwargs: [])
    monkeypatch.setattr(
        "mcp_agent.actions.dispatcher.dispatch_tool",
        lambda **kwargs: {"successful": True},
    )

    # Provide minimal index so SLACK_SEND_MESSAGE passes validation.
    from mcp_agent.knowledge.models import ParameterSpec, ToolSpec
    from mcp_agent.knowledge.index import ToolboxIndex

    parameter = ParameterSpec(
        name="text",
        kind="positional_or_keyword",
        required=True,
        has_default=False,
        annotation="str",
        description=None,
    )
    tool = ToolSpec(
        provider="slack",
        name="SLACK_SEND_MESSAGE",
        description="Send slack message",
        short_description="Send slack message",
        docstring="",
        python_name="SLACK_SEND_MESSAGE",
        python_signature="SLACK_SEND_MESSAGE(text: str)",
        parameters=[parameter],
        mcp_tool_name="SLACK_SEND_MESSAGE",
        oauth_provider="slack",
        oauth_required=True,
        available=True,
    )
    index = ToolboxIndex(providers={}, tools_by_id={tool.tool_id: tool})
    monkeypatch.setattr("mcp_agent.knowledge.builder.get_index", lambda *args, **kwargs: index)

    result = execute_mcp_task("budget loop", user_id=TEST_USER, llm=LoopLLM(), budget=Budget(max_steps=1))
    assert result["success"] is False
    assert result["error"] == "budget_exceeded"
