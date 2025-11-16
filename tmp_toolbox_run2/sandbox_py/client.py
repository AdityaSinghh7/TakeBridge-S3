from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable, Dict, Iterable, MutableMapping, Optional, Protocol, Sequence, TypedDict

logger = logging.getLogger(__name__)


class ToolCallResult(TypedDict, total=False):
    successful: bool
    data: Any
    error: Any
    logs: Any


class ToolCaller(Protocol):
    def __call__(self, provider: str, tool: str, payload: Dict[str, Any]) -> Awaitable[ToolCallResult] | ToolCallResult:
        ...


_REGISTERED_CALLER: ToolCaller | None = None
_DEFAULT_REDACT_KEYS = ("token", "authorization", "password", "api_key", "secret")


def register_tool_caller(caller: ToolCaller) -> None:
    """Bind the sandbox runtime to an MCP bridge callable."""
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
    """Invoke an MCP tool via the registered bridge with basic retries."""
    if _REGISTERED_CALLER is None:
        raise RuntimeError("No sandbox tool caller registered. Call register_tool_caller() first.")
    sanitized = sanitize_payload(dict(payload))
    redacted = redact_payload(dict(sanitized), _DEFAULT_REDACT_KEYS)
    attempt = 0
    last_error: Exception | None = None
    while attempt <= retries:
        try:
            result = _REGISTERED_CALLER(provider, tool, sanitized)
            if asyncio.iscoroutine(result):
                result = await result
            return result
        except Exception as exc:  # pragma: no cover - retry logic
            last_error = exc
            logger.warning(
                "tool call %s.%s failed (attempt %s/%s): %s",
                provider,
                tool,
                attempt + 1,
                retries + 1,
                exc,
            )
            if attempt >= retries:
                exc.payload = redacted  # type: ignore[attr-defined]
                raise
            await asyncio.sleep(retry_delay * (attempt + 1))
        finally:
            attempt += 1
    if last_error:
        raise last_error
    raise RuntimeError("call_tool failed without raising an explicit error.")


def sanitize_payload(payload: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    """Remove keys whose value is None to keep payloads compact."""
    for key in list(payload.keys()):
        if payload[key] is None:
            payload.pop(key)
    return payload


StructuredData = Any
StringListInput = Any


def serialize_structured_param(value: StructuredData) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value)
    except Exception as exc:  # pragma: no cover - serialization errors
        raise ValueError(f"Failed to serialize structured payload: {exc}") from exc


def normalize_string_list(value: StringListInput) -> list[str]:
    if value in (None, "", []):
        return []
    if isinstance(value, str):
        candidates = value.replace(";", ",").split(",")
        return [entry.strip() for entry in candidates if entry.strip()]
    if isinstance(value, Iterable):
        cleaned = []
        for entry in value:
            if isinstance(entry, str) and entry.strip():
                cleaned.append(entry.strip())
        return cleaned
    return [str(value)]


def merge_recipient_lists(base: StringListInput, extras: Sequence[str] | None = None) -> list[str]:
    combined = normalize_string_list(base)
    if extras:
        combined.extend(extra for extra in extras if extra)
    deduped: list[str] = []
    seen = set()
    for entry in combined:
        lowered = entry.lower()
        if lowered not in seen:
            deduped.append(entry)
            seen.add(lowered)
    return deduped


def redact_payload(payload: Dict[str, Any], sensitive_keys: Sequence[str]) -> Dict[str, Any]:
    lowered = {key.lower() for key in sensitive_keys}
    clone: Dict[str, Any] = {}
    for key, value in payload.items():
        clone[key] = "[REDACTED]" if key.lower() in lowered else value
    return clone
