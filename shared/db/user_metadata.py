from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, Optional

from sqlalchemy.orm import Session

from shared.db.engine import DB_URL, SessionLocal
from shared.db.sql import execute_text

IS_PG = DB_URL.startswith("postgres")

RUN_METADATA_KEY = "_tb"

RECENT_RUNS_LIMIT = int(os.getenv("USER_METADATA_RECENT_RUNS_LIMIT", "20"))
RECENT_ERRORS_LIMIT = int(os.getenv("USER_METADATA_RECENT_ERRORS_LIMIT", "10"))
ACTIVE_HEARTBEAT_SECONDS = int(os.getenv("USER_METADATA_ACTIVE_HEARTBEAT_SECONDS", "300"))

TERMINAL_STATUSES = {"success", "error", "attention", "cancelled", "partial"}
ERROR_STATUSES = {"error", "attention"}

_RUN_USER_CACHE: Dict[str, str] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return str(value)


def _parse_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            if raw.endswith("Z"):
                raw = raw[:-1] + "+00:00"
            return datetime.fromisoformat(raw)
        except Exception:
            return None
    return None


def _parse_json_dict(value: Any) -> Dict[str, Any]:
    if not value:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
            return loaded if isinstance(loaded, dict) else {}
        except Exception:
            return {}
    try:
        return dict(value)
    except Exception:
        return {}


def _default_metadata(now_iso: str) -> Dict[str, Any]:
    return {
        "version": 1,
        "updated_at": now_iso,
        "run_counters": {
            "total": 0,
            "terminal": 0,
            "success": 0,
            "error": 0,
            "attention": 0,
            "cancelled": 0,
            "partial": 0,
        },
        "duration_ms": {
            "count": 0,
            "total": 0,
        },
        "credits": {
            "spent_total": 0,
            "last_debit_at": None,
        },
        "costs": {
            "input_cached": 0,
            "input_new": 0,
            "output": 0,
            "cost_usd_total": 0.0,
            "last_cost_update_at": None,
        },
        "recent_runs": [],
        "recent_errors": [],
        "active": {
            "runs": [],
            "workers": [],
        },
        "ingestion": {
            "last_run_update_at": None,
            "last_event_ts": None,
        },
    }


def default_user_metadata(now_iso: Optional[str] = None) -> Dict[str, Any]:
    now_iso = now_iso or _to_iso(_now()) or ""
    return _default_metadata(now_iso)


def _ensure_metadata_shape(metadata: Dict[str, Any], now_iso: str) -> Dict[str, Any]:
    if not metadata:
        return _default_metadata(now_iso)
    metadata.setdefault("version", 1)
    metadata.setdefault("updated_at", now_iso)

    run_counters = metadata.setdefault("run_counters", {})
    for key in ("total", "terminal", "success", "error", "attention", "cancelled", "partial"):
        run_counters.setdefault(key, 0)

    duration_ms = metadata.setdefault("duration_ms", {})
    duration_ms.setdefault("count", 0)
    duration_ms.setdefault("total", 0)

    credits = metadata.setdefault("credits", {})
    credits.setdefault("spent_total", 0)
    credits.setdefault("last_debit_at", None)

    costs = metadata.setdefault("costs", {})
    costs.setdefault("input_cached", 0)
    costs.setdefault("input_new", 0)
    costs.setdefault("output", 0)
    costs.setdefault("cost_usd_total", 0.0)
    costs.setdefault("last_cost_update_at", None)

    metadata.setdefault("recent_runs", [])
    metadata.setdefault("recent_errors", [])

    active = metadata.setdefault("active", {})
    active.setdefault("runs", [])
    active.setdefault("workers", [])

    ingestion = metadata.setdefault("ingestion", {})
    ingestion.setdefault("last_run_update_at", None)
    ingestion.setdefault("last_event_ts", None)

    return metadata


def _trim_list(items: list[Dict[str, Any]], limit: int) -> list[Dict[str, Any]]:
    if limit <= 0:
        return []
    return items[:limit]


