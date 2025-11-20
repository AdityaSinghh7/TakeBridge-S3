from __future__ import annotations

from typing import Any, Dict, List

# Optional legacy compatibility - TODO: Remove when fully migrated
try:
    from mcp_agent.mcp_agent import MCPAgent
    _HAS_LEGACY_MCPAGENT = True
except ImportError:
    _HAS_LEGACY_MCPAGENT = False
    MCPAgent = None

from mcp_agent.execution.envelope import normalize_action_response

from .context import PlannerContext


def _compact_gmail_fetch_emails_payload(response: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a compact, text-focused view of GMAIL_FETCH_EMAILS results.

    Composio's Gmail tool returns data like:
      {
        "messages": [
          {
            "messageId": ...,
            "threadId": ...,
            "sender": ...,
            "to": ...,
            "subject": ...,
            "messageText": "...",
            "messageTimestamp": "...",
            "attachmentList": [...],
            "labelIds": [...],
            "payload": {...},
            "preview": {...},
          },
          ...
        ],
        "nextPageToken": "...",
        "resultSizeEstimate": 201,
      }

    This helper strips heavy fields and truncates messageText so planner
    summaries never pull in huge HTML bodies or attachments.
    """
    data = response.get("data") or {}
    messages = data.get("messages") or []
    compact: List[Dict[str, Any]] = []
    max_text_chars = 4000

    for msg in messages:
        if not isinstance(msg, dict):
            continue
        text = msg.get("messageText") or ""
        if isinstance(text, str) and len(text) > max_text_chars:
            text = text[:max_text_chars]
        compact.append(
            {
                "messageId": msg.get("messageId"),
                "threadId": msg.get("threadId"),
                "sender": msg.get("sender"),
                "to": msg.get("to"),
                "subject": msg.get("subject"),
                "messageTimestamp": msg.get("messageTimestamp"),
                "text": text,
                "attachmentCount": len(msg.get("attachmentList") or []),
            }
        )

    return {
        "messages": compact,
        "resultSizeEstimate": data.get("resultSizeEstimate"),
        "nextPageToken": data.get("nextPageToken"),
    }


def call_direct_tool(
    context: PlannerContext,
    *,
    provider: str,
    tool: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Call a single MCP tool synchronously and record its output in
    PlannerContext.raw_outputs under a tool.* key.
    
    TODO: Migrate to use actions.dispatcher.dispatch_tool with AgentContext
    """
    context.budget_tracker.tool_calls += 1
    context.record_event(
        "mcp.action.called",
        {"provider": provider, "tool": tool},
    )
    
    if not _HAS_LEGACY_MCPAGENT or MCPAgent is None:
        raise RuntimeError("MCPAgent not available - need to migrate to new dispatcher")
    
    agent = MCPAgent.current(context.user_id)
    raw_response = agent.call_tool(provider, tool, payload)
    response = normalize_action_response(raw_response)
    result_key = f"tool.{provider}.{tool}"
    entry = {
        "type": "tool",
        "provider": provider,
        "tool": tool,
        "payload": payload,
        "response": response,
    }
    context.append_raw_output(result_key, entry)
    label = f"{provider}.{tool}"
    if provider == "gmail" and tool == "GMAIL_FETCH_EMAILS":
        summary_payload = _compact_gmail_fetch_emails_payload(response)
        summary = context.summarize_tool_output(label, summary_payload, force=True)
    else:
        summary = context.summarize_tool_output(label, response)
    if summary:
        entry["summary"] = summary
    return response

