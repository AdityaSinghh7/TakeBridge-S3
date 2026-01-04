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
import random
import sys
import time
from select import select
from typing import Any, Callable, Dict, Optional, TypeVar
from urllib.parse import urlparse

import requests
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, DisconnectionError, InvalidatePoolError, OperationalError

from shared.db.engine import SessionLocal, DB_URL, engine
from shared.db import workflow_runs
from shared.supabase_client import get_service_supabase_client

logger = logging.getLogger(__name__)

INTERNAL_API_TOKEN = (os.getenv("INTERNAL_API_TOKEN") or "").strip()
# Default to https to match Procfile (self-signed local cert); override via env if needed.
EXECUTOR_BASE_URL = os.getenv("EXECUTOR_BASE_URL", "https://127.0.0.1:8000")
INTERNAL_VERIFY_SSL = os.getenv("INTERNAL_VERIFY_SSL", "false").lower() in {"1", "true", "yes"}
NOTIFY_CHANNEL = "workflow_run_queued"
IS_POSTGRES = DB_URL.startswith("postgres")
# Poll interval is only used for the non-Postgres fallback.
POLL_INTERVAL_SECONDS = float(os.getenv("WORKER_POLL_INTERVAL_SECONDS", "10"))
IDLE_LOG_EVERY_SECONDS = float(os.getenv("WORKER_IDLE_LOG_EVERY_SECONDS", "30"))
RECONCILE_EVERY_SECONDS = float(os.getenv("WORKER_RECONCILE_EVERY_SECONDS", "600"))
IDLE_SNAPSHOT_EVERY_SECONDS = float(os.getenv("WORKER_IDLE_SNAPSHOT_EVERY_SECONDS", "600"))
WORKER_CLAIMED_BY = os.getenv("WORKER_CLAIMED_BY") or f"worker@{platform.node()}:{os.getpid()}"

DB_RETRY_MAX_ATTEMPTS = int(os.getenv("WORKER_DB_RETRY_MAX_ATTEMPTS", "5"))
DB_RETRY_BACKOFF_BASE_SECONDS = float(os.getenv("WORKER_DB_RETRY_BACKOFF_BASE_SECONDS", "0.5"))
DB_RETRY_BACKOFF_MAX_SECONDS = float(os.getenv("WORKER_DB_RETRY_BACKOFF_MAX_SECONDS", "10"))
DB_RETRY_BACKOFF_JITTER_SECONDS = float(os.getenv("WORKER_DB_RETRY_BACKOFF_JITTER_SECONDS", "0.25"))
LISTEN_RETRY_BACKOFF_BASE_SECONDS = float(os.getenv("WORKER_LISTEN_RETRY_BACKOFF_BASE_SECONDS", "1"))
LISTEN_RETRY_BACKOFF_MAX_SECONDS = float(os.getenv("WORKER_LISTEN_RETRY_BACKOFF_MAX_SECONDS", "30"))
LISTEN_RETRY_BACKOFF_JITTER_SECONDS = float(os.getenv("WORKER_LISTEN_RETRY_BACKOFF_JITTER_SECONDS", "0.5"))

T = TypeVar("T")


class OAuthRefreshRequiredError(RuntimeError):
    def __init__(self, detail: Dict[str, Any]):
        super().__init__("oauth_refresh_required")
        self.detail = detail or {}
        self.providers = self.detail.get("providers") or []
        self.reasons = self.detail.get("reasons") or {}


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


def _normalize_postgres_url(db_url: str) -> str:
    if "://" not in db_url:
        return db_url
    if db_url.startswith("postgresql+"):
        return "postgresql://" + db_url.split("://", 1)[1]
    if db_url.startswith("postgres+"):
        return "postgres://" + db_url.split("://", 1)[1]
    return db_url


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


def _is_retryable_db_error(exc: Exception) -> bool:
    if isinstance(exc, (DisconnectionError, InvalidatePoolError)):
        return True
    if isinstance(exc, DBAPIError) and bool(getattr(exc, "connection_invalidated", False)):
        return True
    if isinstance(exc, OperationalError):
        msg = str(exc).lower()
        transient_markers = (
            "ssl connection has been closed unexpectedly",
            "server closed the connection unexpectedly",
            "connection to server at",
            "could not connect to server",
            "connection refused",
            "connection reset by peer",
            "connection timed out",
            "timeout expired",
            "terminating connection due to administrator command",
            "the database system is starting up",
            "the database system is shutting down",
            "broken pipe",
        )
        if any(marker in msg for marker in transient_markers):
            return True
    return False