def _upsert_recent_entry(
    items: list[Dict[str, Any]],
    run_id: str,
    updater: Callable[[Dict[str, Any]], None],
) -> Dict[str, Any]:
    idx = None
    for i, item in enumerate(items):
        if item.get("run_id") == run_id:
            idx = i
            break
    if idx is not None:
        entry = items.pop(idx)
    else:
        entry = {"run_id": run_id}
    updater(entry)
    items.insert(0, entry)
    return entry


def _status_is_terminal(status: Optional[str]) -> bool:
    return status in TERMINAL_STATUSES


def _status_is_error(status: Optional[str]) -> bool:
    return status in ERROR_STATUSES


def _adjust_counter(counter: Dict[str, Any], key: str, delta: int) -> None:
    if key not in counter:
        return
    counter[key] = max(int(counter.get(key, 0)) + delta, 0)


def _prune_active_runs(metadata: Dict[str, Any], now: datetime) -> None:
    active = metadata.get("active", {}) or {}
    runs = active.get("runs", []) or []
    if not runs:
        return
    pruned: list[Dict[str, Any]] = []
    for entry in runs:
        hb_raw = entry.get("last_heartbeat_at")
        hb_dt = _parse_dt(hb_raw)
        if hb_dt is None:
            pruned.append(entry)
            continue
        age = (now - hb_dt).total_seconds()
        if age <= ACTIVE_HEARTBEAT_SECONDS:
            pruned.append(entry)
    active["runs"] = pruned
    active["workers"] = _rebuild_active_workers(pruned)


