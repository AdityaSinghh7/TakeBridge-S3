from __future__ import annotations

import logging
import os
import json
from typing import TYPE_CHECKING, Any, Dict, Iterable
import requests

from mcp_agent.core.exceptions import UnauthorizedError
from mcp_agent.registry import get_mcp_client, is_provider_available
from mcp_agent.high_signal import emit_high_signal, HIGH_SIGNAL_KEYS
from mcp_agent.types import ToolInvocationResult
from mcp_agent.user_identity import normalize_user_id
from mcp_agent.utils.event_logger import log_mcp_event
from shared.streaming import emit_event

if TYPE_CHECKING:
    from mcp_agent.core.context import AgentContext

logger = logging.getLogger(__name__)


def ensure_authorized(context: "AgentContext", provider: str) -> str:
    """Raise if provider is unavailable for the current user."""
    user_id = normalize_user_id(context.user_id)
    if not is_provider_available(context, provider):
        raise UnauthorizedError(provider, user_id)
    return user_id


def _clean_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Remove None values to avoid sending unset optional params."""
    return {k: v for k, v in payload.items() if v is not None}


def _get_high_signal_field_names(provider: str, tool: str) -> list[str]:
    """Return unique top-level field names referenced by the configured high-signal paths."""
    signal_paths = HIGH_SIGNAL_KEYS.get(provider, {}).get(tool, [])
    seen: set[str] = set()
    fields: list[str] = []
    for path in signal_paths:
        if not path:
            continue
        cut = len(path)
        for sep in (".", "["):
            sep_index = path.find(sep)
            if sep_index != -1:
                cut = min(cut, sep_index)
        field = path[:cut]
        if not field or field in seen:
            continue
        seen.add(field)
        fields.append(field)
    return fields


def normalize_fields_argument(fields: str | Iterable[str] | None, provider: str, tool: str) -> str | None:
    """Ensure the `fields` argument covers the configured high-signal paths by default."""
    if fields is None:
        default_fields = _get_high_signal_field_names(provider, tool)
        return ",".join(default_fields) if default_fields else None
    if isinstance(fields, str):
        return fields
    normalized = ",".join(str(value).strip() for value in fields if str(value).strip())
    return normalized or None


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
    from mcp_agent.execution.response_ops import MCPResponseOps

    normalized: dict[str, Any] = dict(response or {})
    envelope = MCPResponseOps(normalized).to_action_response()
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
    # Default to MCP stream client; Composio execute API is temporarily disabled (500s with code 1601).
    use_execute_api = False
    # use_execute_api = os.getenv("COMPOSIO_TOOL_EXECUTE_ENABLED", "0").strip() not in {"0", "false", "False"}

    started_payload = {
        "server": provider,
        "tool": tool,
        "payload_keys": payload_keys,
        "user_id": user_id,
    }
    emit_event("mcp.action.started", started_payload)
    log_mcp_event("mcp.action.started", started_payload, source="wrapper")

    try:
        if use_execute_api:
            logger.info("Invoking via Composio execute API provider=%s tool=%s user=%s", provider, tool, user_id)
            transport_payload = {
                "server": provider,
                "tool": tool,
                "transport": "composio_execute_api",
                "user_id": user_id,
            }
            emit_event("mcp.action.transport", transport_payload)
            log_mcp_event("mcp.action.transport", transport_payload, source="wrapper")
            response = _invoke_via_composio_api(context, provider, tool, payload)
        else:
            logger.info("Invoking via MCP stream client provider=%s tool=%s user=%s", provider, tool, user_id)
            transport_payload = {
                "server": provider,
                "tool": tool,
                "transport": "mcp_stream",
                "user_id": user_id,
            }
            emit_event("mcp.action.transport", transport_payload)
            log_mcp_event("mcp.action.transport", transport_payload, source="wrapper")
            client = get_mcp_client(context, provider)
            if not client:
                raise RuntimeError(f"MCP client not available for provider: {provider}")
            response = client.call(tool, payload)
    except Exception as exc:  # pragma: no cover - passthrough to caller
        error_message = str(exc)
        failed_payload = {
            "server": provider,
            "tool": tool,
            "error": error_message,
            "user_id": user_id,
        }
        emit_event("mcp.action.failed", failed_payload)
        log_mcp_event("mcp.action.failed", failed_payload, source="wrapper")
        result = _structured_result(
            provider,
            tool,
            successful=False,
            error=error_message,
        )
        emit_high_signal(provider, tool, result)
        return result

    completed_payload = {
        "server": provider,
        "tool": tool,
        "user_id": user_id,
    }
    emit_event("mcp.action.completed", completed_payload)
    log_mcp_event("mcp.action.completed", completed_payload, source="wrapper")
    normalized = _normalize_tool_response(provider, tool, payload_keys, response)
    emit_high_signal(provider, tool, normalized)
    return normalized


def _invoke_via_composio_api(
    context: "AgentContext", provider: str, tool: str, payload: dict[str, Any]
) -> dict[str, Any]:
    """Invoke a tool via Composio REST execute endpoint."""
    from mcp_agent.registry import crud
    from mcp_agent.registry.oauth import COMPOSIO_API_V3, OAuthManager

    user_id = normalize_user_id(context.user_id)
    with context.get_db() as db:
        ca_id, ac_id, _url, hdrs = crud.get_active_context_for_provider(db, user_id, provider)
    # If headers already carry a newer CA/AC, prefer that for consistency
    hdr_lower = {k.lower(): v for k, v in (hdrs or {}).items()}
    header_ca = hdr_lower.get("x-connected-account-id")
    header_ac = hdr_lower.get("x-auth-config-id")
    if header_ca:
        ca_id = header_ca
    if header_ac:
        ac_id = header_ac
    if not ca_id:
        raise RuntimeError(f"No connected account for provider '{provider}' and user '{user_id}'")

    # Base headers: API key + auth headers (if any)
    api_key = os.getenv("COMPOSIO_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("COMPOSIO_API_KEY missing for tool execution")
    headers = {"x-api-key": api_key, "content-type": "application/json"}

    # Fetch auth headers and force them to align with the chosen connected_account_id/auth_config_id
    auth_headers = OAuthManager.get_headers(context, provider) or {}
    # Normalize header keys to overwrite regardless of case
    normalized_auth = {k.lower(): v for k, v in auth_headers.items()}
    if ca_id:
        normalized_auth["x-connected-account-id"] = ca_id
    if ac_id:
        normalized_auth["x-auth-config-id"] = ac_id
    # Rebuild headers with canonical casing
    for k, v in normalized_auth.items():
        # Preserve original casing if present, else title-case dashes
        canonical = next((orig for orig in auth_headers.keys() if orig.lower() == k), k)
        headers[canonical] = v

    body: dict[str, Any] = {
        "connected_account_id": ca_id,
        "user_id": user_id,
        "arguments": payload,
    }
    if ac_id:
        body["auth_config_id"] = ac_id

    url = f"{COMPOSIO_API_V3}/tools/execute/{tool}"
    try:
        safe_body = json.dumps(body, default=str)
    except Exception:
        safe_body = str(body)
    # Log full headers/body (no redaction) to surface exact request; use cautiously
    logger.info("POST %s provider=%s tool=%s user=%s headers(full)=%s body=%s", url, provider, tool, user_id, headers, safe_body)
    print(f"[composio_execute] POST {url} provider={provider} tool={tool} user={user_id} headers={headers} body={safe_body}")
    request_payload = {
        "server": provider,
        "tool": tool,
        "transport": "composio_execute_api",
        "url": url,
        "user_id": user_id,
    }
    emit_event("mcp.action.request", request_payload)
    log_mcp_event("mcp.action.request", request_payload, source="wrapper")
    resp = requests.post(url, json=body, headers=headers, timeout=30)
    if 200 <= resp.status_code < 300:
        try:
            return resp.json()
        except Exception:
            return {"successful": True, "data": resp.text}

    snippet = resp.text[:500]
    raise RuntimeError(f"Composio execute failed HTTP {resp.status_code}: {snippet}")


__all__ = [
    "_clean_payload",
    "_invoke_mcp_tool",
    "ensure_authorized",
]
