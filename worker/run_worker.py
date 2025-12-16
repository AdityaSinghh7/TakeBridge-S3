"""
Lightweight worker that dequeues queued workflow runs and triggers execution
via the server's internal execution endpoint. The server owns orchestration,
event persistence, and status updates; the worker only claims and triggers.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import platform
import sys
import time
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import requests
from sqlalchemy import text

from shared.db.engine import SessionLocal, DB_URL
from shared.supabase_client import get_service_supabase_client

logger = logging.getLogger(__name__)

INTERNAL_API_TOKEN = (os.getenv("INTERNAL_API_TOKEN") or "").strip()
# Default to https to match Procfile (self-signed local cert); override via env if needed.
EXECUTOR_BASE_URL = os.getenv("EXECUTOR_BASE_URL", "https://127.0.0.1:8000")
INTERNAL_VERIFY_SSL = os.getenv("INTERNAL_VERIFY_SSL", "false").lower() in {"1", "true", "yes"}
NOTIFY_CHANNEL = "workflow_run_queued"
IS_POSTGRES = DB_URL.startswith("postgres")
POLL_INTERVAL_SECONDS = float(os.getenv("WORKER_POLL_INTERVAL_SECONDS", "2"))
IDLE_LOG_EVERY_SECONDS = float(os.getenv("WORKER_IDLE_LOG_EVERY_SECONDS", "30"))
WORKER_CLAIMED_BY = os.getenv("WORKER_CLAIMED_BY") or f"worker@{platform.node()}:{os.getpid()}"


def _token_fingerprint(token: str) -> str:
    if not token:
        return "unset"
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:10]


def _summarize_db_url(db_url: str) -> str:
    """
    Return a safe, password-free DB URL summary for logs.
    """
    try:
        parsed = urlparse(db_url)
    except Exception:
        return "<invalid>"
    if parsed.scheme.startswith("sqlite"):
        return parsed.scheme
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    user = f"{parsed.username}@" if parsed.username else ""
    path = parsed.path or ""
    return f"{parsed.scheme}://{user}{host}{port}{path}"


def _get_db_identity() -> Dict[str, str]:
    db = SessionLocal()
    try:
        row = (
            db.execute(
                text(
                    """
                    SELECT current_database() AS database,
                           current_user AS user,
                           current_schema() AS schema
                    """
                )
            )
            .mappings()
            .first()
        )
        return {k: str(v) for k, v in dict(row).items()} if row else {}
    except Exception as exc:
        logger.warning("Failed to fetch DB identity: %s", exc)
        return {}
    finally:
        db.close()


def _get_queue_snapshot() -> Dict[str, Any]:
    db = SessionLocal()
    try:
        queued_count = int(
            db.execute(text("SELECT COUNT(*) FROM workflow_runs WHERE status = 'queued'")).scalar() or 0
        )
        oldest = (
            db.execute(
                text(
                    """
                    SELECT id, workflow_id, user_id, created_at
                    FROM workflow_runs
                    WHERE status = 'queued'
                    ORDER BY created_at ASC
                    LIMIT 1
                    """
                )
            )
            .mappings()
            .first()
        )
        newest = (
            db.execute(
                text(
                    """
                    SELECT id, status, claimed_by, created_at, summary
                    FROM workflow_runs
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                )
            )
            .mappings()
            .first()
        )
        return {
            "queued_count": queued_count,
            "oldest_queued": dict(oldest) if oldest else None,
            "newest": dict(newest) if newest else None,
        }
    except Exception as exc:
        logger.warning("Failed to fetch queue snapshot: %s", exc)
        return {}
    finally:
        db.close()