def _db_backoff_seconds(attempt: int) -> float:
    base = max(0.0, DB_RETRY_BACKOFF_BASE_SECONDS)
    cap = max(base, DB_RETRY_BACKOFF_MAX_SECONDS)
    delay = min(cap, base * (2 ** max(0, attempt - 1)))
    jitter = max(0.0, DB_RETRY_BACKOFF_JITTER_SECONDS)
    if jitter:
        delay += random.uniform(0.0, jitter)
    return delay


def _listen_backoff_seconds(attempt: int) -> float:
    base = max(0.0, LISTEN_RETRY_BACKOFF_BASE_SECONDS)
    cap = max(base, LISTEN_RETRY_BACKOFF_MAX_SECONDS)
    delay = min(cap, base * (2 ** max(0, attempt - 1)))
    jitter = max(0.0, LISTEN_RETRY_BACKOFF_JITTER_SECONDS)
    if jitter:
        delay += random.uniform(0.0, jitter)
    return delay


def _reset_db_pool(reason: str, exc: Optional[Exception] = None) -> None:
    try:
        engine.dispose()
        logger.debug("Disposed DB connection pool (%s)", reason)
    except Exception as dispose_exc:
        logger.debug(
            "Failed to dispose DB connection pool reason=%s err=%s orig_err=%s",
            reason,
            dispose_exc,
            exc,
        )


def _connect_listen_connection() -> Any:
    try:
        import psycopg2
        from psycopg2 import sql as pg_sql
        from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
    except Exception as exc:
        raise RuntimeError("psycopg2 is required for Postgres LISTEN/NOTIFY") from exc

    conn = psycopg2.connect(_normalize_postgres_url(DB_URL))
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    with conn.cursor() as cur:
        cur.execute(pg_sql.SQL("LISTEN {}").format(pg_sql.Identifier(NOTIFY_CHANNEL)))
    return conn


def _wait_for_notifications(conn: Any, timeout: Optional[float]) -> list[Any]:
    if conn is None or getattr(conn, "closed", 1):
        raise RuntimeError("listen_connection_closed")
    timeout_val = None if timeout is None else max(0.0, float(timeout))
    ready = select([conn], [], [], timeout_val)
    if not ready[0]:
        return []
    conn.poll()
    notifies = []
    while conn.notifies:
        notifies.append(conn.notifies.pop(0))
    return notifies


def _with_db_retry(op_name: str, fn: Callable[[], T]) -> T:
    max_attempts = max(1, int(DB_RETRY_MAX_ATTEMPTS))
    last_exc: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt >= max_attempts or not _is_retryable_db_error(exc):
                raise
            backoff = _db_backoff_seconds(attempt)
            logger.warning(
                "Transient DB error during %s (attempt %s/%s): %s; retrying in %.2fs",
                op_name,
                attempt,
                max_attempts,
                exc,
                backoff,
            )
            _reset_db_pool(op_name, exc)
            time.sleep(backoff)
    # Should be unreachable, but keeps type checkers happy.
    assert last_exc is not None
    raise last_exc


def _get_queue_snapshot() -> Dict[str, Any]:
    def _op() -> Dict[str, Any]:
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
        finally:
            db.close()

    try:
        return _with_db_retry("_get_queue_snapshot", _op)
    except Exception as exc:
        logger.warning("Failed to fetch queue snapshot after retries: %s", exc)
        return {}


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
        "Worker config claimed_by=%s poll_interval_s=%.2f idle_log_every_s=%.2f reconcile_every_s=%.2f idle_snapshot_every_s=%.2f db=%s executor_base_url=%s verify_ssl=%s notify_channel=%s",
        WORKER_CLAIMED_BY,
        POLL_INTERVAL_SECONDS,
        IDLE_LOG_EVERY_SECONDS,
        RECONCILE_EVERY_SECONDS,
        IDLE_SNAPSHOT_EVERY_SECONDS,
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
        logger.info(
            "Worker DB is Postgres; run pickup uses LISTEN/NOTIFY with reconciliation every %.2fs.",
            RECONCILE_EVERY_SECONDS,
        )
    else:
        logger.info(
            "Worker DB is not Postgres; using polling fallback every %.2fs.",
            POLL_INTERVAL_SECONDS,
        )


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


