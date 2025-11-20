from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Sequence


DEFAULT_SENSITIVE_KEYS = ["token", "authorization", "password", "api_key", "secret"]


def summarize_payload(
    label: str,
    payload: Any,
    *,
    purpose: str = "for_planning",
    max_chars: int = 4000,
    sample_limit: int = 3,
    storage_dir: Path | None = None,
    persist_payload: bool = False,
    ) -> Dict[str, Any]:
    """
    Summarize arbitrary payloads into a planner-friendly structure.

    This is a pure utility: it never calls an LLM and only derives schema,
    samples, aggregates, and optional storage references for large payloads.
    """
    redacted_payload = redact_payload(payload)
    serialized = _safe_json(redacted_payload)
    size_bytes = len(serialized.encode("utf-8"))
    truncated = len(serialized) > max_chars
    sample = _sample_payload(redacted_payload, sample_limit)
    schema = _infer_schema(redacted_payload)
    aggregates = _derive_aggregates(redacted_payload)
    notes = _purpose_notes(purpose, truncated)

    storage_ref = None
    if storage_dir and (persist_payload or truncated):
        storage_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{_safe_filename(label)}.json"
        storage_path = storage_dir / filename
        storage_path.write_text(serialized, encoding="utf-8")
        storage_ref = storage_path.as_posix()

    summary = {
        "label": label,
        "is_summary": True,
        "original_size": size_bytes,
        "truncated": truncated,
        "schema": schema,
        "sample": sample,
        "aggregates": aggregates,
        "notes": notes,
    }
    if storage_ref:
        summary["storage_ref"] = storage_ref
    return summary


def redact_payload(payload: Any, sensitive_keys: Sequence[str] = DEFAULT_SENSITIVE_KEYS) -> Any:
    """Mask sensitive keys recursively."""
    lower_keys = {k.lower() for k in sensitive_keys}
    if isinstance(payload, dict):
        return {
            key: "[REDACTED]" if key.lower() in lower_keys else redact_payload(value, sensitive_keys)
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [redact_payload(item, sensitive_keys) for item in payload]
    if isinstance(payload, tuple):
        return tuple(redact_payload(item, sensitive_keys) for item in payload)
    return payload


def _safe_json(payload: Any) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False, default=str)
    except TypeError:
        return json.dumps(str(payload))


def _sample_payload(payload: Any, limit: int) -> Any:
    if isinstance(payload, list):
        return payload[:limit]
    if isinstance(payload, dict):
        sample_dict: Dict[str, Any] = {}
        for idx, (key, value) in enumerate(payload.items()):
            if idx >= limit:
                break
            sample_dict[key] = value
        return sample_dict
    return payload


def _infer_schema(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, dict):
        return {"type": "object", "keys": sorted(payload.keys())}
    if isinstance(payload, list):
        if not payload:
            return {"type": "list", "items": 0}
        first = payload[0]
        if isinstance(first, dict):
            keys = sorted({key for item in payload if isinstance(item, dict) for key in item.keys()})
            return {"type": "list[object]", "keys": keys}
        return {"type": f"list[{type(first).__name__}]", "items": len(payload)}
    return {"type": type(payload).__name__}


def _derive_aggregates(payload: Any) -> Dict[str, Any]:
    aggregates: Dict[str, Any] = {}
    if isinstance(payload, list):
        aggregates["count"] = len(payload)
        numeric_values = [item for item in payload if isinstance(item, (int, float))]
        if numeric_values:
            aggregates.update(
                {
                    "sum": sum(numeric_values),
                    "min": min(numeric_values),
                    "max": max(numeric_values),
                }
            )
    if isinstance(payload, dict):
        aggregates["keys"] = len(payload)
    return aggregates


def _purpose_notes(purpose: str, truncated: bool) -> str:
    notes = []
    if purpose == "for_user":
        notes.append("User-facing condensed summary.")
    elif purpose == "for_debug":
        notes.append("Debug summary with additional metadata.")
    else:
        notes.append("Planner-focused summary: schema + sample + aggregates only.")
    if truncated:
        notes.append("Underlying payload is larger than shown; only partial data visible.")
    return " ".join(notes)


def _safe_filename(label: str) -> str:
    sanitized = re.sub(r"[^a-zA-Z0-9._-]", "_", label.strip())
    sanitized = sanitized.strip("_") or "payload"
    return sanitized[:80]

