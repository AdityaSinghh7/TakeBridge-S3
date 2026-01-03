from __future__ import annotations

import logging
import os
from typing import Any, Dict

logger = logging.getLogger("mcp_agent.events")

_TRUE_VALUES = {"1", "true", "yes", "on"}


def _logging_enabled() -> bool:
    return os.getenv("MCP_EVENT_LOGGING", "1").strip().lower() in _TRUE_VALUES


def _truncate_text(value: Any, limit: int = 160) -> str:
    if value is None:
        return ""
    text = str(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def _short_list(values: Any, limit: int = 6) -> str:
    if not values:
        return ""
    if isinstance(values, dict):
        values = list(values.keys())
    items = [str(item) for item in values if item is not None]
    if not items:
        return ""
    if len(items) > limit:
        return ", ".join(items[:limit]) + f" (+{len(items) - limit})"
    return ", ".join(items)


def _kv_pairs(values: Dict[str, Any]) -> str:
    parts = []
    for key, value in values.items():
        if value is None or value == "":
            continue
        parts.append(f"{key}={value}")
    return " ".join(parts)


def _summarize_event(event: str, payload: Any) -> str:
    if not isinstance(payload, dict):
        return f"payload_type={type(payload).__name__}"

    if event == "mcp.step.recorded":
        action_input = payload.get("action_input_KV_pairs")
        tool_id = None
        provider = None
        if isinstance(action_input, dict):
            tool_id = action_input.get("tool_id") or action_input.get("tool")
            provider = action_input.get("provider")
        obs_meta = payload.get("observation_metadata")
        is_smart_summary = obs_meta.get("is_smart_summary") if isinstance(obs_meta, dict) else None
        return _kv_pairs(
            {
                "step": payload.get("action_step"),
                "type": payload.get("action_type"),
                "success": payload.get("success"),
                "provider": provider,
                "tool_id": tool_id,
                "input_keys": _short_list(payload.get("action_input_keys")),
                "outcome_keys": _short_list(payload.get("action_outcome_keys")),
                "obs_keys": _short_list(payload.get("observation_keys")),
                "smart_summary": is_smart_summary,
                "error": _truncate_text(payload.get("error"), 120),
            }
        )

    if event == "mcp.search.completed":
        return _kv_pairs(
            {
                "query": _truncate_text(payload.get("query"), 120),
                "result_count": payload.get("result_count"),
                "tool_names": _short_list(payload.get("tool_names")),
                "tool_ids": _short_list(payload.get("tool_ids")),
            }
        )

    if event in {"mcp.action.planned", "mcp.action.started", "mcp.action.completed", "mcp.action.failed"}:
        provider = payload.get("provider") or payload.get("server")
        tool = payload.get("tool")
        return _kv_pairs(
            {
                "provider": provider,
                "tool": tool,
                "error": _truncate_text(payload.get("error"), 120),
                "transport": payload.get("transport"),
            }
        )

    if event == "mcp.action.request":
        return _kv_pairs(
            {
                "provider": payload.get("provider") or payload.get("server"),
                "tool": payload.get("tool"),
                "transport": payload.get("transport"),
            }
        )

    if event == "mcp.action.exception":
        return _kv_pairs(
            {
                "provider": payload.get("provider"),
                "tool": payload.get("tool"),
                "error": _truncate_text(payload.get("error"), 120),
            }
        )

    if event == "mcp.sandbox.run":
        return _kv_pairs(
            {
                "label": payload.get("label"),
                "success": payload.get("success"),
                "timed_out": payload.get("timed_out"),
                "log_lines": payload.get("log_lines"),
            }
        )

    if event in {"mcp.observation.tool_tokens", "mcp.observation.sandbox_tokens"}:
        return _kv_pairs(
            {
                "token_count": payload.get("token_count"),
                "threshold": payload.get("threshold"),
            }
        )

    if event == "mcp.observation.token_count_failed":
        return _kv_pairs(
            {
                "type": payload.get("type"),
                "error": _truncate_text(payload.get("error"), 120),
            }
        )

    if event == "mcp.observation_processor.completed":
        return _kv_pairs(
            {
                "type": payload.get("type"),
                "original_tokens": payload.get("original_tokens"),
                "compressed_tokens": payload.get("compressed_tokens"),
                "reduction_percent": payload.get("reduction_percent"),
            }
        )

    if event in {
        "mcp.observation_processor.serialization_error",
        "mcp.observation_processor.invalid_json",
        "mcp.observation_processor.failed",
    }:
        return _kv_pairs(
            {
                "type": payload.get("type"),
                "error": _truncate_text(payload.get("error"), 120),
            }
        )

    if event == "mcp.summary.created":
        return _kv_pairs(
            {
                "label": payload.get("label"),
                "purpose": payload.get("purpose"),
                "truncated": payload.get("truncated"),
            }
        )

    if event == "mcp.redaction.applied":
        return _kv_pairs(
            {
                "label": payload.get("label"),
                "purpose": payload.get("purpose"),
            }
        )

    if event == "mcp.high_signal":
        signals = payload.get("signals")
        signal_count = len(signals) if isinstance(signals, dict) else 0
        return _kv_pairs(
            {
                "provider": payload.get("provider"),
                "tool": payload.get("tool"),
                "success": payload.get("success"),
                "signal_count": signal_count,
            }
        )

    if event == "mcp.llm.completed":
        raw_output = payload.get("raw_output")
        raw_len = len(raw_output) if isinstance(raw_output, str) else 0
        return _kv_pairs({"raw_len": raw_len})

    if event in {"mcp.llm.skipped", "mcp.llm.json_mode.unsupported", "mcp.llm.retry_empty"}:
        return _kv_pairs(
            {
                "model": payload.get("model"),
                "reason": payload.get("reason"),
                "error": _truncate_text(payload.get("error"), 120),
            }
        )

    if event == "mcp.planner.protocol_error":
        raw_preview = payload.get("raw_preview")
        preview_len = len(raw_preview) if isinstance(raw_preview, str) else 0
        return _kv_pairs(
            {
                "error": _truncate_text(payload.get("error"), 120),
                "preview_len": preview_len,
            }
        )

    if event == "mcp.planner.failed":
        return _kv_pairs(
            {
                "reason": payload.get("reason"),
                "llm_preview": _truncate_text(payload.get("llm_preview"), 120),
            }
        )

    if event == "mcp.budget.exceeded":
        return _kv_pairs(
            {
                "budget_type": payload.get("budget_type"),
                "steps_taken": payload.get("steps_taken"),
                "cost": payload.get("cost"),
            }
        )

    if event == "mcp.task.started":
        task = payload.get("task")
        task_len = len(task) if isinstance(task, str) else 0
        return _kv_pairs(
            {
                "task_len": task_len,
                "step_id": payload.get("step_id"),
            }
        )

    if event == "mcp.task.completed":
        return _kv_pairs(
            {
                "success": payload.get("success"),
                "step_id": payload.get("step_id"),
            }
        )

    if event == "mcp.planner.started":
        budget = payload.get("budget")
        budget_keys = _short_list(budget.keys()) if isinstance(budget, dict) else ""
        return _kv_pairs(
            {
                "providers": len(payload.get("available_providers") or []),
                "budget_keys": budget_keys,
            }
        )

    if event == "mcp.toolbox.generated":
        return _kv_pairs(
            {
                "providers": payload.get("providers"),
                "fingerprint": payload.get("fingerprint"),
            }
        )

    if event == "mcp.actions.registration.completed":
        actions = payload.get("actions")
        return _kv_pairs({"actions": len(actions) if isinstance(actions, list) else 0})

    if event in {"mcp.actions.registration.skipped", "mcp.toolbox.refresh.failed"}:
        return _kv_pairs({"reason": payload.get("reason"), "error": _truncate_text(payload.get("error"), 120)})

    return _kv_pairs({"keys": _short_list(payload.keys(), limit=8)})


def log_mcp_event(event: str, payload: Any, *, source: str | None = None) -> None:
    if not event.startswith("mcp."):
        return
    if not _logging_enabled():
        return
    summary = _summarize_event(event, payload)
    if source:
        summary = f"src={source} {summary}".strip()
    logger.info("mcp.event %s %s", event, summary)
