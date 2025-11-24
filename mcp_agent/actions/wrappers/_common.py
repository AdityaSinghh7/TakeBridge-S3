from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

from mcp_agent.core.exceptions import UnauthorizedError
from mcp_agent.registry import get_mcp_client, is_provider_available
from mcp_agent.types import ToolInvocationResult
from mcp_agent.user_identity import normalize_user_id
from shared.streaming import emit_event

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext


def ensure_authorized(context: "AgentContext", provider: str) -> str:
    """Raise if provider is unavailable for the current user."""
    user_id = normalize_user_id(context.user_id)
    if not is_provider_available(context, provider):
        raise UnauthorizedError(provider, user_id)
    return user_id


def _clean_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Remove None values to avoid sending unset optional params."""
    return {k: v for k, v in payload.items() if v is not None}


def _structured_result(
    provider: str,
    tool: str,
    *,
    successful: bool,
    error: str | None = None,
    data: Any = None,
) -> ToolInvocationResult:
    """Build standardized tool result."""
    if data is None:
        normalized_data: Any = {}
    elif isinstance(data, dict):
        normalized_data = data
    else:
        normalized_data = {"value": data}

    return {
        "successful": bool(successful),
        "error": error,
        "data": normalized_data,
        "logs": None,
        "provider": provider,
        "tool": tool,
        "payload_keys": [],
    }


def _normalize_tool_response(
    provider: str,
    tool: str,
    payload_keys: list[str],
    response: dict[str, Any] | None,
) -> ToolInvocationResult:
    """Normalize MCP response into standardized envelope."""
    from mcp_agent.execution.envelope import normalize_action_response

    normalized: dict[str, Any] = dict(response or {})
    envelope = normalize_action_response(normalized)
    normalized["successful"] = envelope["successful"]
    normalized["data"] = envelope["data"]
    normalized["error"] = envelope.get("error")
    normalized.pop("successfull", None)
    normalized.pop("success", None)
    normalized["provider"] = provider
    normalized["tool"] = tool
    normalized["payload_keys"] = payload_keys
    return normalized


def _invoke_mcp_tool(
    context: "AgentContext", provider: str, tool: str, payload: dict[str, Any]
) -> ToolInvocationResult:
    """Call MCP tool via registry client and return normalized result."""
    payload_keys = sorted(payload.keys())
    user_id = normalize_user_id(context.user_id)

    emit_event(
        "mcp.action.started",
        {
            "server": provider,
            "tool": tool,
            "payload_keys": payload_keys,
            "user_id": user_id,
        },
    )

    try:
        client = get_mcp_client(context, provider)
        if not client:
            raise RuntimeError(f"MCP client not available for provider: {provider}")
        response = client.call(tool, payload)
    except Exception as exc:  # pragma: no cover - passthrough to caller
        error_message = str(exc)
        emit_event(
            "mcp.action.failed",
            {
                "server": provider,
                "tool": tool,
                "error": error_message,
                "user_id": user_id,
            },
        )
        return _structured_result(
            provider,
            tool,
            successful=False,
            error=error_message,
        )

    emit_event(
        "mcp.action.completed",
        {
            "server": provider,
            "tool": tool,
            "user_id": user_id,
        },
    )
    return _normalize_tool_response(provider, tool, payload_keys, response)


__all__ = [
    "_clean_payload",
    "_invoke_mcp_tool",
    "ensure_authorized",
]
