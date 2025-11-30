from __future__ import annotations

import contextvars
import logging
import threading
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_ALLOWED_EVENT_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")


class StreamEmitter:
    """Callable wrapper that delivers events to the SSE response producer."""

    def __init__(self, publish: Callable[[str, Any], None]) -> None:
        self._publish = publish

    def emit(self, event: str, data: Any) -> None:
        try:
            self._publish(event, data)
        except Exception:  # pragma: no cover - best-effort telemetry
            logger.exception("Failed to publish stream event %s", event)


_CURRENT_EMITTER: contextvars.ContextVar[Optional[StreamEmitter]] = contextvars.ContextVar(
    "framework_stream_emitter",
    default=None,
)
_THREAD_EMITTER = threading.local()
_GLOBAL_EMITTER: Optional[StreamEmitter] = None
_EMITTER_WARNING_EMITTED: bool = False


def set_current_emitter(emitter: Optional[StreamEmitter]) -> contextvars.Token:
    """Set the active emitter for the current context, returning a token to reset."""
    global _GLOBAL_EMITTER
    token = _CURRENT_EMITTER.set(emitter)
    _THREAD_EMITTER.emitter = emitter
    _GLOBAL_EMITTER = emitter
    return token


def reset_current_emitter(token: contextvars.Token) -> None:
    """Reset the active emitter context using a token from set_current_emitter."""
    global _GLOBAL_EMITTER
    try:
        _CURRENT_EMITTER.reset(token)
        remaining = get_current_emitter()
        if remaining is None:
            if hasattr(_THREAD_EMITTER, "emitter"):
                delattr(_THREAD_EMITTER, "emitter")
            _GLOBAL_EMITTER = None
        else:
            _THREAD_EMITTER.emitter = remaining
            _GLOBAL_EMITTER = remaining
    except Exception:  # pragma: no cover - defensive reset
        logger.exception("Failed to reset stream emitter context")


def get_current_emitter() -> Optional[StreamEmitter]:
    """Return the emitter associated with the current execution context."""
    emitter = _CURRENT_EMITTER.get()
    if emitter is not None:
        return emitter
    thread_emitter = getattr(_THREAD_EMITTER, "emitter", None)
    if thread_emitter is not None:
        return thread_emitter
    return _GLOBAL_EMITTER


def streaming_enabled() -> bool:
    """Return True when an emitter has been configured for this context."""
    return get_current_emitter() is not None


def sanitize_event_name(name: str) -> str:
    """Restrict event names to a safe ASCII subset for SSE."""
    if not name:
        return "event"
    sanitized = "".join(ch if ch in _ALLOWED_EVENT_CHARS else "_" for ch in name)
    sanitized = sanitized.strip("._")
    return sanitized or "event"


def emit_event(event: str, data: Any) -> None:
    """Emit an event if streaming is active."""
    global _EMITTER_WARNING_EMITTED
    emitter = get_current_emitter()
    if emitter is None:
        if not _EMITTER_WARNING_EMITTED:
            logger.debug("Dropping stream event '%s' because no emitter is active.", event)
            _EMITTER_WARNING_EMITTED = True
        return
    _EMITTER_WARNING_EMITTED = False
    sanitized = sanitize_event_name(event)
    logger.debug(
        "Emitting stream event '%s' payload_keys=%s",
        sanitized,
        list(data.keys()) if isinstance(data, dict) else type(data).__name__,
    )
    emitter.emit(sanitized, data)


def _coerce_event_obj(item: Any) -> Dict[str, Any]:
    """Best effort conversion of SDK streaming events to plain dicts."""
    if isinstance(item, dict):
        return dict(item)
    if hasattr(item, "model_dump") and callable(getattr(item, "model_dump")):
        try:
            return item.model_dump()  # type: ignore[call-arg]
        except Exception:
            logger.debug("model_dump failed for %r", item)
    if hasattr(item, "__dict__"):
        return {k: v for k, v in vars(item).items() if not k.startswith("_")}
    return {"value": repr(item)}


def _extract_text_chunks(value: Any) -> List[str]:
    """Recursively pull textual content from streaming delta payloads."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        chunks: List[str] = []
        for nested in value.values():
            chunks.extend(_extract_text_chunks(nested))
        return chunks
    if isinstance(value, list):
        chunks: List[str] = []
        for item in value:
            chunks.extend(_extract_text_chunks(item))
        return chunks
    return []


class LLMStreamCollector:
    """Collects delta updates for reasoning/output streams while forwarding telemetry."""

    def __init__(
        self,
        source: str,
        *,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.source = sanitize_event_name(source) or "llm"
        self.metadata = metadata or {}
        self.output_chunks: List[str] = []
        self.reasoning_chunks: List[str] = []

    def handler(self, event: Any) -> None:
        event_dict = _coerce_event_obj(event)
        event_type = event_dict.get("type") or ""
        payload_base = {"source": self.source}
        if self.metadata:
            payload_base.update(self.metadata)

        if event_type.endswith("reasoning.delta"):
            for chunk in _extract_text_chunks(event_dict.get("delta")):
                if not chunk:
                    continue
                self.reasoning_chunks.append(chunk)
                emit_event(
                    f"{self.source}.reasoning.delta",
                    {**payload_base, "text": chunk},
                )
            return

        if event_type.endswith("output_text.delta"):
            for chunk in _extract_text_chunks(event_dict.get("delta")):
                if not chunk:
                    continue
                self.output_chunks.append(chunk)
                emit_event(
                    f"{self.source}.output.delta",
                    {**payload_base, "text": chunk},
                )
            return

        if event_type == "response.completed":
            emit_event(f"{self.source}.stream.completed", payload_base)
            return

        if event_type == "response.error":
            error_info = event_dict.get("error") or event_dict.get("data") or event_dict
            emit_event(f"{self.source}.stream.error", {**payload_base, "error": error_info})

    def reasoning_text(self) -> str:
        return "".join(self.reasoning_chunks)

    def output_text(self) -> str:
        return "".join(self.output_chunks)


def create_collector(source: str, *, metadata: Optional[Dict[str, Any]] = None) -> LLMStreamCollector:
    """Helper to create a collector only when streaming is enabled."""
    return LLMStreamCollector(source, metadata=metadata or {})