def _rebuild_active_workers(runs: Iterable[Dict[str, Any]]) -> list[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for run in runs:
        claimed_by = run.get("claimed_by")
        if not claimed_by:
            continue
        entry = grouped.get(claimed_by)
        if entry is None:
            entry = {
                "claimed_by": claimed_by,
                "run_ids": [],
                "last_heartbeat_at": None,
            }
            grouped[claimed_by] = entry
        entry["run_ids"].append(run.get("run_id"))
        hb = run.get("last_heartbeat_at")
        if hb and (entry.get("last_heartbeat_at") is None or hb > entry.get("last_heartbeat_at")):
            entry["last_heartbeat_at"] = hb
    return list(grouped.values())


def _ensure_user_row(db: Session, user_id: str) -> None:
    metadata_json = json.dumps(_default_metadata(_to_iso(_now()) or ""), ensure_ascii=False)
    if IS_PG:
        execute_text(
            db,
            """
            INSERT INTO users (id, created_at, metadata)
            VALUES (:id, NOW(), :metadata)
            ON CONFLICT (id) DO NOTHING
            """,
            {"id": user_id, "metadata": metadata_json},
        )
    else:
        execute_text(
            db,
            """
            INSERT OR IGNORE INTO users (id, created_at, metadata)
            VALUES (:id, CURRENT_TIMESTAMP, :metadata)
            """,
            {"id": user_id, "metadata": metadata_json},
        )


def _load_user_metadata(db: Session, user_id: str) -> Dict[str, Any]:
    sql = "SELECT metadata FROM users WHERE id = :user_id"
    if IS_PG:
        sql += " FOR UPDATE"
    row = execute_text(db, sql, {"user_id": user_id}).scalar_one_or_none()
    return _parse_json_dict(row)


def update_user_metadata(
    db: Session,
    user_id: str,
    updater: Callable[[Dict[str, Any], str], None],
) -> Dict[str, Any]:
    now_iso = _to_iso(_now()) or ""
    _ensure_user_row(db, user_id)
    metadata = _load_user_metadata(db, user_id)
    metadata = _ensure_metadata_shape(metadata, now_iso)
    updater(metadata, now_iso)
    metadata["updated_at"] = now_iso
    execute_text(
        db,
        "UPDATE users SET metadata = :metadata WHERE id = :user_id",
        {"metadata": json.dumps(metadata, ensure_ascii=False, default=str), "user_id": user_id},
    )
    return metadata


def record_run_enqueued(
    db: Session,
    *,
    user_id: str,
    run_id: str,
    workflow_id: Optional[str],
    trigger_source: Optional[str],
    created_at: Optional[datetime],
    credits_cost: int,
) -> None:
    def _update(metadata: Dict[str, Any], now_iso: str) -> None:
        run_counters = metadata["run_counters"]
        credits = metadata["credits"]
        recent_runs = metadata["recent_runs"]

        def _apply(entry: Dict[str, Any]) -> None:
            entry["workflow_id"] = workflow_id
            entry["status"] = "queued"
            entry["trigger_source"] = trigger_source
            entry["created_at"] = _to_iso(created_at) or now_iso
            entry["credits_cost"] = credits_cost
            entry.setdefault("started_at", None)
            entry.setdefault("ended_at", None)
            entry.setdefault("duration_ms", None)
            entry.setdefault("summary", None)

        existing = next((r for r in recent_runs if r.get("run_id") == run_id), None)
        _upsert_recent_entry(recent_runs, run_id, _apply)
        metadata["recent_runs"] = _trim_list(recent_runs, RECENT_RUNS_LIMIT)

        if existing is None:
            _adjust_counter(run_counters, "total", 1)
            if credits_cost:
                credits["spent_total"] = int(credits.get("spent_total", 0)) + int(credits_cost)
                credits["last_debit_at"] = now_iso

        metadata["ingestion"]["last_run_update_at"] = now_iso

    update_user_metadata(db, user_id, _update)


def record_run_started(
    db: Session,
    *,
    user_id: str,
    run_id: str,
    claimed_by: Optional[str],
    started_at: Optional[datetime],
    last_heartbeat_at: Optional[datetime],
) -> None:
    def _update(metadata: Dict[str, Any], now_iso: str) -> None:
        run_counters = metadata["run_counters"]
        recent_runs = metadata["recent_runs"]
        active = metadata["active"]

        def _apply(entry: Dict[str, Any]) -> None:
            entry["status"] = "running"
            entry["started_at"] = _to_iso(started_at) or now_iso
            entry.setdefault("created_at", now_iso)
            if claimed_by:
                entry["claimed_by"] = claimed_by

        existing = next((r for r in recent_runs if r.get("run_id") == run_id), None)
        _upsert_recent_entry(recent_runs, run_id, _apply)
        metadata["recent_runs"] = _trim_list(recent_runs, RECENT_RUNS_LIMIT)
        if existing is None:
            _adjust_counter(run_counters, "total", 1)

        runs = active.get("runs", [])
        def _apply_active(entry: Dict[str, Any]) -> None:
            entry["claimed_by"] = claimed_by
            entry["started_at"] = _to_iso(started_at) or now_iso
            entry["last_heartbeat_at"] = _to_iso(last_heartbeat_at) or now_iso

        _upsert_recent_entry(runs, run_id, _apply_active)
        active["runs"] = runs
        active["workers"] = _rebuild_active_workers(runs)
        _prune_active_runs(metadata, _now())
        metadata["ingestion"]["last_run_update_at"] = now_iso

    update_user_metadata(db, user_id, _update)


def _extract_error_event(db: Session, run_id: str) -> Optional[Dict[str, Any]]:
    rows = execute_text(
        db,
        """
        SELECT kind, ts, message, payload
        FROM run_events
        WHERE run_id = :run_id
        ORDER BY ts DESC
        LIMIT 25
        """,
        {"run_id": run_id},
    ).mappings().all()
    if not rows:
        return None
    for row in rows:
        kind = row.get("kind") or ""
        payload = _parse_json_dict(row.get("payload"))
        if _event_indicates_error(kind, payload):
            return {
                "kind": kind,
                "ts": row.get("ts"),
                "message": row.get("message"),
                "payload": payload,
            }
    return None


def _event_indicates_error(kind: str, payload: Dict[str, Any]) -> bool:
    if kind in {"mcp.action.failed", "mcp.planner.failed", "response.failed", "response.error", "error"}:
        return True
    if payload.get("error"):
        return True
    if payload.get("success") is False:
        return True
    status = payload.get("status")
    if isinstance(status, str) and status.lower() in {"failed", "error", "attention"}:
        return True
    completion_reason = payload.get("completion_reason")
    if isinstance(completion_reason, str) and completion_reason.upper() in {"FAIL", "HANDOFF_TO_HUMAN"}:
        return True
    return False


def _build_error_snapshot(
    db: Session,
    *,
    run_id: str,
    workflow_id: Optional[str],
    status: Optional[str],
    summary: Optional[str],
) -> Optional[Dict[str, Any]]:
    event = _extract_error_event(db, run_id)
    if not event and not summary:
        return None

    error_reason = None
    error_point: Dict[str, Any] = {}
    event_ts = None

    if event:
        payload = event.get("payload") or {}
        error_reason = payload.get("error") or event.get("message")
        event_ts = _to_iso(event.get("ts"))
        error_point = {
            "event": event.get("kind"),
            "step_id": payload.get("step_id") or payload.get("step"),
            "tool": payload.get("tool_id")
            or (payload.get("action_input_KV_pairs") or {}).get("tool_id"),
            "message": payload.get("message") or payload.get("error") or event.get("message"),
        }

    if not error_reason:
        error_reason = summary or status or "error"

    return {
        "run_id": run_id,
        "workflow_id": workflow_id,
        "status": status,
        "ended_at": None,
        "error_reason": error_reason,
        "error_point": error_point or None,
        "event_ts": event_ts,
    }


def record_run_terminal(
    db: Session,
    *,
    run_id: str,
    status: str,
    summary: Optional[str] = None,
) -> None:
    row = execute_text(
        db,
        """
        SELECT id, workflow_id, user_id, trigger_source, created_at, started_at, ended_at,
               summary, metadata, claimed_by, last_heartbeat_at
        FROM workflow_runs
        WHERE id = :run_id
        """,
        {"run_id": run_id},
    ).mappings().first()
    if not row:
        return

    user_id = str(row.get("user_id"))
    workflow_id = row.get("workflow_id")
    created_at = row.get("created_at")
    started_at = row.get("started_at")
    ended_at = row.get("ended_at")
    run_summary = summary or row.get("summary")
    trigger_source = row.get("trigger_source")
    claimed_by = row.get("claimed_by")
    last_heartbeat_at = row.get("last_heartbeat_at")
    metadata_raw = _parse_json_dict(row.get("metadata"))
    metrics = _parse_json_dict(metadata_raw.get(RUN_METADATA_KEY))
    llm_cost_usd = metrics.get("llm_cost_usd")
    token_usage = _parse_json_dict(metrics.get("token_usage"))
    credits_cost = metrics.get("credits_cost")

    def _update(metadata: Dict[str, Any], now_iso: str) -> None:
        run_counters = metadata["run_counters"]
        duration_ms = metadata["duration_ms"]
        recent_runs = metadata["recent_runs"]
        recent_errors = metadata["recent_errors"]
        active = metadata["active"]

        def _apply(entry: Dict[str, Any]) -> None:
            entry["workflow_id"] = workflow_id
            entry["status"] = status
            entry["trigger_source"] = trigger_source
            entry["created_at"] = _to_iso(created_at) or now_iso
            entry["started_at"] = _to_iso(started_at)
            if _status_is_terminal(status):
                entry["ended_at"] = _to_iso(ended_at) or now_iso
            else:
                entry["ended_at"] = None
            entry["summary"] = run_summary
            if credits_cost is not None:
                entry["credits_cost"] = credits_cost
            if llm_cost_usd is not None:
                entry["llm_cost_usd"] = llm_cost_usd
            if token_usage:
                entry["token_usage"] = token_usage
            if claimed_by:
                entry["claimed_by"] = claimed_by

            duration_val = None
            if _status_is_terminal(status):
                start_dt = _parse_dt(started_at)
                end_dt = _parse_dt(ended_at) or _parse_dt(now_iso)
                if start_dt and end_dt:
                    duration_val = int((end_dt - start_dt).total_seconds() * 1000)
            entry["duration_ms"] = duration_val

        existing = next((r for r in recent_runs if r.get("run_id") == run_id), None)
        prev_status = existing.get("status") if existing else None
        prev_duration = existing.get("duration_ms") if existing else None
        prev_terminal = _status_is_terminal(prev_status)
        new_terminal = _status_is_terminal(status)

        entry = _upsert_recent_entry(recent_runs, run_id, _apply)
        metadata["recent_runs"] = _trim_list(recent_runs, RECENT_RUNS_LIMIT)

        if existing is None:
            _adjust_counter(run_counters, "total", 1)

        if prev_terminal and prev_status != status:
            _adjust_counter(run_counters, "terminal", -1)
            _adjust_counter(run_counters, prev_status, -1)
        if new_terminal and prev_status != status:
            _adjust_counter(run_counters, "terminal", 1)
            _adjust_counter(run_counters, status, 1)

        if prev_terminal and prev_duration is not None and prev_status != status:
            duration_ms["total"] = max(int(duration_ms.get("total", 0)) - int(prev_duration), 0)
            duration_ms["count"] = max(int(duration_ms.get("count", 0)) - 1, 0)
        if new_terminal and entry.get("duration_ms") is not None and prev_status != status:
            duration_ms["total"] = int(duration_ms.get("total", 0)) + int(entry.get("duration_ms"))
            duration_ms["count"] = int(duration_ms.get("count", 0)) + 1

        if _status_is_error(status):
            error_snapshot = None
            try:
                error_snapshot = _build_error_snapshot(
                    db,
                    run_id=run_id,
                    workflow_id=workflow_id,
                    status=status,
                    summary=run_summary,
                )
            except Exception:
                error_snapshot = None
            if error_snapshot:
                error_snapshot["ended_at"] = _to_iso(ended_at) or now_iso
                _upsert_recent_entry(
                    recent_errors,
                    run_id,
                    lambda e: e.update(error_snapshot),
                )
                metadata["recent_errors"] = _trim_list(recent_errors, RECENT_ERRORS_LIMIT)
        else:
            recent_errors = [e for e in recent_errors if e.get("run_id") != run_id]
            metadata["recent_errors"] = recent_errors

        runs = active.get("runs", [])
        runs = [r for r in runs if r.get("run_id") != run_id]
        active["runs"] = runs
        active["workers"] = _rebuild_active_workers(runs)
        _prune_active_runs(metadata, _now())
        metadata["ingestion"]["last_run_update_at"] = now_iso

    update_user_metadata(db, user_id, _update)


def record_run_event(
    db: Session,
    *,
    run_id: str,
    kind: str,
    message: Optional[str],
    payload: Optional[Dict[str, Any]],
    ts: Optional[datetime] = None,
) -> None:
    payload = payload or {}
    if not _event_indicates_error(kind, payload):
        return
    row = execute_text(
        db,
        "SELECT user_id, workflow_id, status FROM workflow_runs WHERE id = :run_id",
        {"run_id": run_id},
    ).mappings().first()
    if not row:
        return
    user_id = str(row.get("user_id"))
    workflow_id = row.get("workflow_id")
    status = row.get("status")

    def _update(metadata: Dict[str, Any], now_iso: str) -> None:
        recent_errors = metadata["recent_errors"]
        error_snapshot = {
            "run_id": run_id,
            "workflow_id": workflow_id,
            "status": status,
            "ended_at": None,
            "error_reason": payload.get("error") or message or kind,
            "error_point": {
                "event": kind,
                "step_id": payload.get("step_id") or payload.get("step"),
                "tool": payload.get("tool_id")
                or (payload.get("action_input_KV_pairs") or {}).get("tool_id"),
                "message": payload.get("message") or payload.get("error") or message,
            },
            "event_ts": _to_iso(ts) or now_iso,
        }
        _upsert_recent_entry(
            recent_errors,
            run_id,
            lambda e: e.update(error_snapshot),
        )
        metadata["recent_errors"] = _trim_list(recent_errors, RECENT_ERRORS_LIMIT)
        metadata["ingestion"]["last_event_ts"] = _to_iso(ts) or now_iso

    update_user_metadata(db, user_id, _update)


def record_token_usage(
    *,
    run_id: str,
    delta_tokens: Dict[str, int],
    delta_cost_usd: float,
    model: Optional[str] = None,
    source: Optional[str] = None,
    db: Optional[Session] = None,
) -> None:
    if not run_id:
        return
    token_sum = (
        int(delta_tokens.get("input_cached", 0))
        + int(delta_tokens.get("input_new", 0))
        + int(delta_tokens.get("output", 0))
    )
    if token_sum == 0 and not delta_cost_usd:
        return

    owns_session = db is None
    session = db or SessionLocal()
    try:
        user_id = _RUN_USER_CACHE.get(run_id)
        row = None
        if user_id is None:
            sql = "SELECT user_id, metadata FROM workflow_runs WHERE id = :run_id"
            if IS_PG:
                sql += " FOR UPDATE"
            row = execute_text(session, sql, {"run_id": run_id}).mappings().first()
            if not row:
                return
            user_id = str(row.get("user_id"))
            _RUN_USER_CACHE[run_id] = user_id
        if row is None:
            sql = "SELECT user_id, metadata FROM workflow_runs WHERE id = :run_id"
            if IS_PG:
                sql += " FOR UPDATE"
            row = execute_text(session, sql, {"run_id": run_id}).mappings().first()
            if not row:
                return

        metadata_raw = _parse_json_dict(row.get("metadata"))
        metrics = _parse_json_dict(metadata_raw.get(RUN_METADATA_KEY))
        token_usage = _parse_json_dict(metrics.get("token_usage"))
        token_usage.setdefault("input_cached", 0)
        token_usage.setdefault("input_new", 0)
        token_usage.setdefault("output", 0)

        token_usage["input_cached"] = int(token_usage.get("input_cached", 0)) + int(delta_tokens.get("input_cached", 0))
        token_usage["input_new"] = int(token_usage.get("input_new", 0)) + int(delta_tokens.get("input_new", 0))
        token_usage["output"] = int(token_usage.get("output", 0)) + int(delta_tokens.get("output", 0))

        prev_cost = float(metrics.get("llm_cost_usd") or 0.0)
        metrics["token_usage"] = token_usage
        metrics["llm_cost_usd"] = round(prev_cost + float(delta_cost_usd or 0.0), 8)
        metadata_raw[RUN_METADATA_KEY] = metrics

        execute_text(
            session,
            "UPDATE workflow_runs SET metadata = :metadata, updated_at = NOW() WHERE id = :run_id",
            {"metadata": json.dumps(metadata_raw, ensure_ascii=False, default=str), "run_id": run_id},
        )

        def _update_user(metadata: Dict[str, Any], now_iso: str) -> None:
            costs = metadata["costs"]
            costs["input_cached"] = int(costs.get("input_cached", 0)) + int(delta_tokens.get("input_cached", 0))
            costs["input_new"] = int(costs.get("input_new", 0)) + int(delta_tokens.get("input_new", 0))
            costs["output"] = int(costs.get("output", 0)) + int(delta_tokens.get("output", 0))
            costs["cost_usd_total"] = round(float(costs.get("cost_usd_total", 0.0)) + float(delta_cost_usd or 0.0), 8)
            costs["last_cost_update_at"] = now_iso

        update_user_metadata(session, user_id, _update_user)

        if len(_RUN_USER_CACHE) > 10000:
            _RUN_USER_CACHE.clear()

        if owns_session:
            session.commit()
    except Exception:
        if owns_session:
            session.rollback()
        raise
    finally:
        if owns_session:
            session.close()


__all__ = [
    "default_user_metadata",
    "record_run_enqueued",
    "record_run_started",
    "record_run_terminal",
    "record_run_event",
    "record_token_usage",
    "record_run_heartbeat",
]


def record_run_heartbeat(db: Session, *, run_id: str) -> None:
    row = execute_text(
        db,
        """
        SELECT user_id, status, claimed_by, started_at, last_heartbeat_at
        FROM workflow_runs
        WHERE id = :run_id
        """,
        {"run_id": run_id},
    ).mappings().first()
    if not row:
        return
    if row.get("status") != "running":
        return
    user_id = str(row.get("user_id"))
    claimed_by = row.get("claimed_by")
    started_at = row.get("started_at")
    last_heartbeat_at = row.get("last_heartbeat_at")

    def _update(metadata: Dict[str, Any], now_iso: str) -> None:
        active = metadata["active"]
        runs = active.get("runs", [])

        def _apply(entry: Dict[str, Any]) -> None:
            entry["claimed_by"] = claimed_by
            entry["started_at"] = _to_iso(started_at) or entry.get("started_at") or now_iso
            entry["last_heartbeat_at"] = _to_iso(last_heartbeat_at) or now_iso

        _upsert_recent_entry(runs, run_id, _apply)
        active["runs"] = runs
        active["workers"] = _rebuild_active_workers(runs)
        _prune_active_runs(metadata, _now())

    update_user_metadata(db, user_id, _update)
