from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from shared.db.engine import SessionLocal, DB_URL
from shared.db.sql import execute_text
from shared.db.user_metadata import (
    ERROR_STATUSES,
    RUN_METADATA_KEY,
    TERMINAL_STATUSES,
    update_user_metadata,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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


def _json_safe(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    try:
        json.dumps(value)
        return value
    except Exception:
        return str(value)


def _duration_ms(started_at: Any, ended_at: Any) -> Optional[int]:
    start_dt = _parse_dt(started_at)
    end_dt = _parse_dt(ended_at)
    if not start_dt or not end_dt:
        return None
    return int((end_dt - start_dt).total_seconds() * 1000)


def _recent_items(rows: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    if limit <= 0:
        return []
    return rows[:limit]


def _load_error_snapshot(
    db,
    *,
    run_id: str,
    workflow_id: Optional[str],
    status: Optional[str],
    summary: Optional[str],
) -> Dict[str, Any]:
    from shared.db.user_metadata import _build_error_snapshot  # type: ignore

    snapshot = _build_error_snapshot(
        db,
        run_id=run_id,
        workflow_id=workflow_id,
        status=status,
        summary=summary,
    )
    if snapshot is None:
        snapshot = {
            "run_id": run_id,
            "workflow_id": workflow_id,
            "status": status,
            "ended_at": None,
            "error_reason": summary or status or "error",
            "error_point": None,
            "event_ts": None,
        }
    return snapshot


def _fetch_user_ids(db) -> List[str]:
    rows = execute_text(db, "SELECT DISTINCT user_id FROM workflow_runs").fetchall()
    user_ids = {str(r[0]) for r in rows if r and r[0]}
    user_rows = execute_text(db, "SELECT id FROM users").fetchall()
    for row in user_rows:
        if row and row[0]:
            user_ids.add(str(row[0]))
    if DB_URL.startswith("postgres"):
        user_ids = {uid for uid in user_ids if _is_uuid(uid)}
    return sorted(user_ids)


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except Exception:
        return False


def _latest_event_ts(db, user_id: str) -> Optional[str]:
    row = execute_text(
        db,
        """
        SELECT MAX(re.ts)
        FROM run_events re
        JOIN workflow_runs wr ON wr.id = re.run_id
        WHERE wr.user_id = :user_id
        """,
        {"user_id": user_id},
    ).scalar_one_or_none()
    if not row:
        return None
    if isinstance(row, datetime):
        return row.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return str(row)


def build_metadata(db, user_id: str, *, recent_runs: int, recent_errors: int, active_hb_seconds: int) -> Dict[str, Any]:
    now_iso = _now_iso()
    rows = execute_text(
        db,
        """
        SELECT id, workflow_id, status, trigger_source, created_at, started_at, ended_at,
               summary, claimed_by, last_heartbeat_at, metadata
        FROM workflow_runs
        WHERE user_id = :user_id
        ORDER BY created_at DESC
        """,
        {"user_id": user_id},
    ).mappings().all()

    run_counters = {k: 0 for k in ("total", "terminal", "success", "error", "attention", "cancelled", "partial")}
    duration_ms = {"count": 0, "total": 0}
    credits = {"spent_total": 0, "last_debit_at": None}
    costs = {"input_cached": 0, "input_new": 0, "output": 0, "cost_usd_total": 0.0, "last_cost_update_at": None}

    recent_run_rows: List[Dict[str, Any]] = []
    error_rows: List[Dict[str, Any]] = []
    active_runs: List[Dict[str, Any]] = []

    for row in rows:
        status = row.get("status")
        run_counters["total"] += 1
        if status in TERMINAL_STATUSES:
            run_counters["terminal"] += 1
            if status in run_counters:
                run_counters[status] += 1

        metrics = _parse_json_dict(_parse_json_dict(row.get("metadata")).get(RUN_METADATA_KEY))
        credits_cost = metrics.get("credits_cost")
        if isinstance(credits_cost, (int, float)):
            credits["spent_total"] += int(credits_cost)
            created_at = row.get("created_at")
            if credits["last_debit_at"] is None and created_at is not None:
                created_iso = created_at.isoformat() if isinstance(created_at, datetime) else str(created_at)
                credits["last_debit_at"] = created_iso

        token_usage = _parse_json_dict(metrics.get("token_usage"))
        costs["input_cached"] += int(token_usage.get("input_cached", 0) or 0)
        costs["input_new"] += int(token_usage.get("input_new", 0) or 0)
        costs["output"] += int(token_usage.get("output", 0) or 0)
        costs["cost_usd_total"] += float(metrics.get("llm_cost_usd") or 0.0)

        duration_val = _duration_ms(row.get("started_at"), row.get("ended_at"))
        if duration_val is not None and status in TERMINAL_STATUSES:
            duration_ms["count"] += 1
            duration_ms["total"] += duration_val

        recent_run_rows.append(
            {
                "run_id": str(row.get("id")) if row.get("id") is not None else None,
                "workflow_id": str(row.get("workflow_id")) if row.get("workflow_id") is not None else None,
                "status": status,
                "trigger_source": row.get("trigger_source"),
                "created_at": row.get("created_at").isoformat() if isinstance(row.get("created_at"), datetime) else row.get("created_at"),
                "started_at": row.get("started_at").isoformat() if isinstance(row.get("started_at"), datetime) else row.get("started_at"),
                "ended_at": row.get("ended_at").isoformat() if isinstance(row.get("ended_at"), datetime) else row.get("ended_at"),
                "duration_ms": duration_val,
                "summary": row.get("summary"),
                "credits_cost": credits_cost,
                "llm_cost_usd": metrics.get("llm_cost_usd"),
                "token_usage": token_usage or None,
                "claimed_by": row.get("claimed_by"),
            }
        )

        if status in ERROR_STATUSES:
            error_rows.append(row)

        if status == "running":
            hb_dt = _parse_dt(row.get("last_heartbeat_at"))
            if hb_dt is None:
                continue
            age = (datetime.now(timezone.utc) - hb_dt).total_seconds()
            if age <= active_hb_seconds:
                active_runs.append(
                    {
                        "run_id": str(row.get("id")) if row.get("id") is not None else None,
                        "claimed_by": row.get("claimed_by"),
                        "started_at": row.get("started_at").isoformat() if isinstance(row.get("started_at"), datetime) else row.get("started_at"),
                        "last_heartbeat_at": row.get("last_heartbeat_at").isoformat() if isinstance(row.get("last_heartbeat_at"), datetime) else row.get("last_heartbeat_at"),
                    }
                )

    recent_runs = _recent_items(recent_run_rows, recent_runs)
    recent_errors_list: List[Dict[str, Any]] = []
    for row in error_rows[:recent_errors]:
        snapshot = _load_error_snapshot(
            db,
            run_id=str(row.get("id")) if row.get("id") is not None else "",
            workflow_id=str(row.get("workflow_id")) if row.get("workflow_id") is not None else None,
            status=row.get("status"),
            summary=row.get("summary"),
        )
        snapshot["ended_at"] = row.get("ended_at").isoformat() if isinstance(row.get("ended_at"), datetime) else row.get("ended_at")
        recent_errors_list.append(snapshot)

    active_workers: Dict[str, Dict[str, Any]] = {}
    for run in active_runs:
        claimed_by = run.get("claimed_by")
        if not claimed_by:
            continue
        entry = active_workers.get(claimed_by)
        if entry is None:
            entry = {"claimed_by": claimed_by, "run_ids": [], "last_heartbeat_at": None}
            active_workers[claimed_by] = entry
        entry["run_ids"].append(run.get("run_id"))
        hb = run.get("last_heartbeat_at")
        if hb and (entry["last_heartbeat_at"] is None or hb > entry["last_heartbeat_at"]):
            entry["last_heartbeat_at"] = hb

    costs["cost_usd_total"] = round(costs["cost_usd_total"], 8)
    if costs["cost_usd_total"] > 0:
        costs["last_cost_update_at"] = now_iso

    metadata = {
        "version": 1,
        "updated_at": now_iso,
        "run_counters": run_counters,
        "duration_ms": duration_ms,
        "credits": credits,
        "costs": costs,
        "recent_runs": recent_runs,
        "recent_errors": recent_errors_list,
        "active": {"runs": active_runs, "workers": list(active_workers.values())},
        "ingestion": {
            "last_run_update_at": now_iso,
            "last_event_ts": _latest_event_ts(db, user_id),
        },
    }
    return _json_safe(metadata)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill users.metadata from workflow_runs/run_events.")
    parser.add_argument("--dry-run", action="store_true", help="Compute but do not write updates.")
    parser.add_argument("--recent-runs", type=int, default=20, help="Recent runs to store per user.")
    parser.add_argument("--recent-errors", type=int, default=10, help="Recent errors to store per user.")
    parser.add_argument("--active-heartbeat-seconds", type=int, default=300, help="Heartbeat staleness threshold.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        user_ids = _fetch_user_ids(db)
        print(f"Found {len(user_ids)} users to backfill.")
        for user_id in user_ids:
            metadata = build_metadata(
                db,
                user_id,
                recent_runs=args.recent_runs,
                recent_errors=args.recent_errors,
                active_hb_seconds=args.active_heartbeat_seconds,
            )
            if args.dry_run:
                print(f"[dry-run] user_id={user_id} runs={metadata['run_counters']['total']}")
                continue

            def _replace(existing: Dict[str, Any], now_iso: str) -> None:
                existing.clear()
                existing.update(metadata)
                existing["updated_at"] = now_iso

            update_user_metadata(db, user_id, _replace)
            db.commit()
            print(f"Updated user_id={user_id} runs={metadata['run_counters']['total']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