def _summarize_notify_payload(payload: Optional[str]) -> str:
    if not payload:
        return ""
    try:
        parsed = json.loads(payload)
        if isinstance(parsed, dict):
            run_id = parsed.get("run_id")
            user_id = parsed.get("user_id")
            parts = []
            if run_id:
                parts.append(f"run_id={run_id}")
            if user_id:
                parts.append(f"user_id={user_id}")
            if parts:
                return " ".join(parts)
    except Exception:
        pass
    return str(payload)[:200]


def claim_next_run(claimed_by: str) -> Optional[Dict[str, Any]]:
    """Atomically claim the oldest queued run."""
    def _op() -> Optional[Dict[str, Any]]:
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
                    RETURNING wr.id, wr.workflow_id, wr.user_id, wr.created_at,
                              wr.started_at, wr.last_heartbeat_at, wr.claimed_by
                    """
                ),
                {"claimed_by": claimed_by},
            ).mappings().first()
            db.commit()
            return dict(row) if row else None
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    try:
        return _with_db_retry("claim_next_run", _op)
    except Exception as exc:
        logger.exception("Failed to claim run after retries: %s", exc)
        return None


def update_run_status(run_id: str, status: str, summary: Optional[str] = None):
    def _op() -> None:
        db = SessionLocal()
        try:
            workflow_runs.update_status(
                db,
                run_id=run_id,
                status=status,
                summary=summary,
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    try:
        _with_db_retry("update_run_status", _op)
    except Exception as exc:
        logger.exception("Failed to update run status after retries run_id=%s status=%s: %s", run_id, status, exc)
        return
    if summary:
        logger.info(
            "Updated run status run_id=%s status=%s summary_preview=%s",
            run_id,
            status,
            summary[:200],
        )
    else:
        logger.info("Updated run status run_id=%s status=%s", run_id, status)


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
            error_detail: Dict[str, Any] = {}
            try:
                text_body = resp.text
            except Exception:
                pass
            try:
                payload_json = resp.json()
                if isinstance(payload_json, dict):
                    detail = payload_json.get("detail")
                    error_detail = detail if isinstance(detail, dict) else payload_json
            except Exception:
                pass
            if resp.status_code == 409 and error_detail.get("error") == "oauth_refresh_required":
                raise OAuthRefreshRequiredError(error_detail)
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
    started_at = claim.get("started_at")
    last_heartbeat_at = claim.get("last_heartbeat_at")
    claimed_by = claim.get("claimed_by") or claimed_by
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

    db = SessionLocal()
    try:
        from shared.db.user_metadata import record_run_started

        record_run_started(
            db,
            user_id=user_id,
            run_id=run_id,
            claimed_by=claimed_by,
            started_at=started_at,
            last_heartbeat_at=last_heartbeat_at,
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("Failed to update user metadata for run start run_id=%s: %s", run_id, exc)
    finally:
        db.close()

    try:
        wf = fetch_workflow(workflow_id)
        definition_json = wf.get("definition_json") or {}
        task_prompt = (
            definition_json.get("combined_prompt")
        )
        task_prompt = str(task_prompt)
        composed_plan = definition_json
        logger.info("Triggering execution for run %s workflow %s task_prompt=%s", run_id, workflow_id, task_prompt)
        trigger_execution(run_id, workflow_id, user_id, task_prompt, composed_plan)
    except OAuthRefreshRequiredError as exc:
        logger.warning(
            "Run %s blocked by oauth refresh required providers=%s reasons=%s",
            run_id,
            exc.providers,
            exc.reasons,
        )
        update_run_status(run_id, "attention", summary="oauth_refresh_required")
    except Exception as exc:
        logger.exception("Run %s failed to trigger execution: %s", run_id, exc)
        update_run_status(run_id, "error", summary=str(exc))
    return True


async def _drain_queue(claimed_by: str) -> bool:
    processed_any = False
    while True:
        try:
            processed = await run_once(claimed_by=claimed_by)
        except Exception as exc:
            logger.exception("Unhandled worker loop error: %s", exc)
            processed = False
        if not processed:
            break
        processed_any = True
    return processed_any


async def _worker_loop_postgres() -> None:
    last_idle_log = 0.0
    last_snapshot_log = 0.0
    idle_checks = 0
    last_other_claimed_by: Optional[str] = None
    last_notify_payload: Optional[str] = None
    reconnect_attempt = 0
    next_reconcile = None
    if RECONCILE_EVERY_SECONDS > 0:
        next_reconcile = time.monotonic() + RECONCILE_EVERY_SECONDS

    await _drain_queue(claimed_by=WORKER_CLAIMED_BY)

    while True:
        listen_conn = None
        try:
            listen_conn = _connect_listen_connection()
            reconnect_attempt = 0
            logger.info("Listening for queued runs channel=%s", NOTIFY_CHANNEL)
            processed_any = await _drain_queue(claimed_by=WORKER_CLAIMED_BY)
            if processed_any:
                idle_checks = 0
            while True:
                now = time.monotonic()
                timeouts = []
                if IDLE_LOG_EVERY_SECONDS > 0:
                    timeouts.append(last_idle_log + IDLE_LOG_EVERY_SECONDS)
                if next_reconcile is not None:
                    timeouts.append(next_reconcile)
                timeout = None
                if timeouts:
                    timeout = max(0.0, min(timeouts) - now)

                notifies = await asyncio.to_thread(_wait_for_notifications, listen_conn, timeout)
                if notifies:
                    last_notify_payload = _summarize_notify_payload(notifies[-1].payload)
                    logger.info(
                        "Received run queue notification count=%s last_payload=%s",
                        len(notifies),
                        last_notify_payload or "none",
                    )
                    processed_any = await _drain_queue(claimed_by=WORKER_CLAIMED_BY)
                    if processed_any:
                        idle_checks = 0
                    else:
                        idle_checks += 1

                now = time.monotonic()
                if next_reconcile is not None and now >= next_reconcile:
                    logger.info("Reconciliation sweep triggered; draining queue.")
                    processed_any = await _drain_queue(claimed_by=WORKER_CLAIMED_BY)
                    if processed_any:
                        idle_checks = 0
                    else:
                        idle_checks += 1
                    next_reconcile = now + RECONCILE_EVERY_SECONDS

                if IDLE_LOG_EVERY_SECONDS > 0 and now - last_idle_log >= IDLE_LOG_EVERY_SECONDS:
                    snapshot = None
                    if IDLE_SNAPSHOT_EVERY_SECONDS > 0 and now - last_snapshot_log >= IDLE_SNAPSHOT_EVERY_SECONDS:
                        snapshot = _get_queue_snapshot()
                        last_snapshot_log = now
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
                            "Idle: no queued runs (checks=%s); waiting for notifications queued_count=%s newest_id=%s newest_status=%s newest_claimed_by=%s newest_summary=%s oldest_queued_id=%s last_notify=%s",
                            idle_checks,
                            snapshot.get("queued_count"),
                            newest.get("id"),
                            newest.get("status"),
                            newest_claimed_by,
                            newest_summary_preview,
                            oldest_queued.get("id"),
                            last_notify_payload or "none",
                        )
                    else:
                        logger.info(
                            "Idle: no queued runs (checks=%s); waiting for notifications last_notify=%s",
                            idle_checks,
                            last_notify_payload or "none",
                        )
                    last_idle_log = now
        except Exception as exc:
            logger.exception("Worker LISTEN loop error: %s", exc)
            if listen_conn is not None:
                try:
                    listen_conn.close()
                except Exception:
                    pass
            reconnect_attempt += 1
            backoff = _listen_backoff_seconds(reconnect_attempt)
            logger.warning("Reconnecting LISTEN in %.2fs", backoff)
            await asyncio.sleep(backoff)


async def _worker_loop_polling() -> None:
    last_idle_log = 0.0
    idle_checks = 0
    last_other_claimed_by: Optional[str] = None
    while True:
        processed_any = await _drain_queue(claimed_by=WORKER_CLAIMED_BY)
        if not processed_any:
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


async def worker_loop():
    """
    Process queued runs with LISTEN/NOTIFY on Postgres and polling fallback elsewhere.
    """
    if IS_POSTGRES:
        await _worker_loop_postgres()
    else:
        await _worker_loop_polling()


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    _log_worker_startup()
    asyncio.run(worker_loop())
