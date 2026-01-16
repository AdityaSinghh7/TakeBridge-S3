from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class LLMRequestEntry:
    request_id: str
    run_id: str
    provider: str
    model: str
    stream: bool
    started_at: float
    params: Dict[str, Any]
    message_count: int
    has_input: bool
    cancel_event: threading.Event = field(default_factory=threading.Event)
    retry_event: threading.Event = field(default_factory=threading.Event)
    retry_count: int = 0
    last_retry_at: Optional[float] = None

    def snapshot(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "run_id": self.run_id,
            "provider": self.provider,
            "model": self.model,
            "stream": self.stream,
            "started_at": self.started_at,
            "params": self.params,
            "message_count": self.message_count,
            "has_input": self.has_input,
            "retry_count": self.retry_count,
            "last_retry_at": self.last_retry_at,
            "cancel_requested": self.cancel_event.is_set(),
            "retry_requested": self.retry_event.is_set(),
        }


_REGISTRY: Dict[str, LLMRequestEntry] = {}
_LOCK = threading.Lock()


def _summarize_request(request: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(request, dict):
        return {}
    params = request.get("params") if isinstance(request.get("params"), dict) else {}
    messages = request.get("messages")
    message_count = len(messages) if isinstance(messages, list) else 0
    has_input = request.get("input") is not None
    return {
        "params": params,
        "message_count": message_count,
        "has_input": has_input,
    }


def register_request(
    *,
    run_id: str,
    provider: str,
    model: str,
    stream: bool,
    request: Optional[Dict[str, Any]] = None,
) -> LLMRequestEntry:
    summary = _summarize_request(request)
    entry = LLMRequestEntry(
        request_id=str(uuid.uuid4()),
        run_id=run_id,
        provider=provider,
        model=model,
        stream=stream,
        started_at=time.time(),
        params=summary.get("params", {}),
        message_count=summary.get("message_count", 0),
        has_input=summary.get("has_input", False),
    )
    with _LOCK:
        existing = _REGISTRY.get(run_id)
        if existing:
            logger.warning(
                "Overwriting active LLM request entry for run_id=%s old_request_id=%s",
                run_id,
                existing.request_id,
            )
        _REGISTRY[run_id] = entry
    return entry


def get_request(run_id: str) -> Optional[LLMRequestEntry]:
    with _LOCK:
        return _REGISTRY.get(run_id)


def clear_request(run_id: str, request_id: str) -> None:
    with _LOCK:
        entry = _REGISTRY.get(run_id)
        if entry and entry.request_id == request_id:
            _REGISTRY.pop(run_id, None)


def request_cancel_retry(run_id: str) -> Optional[Dict[str, Any]]:
    with _LOCK:
        entry = _REGISTRY.get(run_id)
        if not entry:
            return None
        entry.cancel_event.set()
        entry.retry_event.set()
        entry.last_retry_at = time.time()
        return entry.snapshot()
