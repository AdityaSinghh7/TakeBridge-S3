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
            {
                "type": "tool",
                "provider": "slack",
                "tool": "SLACK_SEND_MESSAGE",
                "payload": {"text": "hi"},
                "reasoning": "Call slack send message once.",
            },
            {"type": "finish", "summary": "done", "reasoning": "Tool call is complete."},
        ]
    )

    monkeypatch.setattr("mcp_agent.planner.runtime.perform_initial_discovery", lambda ctx: None)

    captured = {}

    def fake_call_direct_tool(context, provider, tool, payload):
        captured["provider"] = provider
        captured["tool"] = tool
        captured["payload"] = payload

    monkeypatch.setattr("mcp_agent.planner.runtime.call_direct_tool", fake_call_direct_tool)

    # Provide a minimal toolbox index so validation passes.
    from mcp_agent.toolbox.models import ParameterSpec, ProviderSpec, ToolSpec, ToolboxManifest
    from mcp_agent.toolbox.index import ToolboxIndex

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
    provider = ProviderSpec(
        provider="slack",
        display_name="Slack",
        authorized=True,
        registered=True,
        configured=True,
        mcp_url="https://slack.example.com",
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
    monkeypatch.setattr("mcp_agent.planner.runtime.get_index", lambda *args, **kwargs: index)

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
            {
                "type": "sandbox",
                "code": "result = {'ok': True}",
                "reasoning": "Run a simple sandbox script.",
            },
            {"type": "finish", "summary": "complete", "reasoning": "Sandbox work done."},
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
        context.append_raw_output(
            f"sandbox.{label}",
            {
                "type": "sandbox",
                "label": label,
                "success": True,
                "result": sandbox_result.result,
                "logs": sandbox_result.logs,
                "error": sandbox_result.error,
                "timed_out": sandbox_result.timed_out,
            },
        )
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
            {
                "type": "search",
                "query": "gmail attachments",
                "detail_level": "full",
                "limit": 3,
                "reasoning": "Discover Gmail tools for attachments.",
            },
            {"type": "finish", "summary": "done", "reasoning": "Search completed."},
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
        classmethod(lambda cls, user_id: StubAgent()),
    )

    response = call_direct_tool(
        context,
        provider="slack",
        tool="SLACK_SEND_MESSAGE",
        payload={"text": "hello"},
    )

    key = "tool.slack.SLACK_SEND_MESSAGE"
    assert key in context.raw_outputs
    entries = context.raw_outputs[key]
    entry = entries[-1]
    assert entry["response"]["data"]["ok"] is True
    assert entry["payload"] == {"text": "hello"}
    assert response["successful"] is True


def test_tool_validation_unknown_tool_id(monkeypatch, tmp_path):
    context = PlannerContext(task="Unknown tool", user_id="tester", budget=Budget())
    context.summary_root = tmp_path
    llm = FakeLLM(
        [
            {
                "type": "tool",
                "tool_id": "unknown.provider_tool",
                "server": "unknown",
                "args": {},
                "reasoning": "Intentionally call an unknown tool.",
            }
        ]
    )

    monkeypatch.setattr("mcp_agent.planner.runtime.perform_initial_discovery", lambda ctx: None)

    from mcp_agent.toolbox.index import ToolboxIndex

    empty_index = ToolboxIndex(providers={}, tools_by_id={})
    monkeypatch.setattr("mcp_agent.planner.runtime.get_index", lambda *args, **kwargs: empty_index)

    runtime = PlannerRuntime(context, llm=llm)
    result = runtime.run()

    assert result["success"] is False
    assert result["error"] == "planner_used_unknown_tool"
    assert result.get("error_code") == "planner_used_unknown_tool"
    assert isinstance(result.get("steps"), list)


def test_tool_validation_undiscovered_tool_id(monkeypatch, tmp_path):
    context = PlannerContext(task="Undiscovered tool", user_id="tester", budget=Budget())
    context.summary_root = tmp_path

    # Pretend a search already occurred but returned no tools.
    context.record_step(
        type="search",
        command={"type": "search", "query": "gmail"},
        success=True,
        preview="dummy search",
        output=[],
        is_summary=False,
    )

    from mcp_agent.toolbox.models import ParameterSpec, ProviderSpec, ToolSpec, ToolboxManifest
    from mcp_agent.toolbox.index import ToolboxIndex

    parameter = ParameterSpec(
        name="dummy",
        kind="positional_or_keyword",
        required=False,
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
        mcp_tool_name="GMAIL_SEARCH",
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
    monkeypatch.setattr("mcp_agent.planner.runtime.get_index", lambda *args, **kwargs: index)

    llm = FakeLLM(
        [
            {
                "type": "tool",
                "tool_id": tool.tool_id,
                "server": "gmail",
                "args": {},
                "reasoning": "Call a tool that was not discovered via search.",
            }
        ]
    )

    monkeypatch.setattr("mcp_agent.planner.runtime.perform_initial_discovery", lambda ctx: None)

    runtime = PlannerRuntime(context, llm=llm)
    result = runtime.run()

    assert result["success"] is False
    assert result["error"] == "planner_used_undiscovered_tool"


def test_sandbox_validator_blocks_unknown_server(monkeypatch, tmp_path):
    context = PlannerContext(task="Sandbox unknown server", user_id="tester", budget=Budget())
    context.summary_root = tmp_path
    llm = FakeLLM(
        [
            {
                "type": "sandbox",
                "code": "from sandbox_py.servers import gmail\nresult = 1",
                "reasoning": "Attempt to use gmail without discovery.",
            }
        ]
    )

    monkeypatch.setattr("mcp_agent.planner.runtime.perform_initial_discovery", lambda ctx: None)

    runtime = PlannerRuntime(context, llm=llm)
    result = runtime.run()

    assert result["success"] is False
    assert result["error"] == "planner_used_unknown_server"


def test_discovery_failure_after_multiple_empty_searches(monkeypatch, tmp_path):
    context = PlannerContext(task="Discovery failure", user_id="tester", budget=Budget())
    context.summary_root = tmp_path
    llm = FakeLLM(
        [
            {
                "type": "search",
                "query": "gmail",
                "detail_level": "summary",
                "limit": 5,
                "reasoning": "Look for Gmail tools.",
            },
            {
                "type": "search",
                "query": "gmail inbox emails",
                "detail_level": "summary",
                "limit": 5,
                "reasoning": "Refine Gmail tool search.",
            },
            {
                "type": "sandbox",
                "code": "from sandbox_py.servers import gmail\nresult = 1",
                "reasoning": "Try to use gmail tools after failed discovery.",
            },
        ]
    )

    monkeypatch.setattr("mcp_agent.planner.runtime.perform_initial_discovery", lambda ctx: None)

    def fake_refined(context: PlannerContext, *, query: str, detail_level: str, limit: int):
        # Always return empty results so discovery never finds tools.
        return []

    monkeypatch.setattr("mcp_agent.planner.runtime.perform_refined_discovery", fake_refined)

    runtime = PlannerRuntime(context, llm=llm)
    result = runtime.run()

    assert result["success"] is False
    assert result["error"] == "discovery_failed"
    assert "No suitable tools were found via search" in result["final_summary"]
