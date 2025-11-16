from __future__ import annotations

from typing import Any, Dict

from mcp_agent.mcp_agent import MCPAgent

from .context import PlannerContext


def call_direct_tool(
    context: PlannerContext,
    *,
    provider: str,
    tool: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    context.budget_tracker.tool_calls += 1
    context.record_event(
        "mcp.action.called",
        {"provider": provider, "tool": tool},
    )
    agent = MCPAgent.current(context.user_id)
    response = agent.call_tool(provider, tool, payload)
    result_key = f"tool.{provider}.{tool}"
    entry = {
        "type": "tool",
        "provider": provider,
        "tool": tool,
        "payload": payload,
        "response": response,
    }
    context.append_raw_output(result_key, entry)
    summary = context.summarize_tool_output(f"{provider}.{tool}", response)
    if summary:
        entry["summary"] = summary
    return response
