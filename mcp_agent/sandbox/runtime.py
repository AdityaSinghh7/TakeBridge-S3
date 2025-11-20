"""Sandbox runtime for calling MCP tools from generated Python code.

This module replaces the generated sandbox_py package with a cleaner,
source-based implementation that uses dynamic dispatch.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict, Iterable, Optional, Protocol, Sequence, TypedDict

logger = logging.getLogger(__name__)


class ToolCallResult(TypedDict, total=False):
    """Result envelope from MCP tool invocation."""
    successful: bool
    data: Any
    error: Any
    logs: Any


class ToolCaller(Protocol):
    """Protocol for tool calling function."""
    def __call__(
        self, provider: str, tool: str, payload: Dict[str, Any]
    ) -> Awaitable[ToolCallResult] | ToolCallResult:
        ...


_REGISTERED_CALLER: ToolCaller | None = None
_DEFAULT_REDACT_KEYS = ("token", "authorization", "password", "api_key", "secret")


def register_tool_caller(caller: ToolCaller) -> None:
    """Bind the sandbox runtime to an MCP bridge callable.

    This is called by mcp_agent.sandbox.glue.register_default_tool_caller()
    to wire up the dispatch_tool backend.
    """
    global _REGISTERED_CALLER
    _REGISTERED_CALLER = caller


async def call_tool(
    provider: str,
    tool: str,
    payload: Dict[str, Any],
    *,
    retries: int = 2,
    retry_delay: float = 0.1,
) -> ToolCallResult:
    """Invoke an MCP tool via the registered bridge with basic retries.

    Args:
        provider: Provider name (e.g., 'gmail', 'slack')
        tool: Tool/action name (e.g., 'GMAIL_FETCH_EMAILS')
        payload: Tool parameters as dict
        retries: Number of retry attempts on transient failures
        retry_delay: Delay in seconds between retries

    Returns:
        ToolCallResult with successful, data, error, logs fields

    Raises:
        RuntimeError: If no tool caller is registered
    """
    if _REGISTERED_CALLER is None:
        raise RuntimeError(
            "No sandbox tool caller registered. "
            "Call register_tool_caller() or mcp_agent.sandbox.glue.register_default_tool_caller() first."
        )

    sanitized = sanitize_payload(dict(payload))
    redacted = redact_payload(dict(sanitized), _DEFAULT_REDACT_KEYS)

    attempt = 0
    last_error: Exception | None = None

    while attempt <= retries:
        try:
            result = _REGISTERED_CALLER(provider, tool, sanitized)
            if asyncio.iscoroutine(result) or asyncio.isfuture(result):
                result = await result

            logger.info(
                "MCP tool call: provider=%s tool=%s payload=%s -> %s",
                provider,
                tool,
                redacted,
                "success" if result.get("successful") else "failure",
            )
            return result
        except Exception as exc:
            last_error = exc
            attempt += 1
            if attempt <= retries:
                logger.warning(
                    "Tool call failed (attempt %d/%d): %s", attempt, retries + 1, exc
                )
                await asyncio.sleep(retry_delay)
            else:
                logger.error("Tool call failed after %d attempts: %s", retries + 1, exc)

    # All retries exhausted
    return {
        "successful": False,
        "data": None,
        "error": f"Tool call failed after {retries + 1} attempts: {last_error}",
        "logs": None,
    }


def sanitize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Remove None values and normalize types for MCP transmission.

    Args:
        payload: Raw payload dict

    Returns:
        Sanitized payload with None values removed
    """
    return {k: v for k, v in payload.items() if v is not None}


def redact_payload(
    payload: Dict[str, Any], redact_keys: Sequence[str] = _DEFAULT_REDACT_KEYS
) -> Dict[str, Any]:
    """Redact sensitive keys for logging.

    Args:
        payload: Payload dict to redact
        redact_keys: Keys to redact (case-insensitive)

    Returns:
        New dict with sensitive values replaced with '<redacted>'
    """
    lower_keys = {k.lower() for k in redact_keys}
    redacted = {}
    for k, v in payload.items():
        if k.lower() in lower_keys:
            redacted[k] = "<redacted>"
        elif isinstance(v, dict):
            redacted[k] = redact_payload(v, redact_keys)
        else:
            redacted[k] = v
    return redacted


def normalize_string_list(value: Any) -> list[str] | None:
    """Normalize various input formats to a list of strings.

    Handles:
    - None -> None
    - str -> [str]
    - Iterable[str] -> list[str]
    - comma-separated string -> list[str]

    Args:
        value: Input value to normalize

    Returns:
        List of strings or None
    """
    if value is None:
        return None
    if isinstance(value, str):
        # Check if comma-separated
        if "," in value:
            return [item.strip() for item in value.split(",") if item.strip()]
        return [value]
    if isinstance(value, Iterable):
        return [str(item) for item in value]
    return [str(value)]
