from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from mcp_agent.agent.budget import Budget
from mcp_agent.agent.orchestrator import AgentOrchestrator
from mcp_agent.agent.state import AgentState
from mcp_agent.core.context import AgentContext


class FakeLLM:
    def __init__(self, commands):
        self._commands = commands
        self.calls = 0

    def generate_plan(self, state: AgentState) -> dict:
        if self.calls >= len(self._commands):
            raise AssertionError("LLM called more times than scripted.")
        command = self._commands[self.calls]
        self.calls += 1
        return {"text": json.dumps(command), "messages": [], "response": None}


@pytest.fixture(autouse=True)
def no_inventory(monkeypatch):
    monkeypatch.setattr(
        "mcp_agent.agent.orchestrator.AgentOrchestrator._load_inventory",
        lambda self: None,
    )


def make_runtime(task: str, *, budget: Budget | None = None, tmp_path=None, llm=None):
    ctx = AgentContext.create(user_id="tester")
    state = AgentState(
        task=task,
        user_id="tester",
        request_id="test-run",
        budget=budget or Budget(),
    )
    if tmp_path is not None:
        state.summary_root = tmp_path
    runtime = AgentOrchestrator(ctx, state, llm=llm or FakeLLM(commands=[]))
    return runtime, state


def test_orchestrator_executes_tool_then_finishes(monkeypatch, tmp_path):
    llm = FakeLLM(
        [
            {
                "type": "tool",
                "provider": "slack",
                "tool": "SLACK_SEND_MESSAGE",
                "payload": {"text": "hi"},
                "reasoning": "Call slack send message once.",
            },
            {"type": "finish", "summary": "done", "reasoning": "complete"},
        ]
    )

    captured = {}

    def fake_dispatch_tool(*, context, provider, tool, payload):
        captured["provider"] = provider
        captured["tool"] = tool
        captured["payload"] = payload
        return {"successful": True, "data": {}}

    monkeypatch.setattr("mcp_agent.actions.dispatcher.dispatch_tool", fake_dispatch_tool)

    from mcp_agent.knowledge.models import ParameterSpec, ProviderSpec, ToolSpec, ToolboxManifest
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
        description="",
        short_description="",
        docstring="",
        python_name="SLACK_SEND_MESSAGE",
        python_signature="SLACK_SEND_MESSAGE(text: str)",
        parameters=[parameter],
        mcp_tool_name="SLACK_SEND_MESSAGE",
        oauth_provider="slack",
        oauth_required=True,
        available=True,
    )
    provider = ProviderSpec(
        provider="slack",
        display_name="Slack",
        authorized=True,
        registered=True,
        configured=True,
        mcp_url="https://slack",
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
    monkeypatch.setattr("mcp_agent.knowledge.builder.get_index", lambda *_, **__: index)

    runtime, _state = make_runtime("Send update", tmp_path=tmp_path, llm=llm)
    result = runtime.run()

    assert result["success"] is True
    assert result["final_summary"] == "done"
    assert captured == {"provider": "slack", "tool": "SLACK_SEND_MESSAGE", "payload": {"text": "hi"}}


def test_orchestrator_runs_sandbox(monkeypatch, tmp_path):
    llm = FakeLLM(
        [
            {"type": "sandbox", "code": "result = {'ok': True}", "reasoning": "do work"},
            {"type": "finish", "summary": "complete", "reasoning": "sandbox done"},
        ]
    )

    def fake_run_python_plan(*, context, code_body, label):
        return SimpleNamespace(
            success=True,
            result={"successful": True, "data": {"ok": True}},
            logs=["log"],
            error=None,
            timed_out=False,
        )

    monkeypatch.setattr("mcp_agent.execution.sandbox.run_python_plan", fake_run_python_plan)

    runtime, _state = make_runtime("Process", tmp_path=tmp_path, llm=llm)
    result = runtime.run()

    assert result["success"] is True
    assert result["final_summary"] == "complete"


def test_orchestrator_budget_exceeded(monkeypatch):
    runtime, state = make_runtime("Over budget", budget=Budget(max_steps=1))
    state.budget_tracker.steps_taken = state.budget_tracker.budget.max_steps
    result = runtime.run()
    assert result["success"] is False
    assert result["error"] == "budget_exceeded"


def test_orchestrator_handles_search(monkeypatch, tmp_path):
    llm = FakeLLM(
        [
            {"type": "search", "query": "gmail attachments", "reasoning": "discover"},
            {"type": "finish", "summary": "done", "reasoning": "search complete"},
        ]
    )

    monkeypatch.setattr(
        "mcp_agent.knowledge.search.search_tools",
        lambda **_: [
            {
                "tool_id": "gmail.gmail_search",
                "provider": "gmail",
                "server": "gmail",
                "py_name": "gmail_search",
                "input_params": {"required": []},
            }
        ],
    )
    monkeypatch.setattr(
        "mcp_agent.knowledge.views.get_deep_view",
        lambda ctx, tool_ids: [
            {
                "tool_id": "gmail.gmail_search",
                "provider": "gmail",
                "server": "gmail",
                "py_name": "gmail_search",
                "input_params": {"required": []},
            }
        ],
    )
    monkeypatch.setattr(
        "mcp_agent.knowledge.builder.get_index",
        lambda *_, **__: SimpleNamespace(get_tool=lambda *_: SimpleNamespace(provider="gmail", name="gmail_search", mcp_tool_name="GMAIL_SEARCH")),
    )

    runtime, _state = make_runtime("Need tools", tmp_path=tmp_path, llm=llm)
    result = runtime.run()
    assert result["success"] is True
    assert result["final_summary"] == "done"


def test_orchestrator_unknown_command(monkeypatch, tmp_path):
    llm = FakeLLM([{"type": "unknown", "foo": "bar"}])
    runtime, _state = make_runtime("Unknown", tmp_path=tmp_path, llm=llm)
    result = runtime.run()
    assert result["success"] is False
    assert result["error"] == "planner_unknown_command"