def _log_worker_startup() -> None:
    supabase_url_set = bool(os.getenv("SUPABASE_URL"))
    supabase_anon_set = bool(os.getenv("SUPABASE_ANON_KEY"))
    supabase_service_set = bool(os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
    internal_token_set = bool(INTERNAL_API_TOKEN)
    logger.info(
        "Worker starting pid=%s python=%s platform=%s cwd=%s",
        os.getpid(),
        sys.version.split()[0],
        platform.platform(),
        os.getcwd(),
    )
    logger.info(
        "Worker config claimed_by=%s poll_interval_s=%.2f idle_log_every_s=%.2f db=%s executor_base_url=%s verify_ssl=%s notify_channel=%s",
        WORKER_CLAIMED_BY,
        POLL_INTERVAL_SECONDS,
        IDLE_LOG_EVERY_SECONDS,
        _summarize_db_url(DB_URL),
        EXECUTOR_BASE_URL,
        INTERNAL_VERIFY_SSL,
        NOTIFY_CHANNEL,
    )
    logger.info(
        "Worker env INTERNAL_API_TOKEN_set=%s SUPABASE_URL_set=%s SUPABASE_ANON_KEY_set=%s SUPABASE_SERVICE_ROLE_KEY_set=%s",
        internal_token_set,
        supabase_url_set,
        supabase_anon_set,
        supabase_service_set,
    )
    if internal_token_set:
        logger.info("Worker INTERNAL_API_TOKEN fingerprint=%s", _token_fingerprint(INTERNAL_API_TOKEN))
    identity = _get_db_identity()
    if identity:
        logger.info(
            "Worker DB identity database=%s user=%s schema=%s",
            identity.get("database"),
            identity.get("user"),
            identity.get("schema"),
        )
    if IS_POSTGRES:
        logger.info("Worker DB is Postgres; run pickup is currently via polling (pg_notify wakeups not implemented in worker).")


def _json_safe(val: Any) -> Any:
    """Recursively coerce values to JSON-serializable forms."""
    try:
        import json

        json.dumps(val)
        return val
    except Exception:
        if isinstance(val, dict):
            return {k: _json_safe(v) for k, v in val.items()}
        if isinstance(val, (list, tuple)):
            return [_json_safe(v) for v in val]
        return str(val)


def claim_next_run(claimed_by: str) -> Optional[Dict[str, Any]]:
    """Atomically claim the oldest queued run."""
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                """
                WITH next_run AS (
                    SELECT id, workflow_id, user_id, created_at
                    FROM workflow_runs
                    WHERE status = 'queued'
                    ORDER BY created_at ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                )
                UPDATE workflow_runs wr
                SET status = 'running',
                    started_at = NOW(),
                    last_heartbeat_at = NOW(),
                    claimed_by = :claimed_by,
                    updated_at = NOW()
                FROM next_run
                WHERE wr.id = next_run.id
                RETURNING wr.id, wr.workflow_id, wr.user_id, wr.created_at
                """
            ),
            {"claimed_by": claimed_by},
        ).mappings().first()
        db.commit()
        return dict(row) if row else None
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to claim run: %s", exc)
        return None
    finally:
        db.close()


def update_run_status(run_id: str, status: str, summary: Optional[str] = None):
    db = SessionLocal()
    try:
        db.execute(
            text(
                """
                UPDATE workflow_runs
                SET status = :status,
                    summary = COALESCE(:summary, summary),
                    ended_at = CASE WHEN :terminal THEN NOW() ELSE ended_at END,
                    updated_at = NOW()
                WHERE id = :run_id
                """
            ),
            {
                "status": status,
                "summary": summary,
                "run_id": run_id,
                "terminal": status in {"success", "error", "attention", "cancelled"},
            },
        )
        db.commit()
        if summary:
            logger.info(
                "Updated run status run_id=%s status=%s summary_preview=%s",
                run_id,
                status,
                summary[:200],
            )
        else:
            logger.info("Updated run status run_id=%s status=%s", run_id, status)
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to update run status run_id=%s status=%s: %s", run_id, status, exc)
    finally:
        db.close()


def fetch_workflow(workflow_id: str) -> Dict[str, Any]:
    client = get_service_supabase_client()
    res = (
        client.table("workflows")
        .select("id,name,prompt,definition_json")
        .eq("id", workflow_id)
        .single()
        .execute()
    )
    if not res.data:
        raise RuntimeError("workflow_not_found")
    return res.data


def trigger_execution(run_id: str, workflow_id: str, user_id: str, task: str, composed_plan: Optional[Dict[str, Any]]):
    url = f"{EXECUTOR_BASE_URL}/internal/runs/{run_id}/execute"
    headers: Dict[str, str] = {}
    if INTERNAL_API_TOKEN:
        headers["X-Internal-Token"] = INTERNAL_API_TOKEN
        # Fallback for environments that strip custom headers.
        headers["Authorization"] = f"Bearer {INTERNAL_API_TOKEN}"
    verify_arg = os.getenv("REQUESTS_CA_BUNDLE") or os.getenv("CURL_CA_BUNDLE") or os.getenv("EXECUTOR_CA_BUNDLE")
    verify = verify_arg or INTERNAL_VERIFY_SSL
    payload = {
        "user_id": user_id,
        "workflow_id": workflow_id,
        "task": task,
        "composed_plan": composed_plan,
    }
    payload = _json_safe(payload)
    # Ensure full JSON-serializability (e.g., UUIDs) before sending
    payload = json.loads(json.dumps(payload, default=str))
    start = time.monotonic()
    session = requests.Session()
    # Avoid accidentally routing localhost calls through corporate/system proxies.
    try:
        parsed = urlparse(url)
        if (parsed.hostname or "").lower() in {"127.0.0.1", "localhost"}:
            session.trust_env = False
    except Exception:
        pass
    logger.info(
        "Calling executor run_id=%s workflow_id=%s url=%s verify=%s ca_bundle_set=%s internal_token_set=%s internal_token_fp=%s headers=%s trust_env=%s",
        run_id,
        workflow_id,
        url,
        bool(verify),
        bool(verify_arg),
        bool(INTERNAL_API_TOKEN),
        _token_fingerprint(INTERNAL_API_TOKEN),
        sorted(headers.keys()),
        session.trust_env,
    )
    with session.post(
        url,
        json=payload,
        headers=headers,
        stream=True,
        timeout=None,
        verify=verify,
    ) as resp:
        if resp.status_code >= 300:
            text_body = ""
            try:
                text_body = resp.text
            except Exception:
                pass
            logger.error(
                "Executor call failed run_id=%s workflow_id=%s status=%s body_preview=%s internal_token_fp=%s headers=%s",
                run_id,
                workflow_id,
                resp.status_code,
                text_body[:200],
                _token_fingerprint(INTERNAL_API_TOKEN),
                sorted(headers.keys()),
            )
            raise RuntimeError(f"execution call failed: status={resp.status_code} body={text_body[:200]}")
        # Consume stream to completion to let server run fully
        for _ in resp.iter_lines():
            pass
    elapsed_ms = int((time.monotonic() - start) * 1000)
    logger.info("Executor stream completed run_id=%s workflow_id=%s duration_ms=%s", run_id, workflow_id, elapsed_ms)


