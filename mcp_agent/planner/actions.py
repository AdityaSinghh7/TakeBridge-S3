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
    context.raw_outputs[f"tool.{provider}.{tool}"] = {
        "type": "tool",
        "provider": provider,
        "tool": tool,
        "payload": payload,
        "response": response,
    }
    context.summarize_tool_output(f"{provider}.{tool}", response)
    return response
