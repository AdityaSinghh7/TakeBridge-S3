from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List

import pytest

from mcp_agent.planner.runtime import execute_mcp_task
from mcp_agent.toolbox.builder import ToolboxBuilder

from mcp_agent import registry
from mcp_agent.mcp_agent import MCPAgent
from tests.fakes.fake_mcp import CALL_HISTORY, reset_history


class ScriptedLLM:
    def __init__(self, commands: List[dict]):
        self._commands = commands
        self._index = 0

    def generate_plan(self, context):
        if self._index >= len(self._commands):
            raise RuntimeError("LLM invoked more times than expected.")
        payload = self._commands[self._index]
        self._index += 1
        return {"text": json.dumps(payload), "messages": [], "response": None}


@pytest.fixture(autouse=True)
def fake_registry(monkeypatch):
    monkeypatch.setenv("MCP_FAKE_CLIENT_FACTORY", "tests.fakes.fake_mcp:build_fake_clients")
    reset_history()
    registry.MCP.clear()
    registry._REGISTRY_VERSION_BY_USER = {}
    MCPAgent._current_by_user = {}
    registry.init_registry("singleton")
    assert registry.is_registered("slack", "singleton")
    monkeypatch.setattr(
        "mcp_agent.mcp_agent.init_registry",
        lambda user_id=None: registry.init_registry(user_id or "singleton"),
    )
    class _StubAgent:
        def __init__(self, user_id: str = "singleton") -> None:
            self.user_id = user_id

        def call_tool(self, provider: str, tool: str, payload: dict[str, Any]) -> dict[str, Any]:
            client = registry.get_client(provider, self.user_id)
            if not client:
                raise RuntimeError(f"Stub MCP provider '{provider}' missing.")
            return client.call(tool, payload)

    monkeypatch.setattr(
        "mcp_agent.mcp_agent.MCPAgent.current",
        classmethod(lambda cls, user_id=None: _StubAgent(user_id or "singleton")),  # type: ignore[arg-type]
    )


def test_execute_task_with_slack_tool(monkeypatch):
    def fake_search_tools(*, query, detail_level, limit, user_id):
        return [
            {
                "provider": "slack",
                "tool": "SLACK_SEND_MESSAGE",
                "short_description": "Post Slack message",
                "available": True,
                "score": 10,
                "parameters": ["channel", "text"],
            }
        ]

    monkeypatch.setattr("mcp_agent.planner.discovery.search_tools", fake_search_tools)

    llm = ScriptedLLM(
        [
            {"type": "tool", "provider": "slack", "tool": "slack_post_message", "payload": {"channel": "#ops", "text": "Hello"}},
            {"type": "finish", "summary": "sent"},
        ]
    )

    result = execute_mcp_task("Send Slack update", llm=llm)
    assert result["success"] is True, result
    assert result["final_summary"] == "sent"
    assert CALL_HISTORY and CALL_HISTORY[0]["provider"] == "slack"


def test_execute_task_with_gmail_sandbox(monkeypatch, tmp_path):
    def fake_search_tools(*, query, detail_level, limit, user_id):
        return [
            {
                "provider": "gmail",
                "tool": "GMAIL_FETCH_EMAILS",
                "short_description": "Search Gmail messages",
                "available": True,
                "score": 12,
                "parameters": ["query"],
            }
        ]

    monkeypatch.setattr("mcp_agent.planner.discovery.search_tools", fake_search_tools)

    toolbox_root = tmp_path / "toolbox"
    builder = ToolboxBuilder(user_id="test", base_dir=toolbox_root)
    manifest = builder.build()
    builder.persist(manifest)

    code_body = """from sandbox_py.servers.gmail import gmail_search
result = await gmail_search(query="from:boss")
return {"sandbox": result}
"""
    llm = ScriptedLLM(
        [
            {"type": "sandbox", "code": code_body},
            {"type": "finish", "summary": "gmail done"},
        ]
    )

    result = execute_mcp_task("Process Gmail data", llm=llm, toolbox_root=toolbox_root)
    assert result["success"] is True, result
    sandbox_output = result["raw_outputs"].get("sandbox.sandbox", {})
    assert sandbox_output["success"] is True
    sandbox_payload = sandbox_output["result"]["sandbox"]["data"]["data"]
    assert sandbox_payload["provider"] == "gmail"