async def run_once(claimed_by: str = "worker") -> bool:
    claim = claim_next_run(claimed_by)
    if not claim:
        return False

    run_id = claim["id"]
    workflow_id = claim["workflow_id"]
    user_id = claim["user_id"]
    created_at = claim.get("created_at")
    if created_at is not None:
        logger.info(
            "Claimed run run_id=%s workflow_id=%s user_id=%s created_at=%s claimed_by=%s",
            run_id,
            workflow_id,
            user_id,
            created_at,
            claimed_by,
        )
    else:
        logger.info(
            "Claimed run run_id=%s workflow_id=%s user_id=%s claimed_by=%s",
            run_id,
            workflow_id,
            user_id,
            claimed_by,
        )

    try:
        wf = fetch_workflow(workflow_id)
        task_prompt = wf.get("prompt") or wf.get("name") or "task"
        composed_plan = wf.get("definition_json") or {}
        logger.info("Triggering execution for run %s workflow %s", run_id, workflow_id)
        trigger_execution(run_id, workflow_id, user_id, task_prompt, composed_plan)
    except Exception as exc:
        logger.exception("Run %s failed to trigger execution: %s", run_id, exc)
        update_run_status(run_id, "error", summary=str(exc))
    return True


async def worker_loop():
    """
    Simple loop to process queued runs.
    """
    last_idle_log = 0.0
    idle_checks = 0
    last_other_claimed_by: Optional[str] = None
    while True:
        try:
            processed = await run_once(claimed_by=WORKER_CLAIMED_BY)
        except Exception as exc:
            logger.exception("Unhandled worker loop error: %s", exc)
            processed = False
        if not processed:
            idle_checks += 1
            now = time.monotonic()
            if now - last_idle_log >= IDLE_LOG_EVERY_SECONDS:
                snapshot = _get_queue_snapshot()
                if snapshot:
                    newest = snapshot.get("newest") or {}
                    oldest_queued = snapshot.get("oldest_queued") or {}
                    newest_summary = newest.get("summary") or ""
                    newest_summary_preview = str(newest_summary)[:160] if newest_summary else ""
                    newest_claimed_by = newest.get("claimed_by")
                    if newest_claimed_by and newest_claimed_by != WORKER_CLAIMED_BY:
                        if newest_claimed_by != last_other_claimed_by:
                            logger.warning(
                                "Newest run appears claimed by a different worker newest_id=%s newest_status=%s claimed_by=%s this_worker=%s",
                                newest.get("id"),
                                newest.get("status"),
                                newest_claimed_by,
                                WORKER_CLAIMED_BY,
                            )
                            last_other_claimed_by = str(newest_claimed_by)
                    logger.info(
                        "Idle: no queued runs (checks=%s); sleeping %.2fs queued_count=%s newest_id=%s newest_status=%s newest_claimed_by=%s newest_summary=%s oldest_queued_id=%s",
                        idle_checks,
                        POLL_INTERVAL_SECONDS,
                        snapshot.get("queued_count"),
                        newest.get("id"),
                        newest.get("status"),
                        newest_claimed_by,
                        newest_summary_preview,
                        oldest_queued.get("id"),
                    )
                else:
                    logger.info(
                        "Idle: no queued runs (checks=%s); sleeping %.2fs",
                        idle_checks,
                        POLL_INTERVAL_SECONDS,
                    )
                last_idle_log = now
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
        else:
            idle_checks = 0


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    _log_worker_startup()
    asyncio.run(worker_loop())
