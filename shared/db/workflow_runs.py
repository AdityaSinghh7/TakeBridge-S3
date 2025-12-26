from __future__ import annotations

import base64
import gzip
import json
import logging
import os
import random
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from .engine import DB_URL, SessionLocal
from .sql import execute_text

logger = logging.getLogger(__name__)

_AGENT_STATES_MAX_RETRIES = int(os.getenv("AGENT_STATES_DB_RETRIES", "2"))
_AGENT_STATES_RETRY_BACKOFF_BASE = float(os.getenv("AGENT_STATES_DB_RETRY_BACKOFF_BASE", "0.25"))
_AGENT_STATES_RETRY_BACKOFF_CAP = float(os.getenv("AGENT_STATES_DB_RETRY_BACKOFF_CAP", "2.0"))
_AGENT_STATES_RETRY_BACKOFF_JITTER = float(os.getenv("AGENT_STATES_DB_RETRY_BACKOFF_JITTER", "0.25"))


def _is_retryable_db_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(
        token in message
        for token in (
            "ssl",
            "tls",
            "bad record mac",
            "connection",
            "server closed",
            "could not connect",
            "connection reset",
            "connection aborted",
            "connection refused",
            "timeout",
            "terminating connection",
        )
    )


def _sleep_with_backoff(attempt: int) -> None:
    if _AGENT_STATES_RETRY_BACKOFF_BASE <= 0:
        return
    delay = min(
        _AGENT_STATES_RETRY_BACKOFF_CAP,
        _AGENT_STATES_RETRY_BACKOFF_BASE * (2**attempt),
    )
    if _AGENT_STATES_RETRY_BACKOFF_JITTER:
        delay += random.uniform(0.0, _AGENT_STATES_RETRY_BACKOFF_JITTER)
    time.sleep(delay)


def _run_with_retry(
    *,
    label: str,
    db: Optional[Session],
    op: Callable[[Session, bool], int],
) -> int:
    owns_session = db is None
    session = db or SessionLocal()
    max_attempts = _AGENT_STATES_MAX_RETRIES + 1
    try:
        for attempt in range(max_attempts):
            try:
                return op(session, owns_session)
            except OperationalError as exc:
                if owns_session:
                    session.rollback()
                if (
                    not owns_session
                    or attempt >= _AGENT_STATES_MAX_RETRIES
                    or not _is_retryable_db_error(exc)
                ):
                    raise
                logger.warning(
                    "%s failed due to database error; retrying attempt=%s/%s error=%s",
                    label,
                    attempt + 1,
                    max_attempts,
                    exc,
                )
                if owns_session:
                    session.close()
                    session = SessionLocal()
                _sleep_with_backoff(attempt)
            except Exception:
                if owns_session:
                    session.rollback()
                raise
    finally:
        if owns_session:
            session.close()


def _deep_merge(dest: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge src into dest (mutates dest)."""
    for key, val in src.items():
        if key in dest and isinstance(dest[key], dict) and isinstance(val, dict):
            _deep_merge(dest[key], val)
        else:
            dest[key] = val
    return dest


def _ensure_path(root: Dict[str, Any], path: Optional[list[str]]) -> Dict[str, Any]:
    """Ensure nested dict path exists; return the dict at that path."""
    node = root
    if not path:
        return node
    for key in path:
        if key not in node or not isinstance(node.get(key), dict):
            node[key] = {}
        node = node[key]
    return node


def _json_safe(val: Any) -> str:
    """
    Convert payload to a JSON string for PostgreSQL JSONB columns.
    
    psycopg2 with raw SQL text() cannot adapt Python dicts directly to JSONB,
    so we must serialize to a JSON string which PostgreSQL will parse.
    
    Falls back to string conversion for unsupported types.
    """
    try:
        return json.dumps(val)
    except Exception:
        try:
            return json.dumps(val, default=str)
        except Exception:
            logger.warning("agent_states payload not JSON-serializable; coercing to string")
            return json.dumps(str(val))


def _compress_agent_states(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compress agent_states into a JSON-safe wrapper.

    Uses zstd when available, otherwise gzip. Always returns a JSON-serializable
    wrapper; callers must not store the raw payload to avoid oversized rows.
    """
    try:
        raw = json.dumps(payload, default=str).encode("utf-8")
    except Exception as exc:
        raise ValueError(f"agent_states not serializable for compression: {exc}") from exc

    codec = "gzip"
    compressed = None
    try:
        import zstandard as zstd  # type: ignore

        compressed = zstd.ZstdCompressor(level=4).compress(raw)
        codec = "zstd"
    except Exception:
        compressed = gzip.compress(raw)

    b64 = base64.b64encode(compressed).decode("ascii")
    return {"_encoding": f"{codec}_b64", "data": b64}


def _decompress_agent_states(value: Any) -> Dict[str, Any]:
    """
    Decompress agent_states wrapper into a dict.

    - Legacy (raw dict) is returned as-is.
    - Wrapper with _encoding is decoded/decompressed.
    - Failures return {} to avoid crashes.
    """
    if isinstance(value, dict) and "_encoding" not in value:
        return value

    # Handle legacy JSON string or wrapper serialized as text
    if not isinstance(value, dict):
        try:
            value = json.loads(value) if value else {}
        except Exception:
            return {}

    encoding = value.get("_encoding")
    data_b64 = value.get("data")
    if not encoding or not data_b64:
        return value if isinstance(value, dict) else {}

    try:
        compressed = base64.b64decode(data_b64)
        if encoding.startswith("zstd"):
            import zstandard as zstd  # type: ignore

            raw = zstd.ZstdDecompressor().decompress(compressed)
        elif encoding.startswith("gzip"):
            raw = gzip.decompress(compressed)
        else:
            logger.warning("Unknown agent_states encoding %s; returning legacy value", encoding)
            return value if isinstance(value, dict) else {}
        return json.loads(raw.decode("utf-8"))
    except Exception as exc:
        logger.error("Failed to decompress agent_states: %s", exc)
        return {}


def update_agent_states(
    run_id: str,
    agent_states: Dict[str, Any],
    *,
    db: Optional[Session] = None,
) -> int:
    """
    Persist the latest agent_states snapshot for a workflow run.

    Args:
        run_id: workflow_runs.id to update
        agent_states: full JSON-safe snapshot to store
        db: optional existing Session; if omitted, a session is created/closed

    Returns:
        Number of rows updated (0 when run_id not found)
    """
    if not run_id:
        raise ValueError("run_id is required")

    compressed = _compress_agent_states(agent_states)

    def _op(session: Session, owns_session: bool) -> int:
        now = datetime.now(timezone.utc)
        result = session.execute(
            text(
                """
                UPDATE workflow_runs
                SET agent_states = :agent_states,
                    agent_states_updated_at = :updated_at,
                    updated_at = :updated_at
                WHERE id = :run_id
                """
            ),
            {
                "run_id": run_id,
                "agent_states": _json_safe(compressed),
                "updated_at": now,
            },
        )
        if owns_session:
            session.commit()
        return result.rowcount or 0

    return _run_with_retry(label="update_agent_states", db=db, op=_op)


def merge_agent_states(
    run_id: str,
    patch: Dict[str, Any],
    *,
    path: Optional[list[str]] = None,
    db: Optional[Session] = None,
) -> int:
    """
    Merge a patch into agent_states (read-modify-write). Useful for per-agent partial updates.

    Args:
        run_id: workflow_runs.id to update
        patch: dict to merge
        path: optional list of keys to merge under (e.g., ["agents", "mcp"])
        db: optional existing Session

    Returns:
        Number of rows updated (0 when run_id not found)
    """
    if not run_id:
        raise ValueError("run_id is required")
    if not isinstance(patch, dict):
        raise ValueError("patch must be a dict")

    def _op(session: Session, owns_session: bool) -> int:
        row = session.execute(
            text("SELECT agent_states FROM workflow_runs WHERE id = :run_id FOR UPDATE"),
            {"run_id": run_id},
        ).scalar_one_or_none()
        if row is None:
            return 0

        try:
            current = _decompress_agent_states(row)
        except Exception:
            current = {}

        target = _ensure_path(current, path)
        _deep_merge(target, patch)

        now = datetime.now(timezone.utc)
        result = session.execute(
            text(
                """
                UPDATE workflow_runs
                SET agent_states = :agent_states,
                    agent_states_updated_at = :updated_at,
                    updated_at = :updated_at
                WHERE id = :run_id
                """
            ),
            {
                "run_id": run_id,
                "agent_states": _json_safe(_compress_agent_states(current)),
                "updated_at": now,
            },
        )
        if owns_session:
            session.commit()
        return result.rowcount or 0

    return _run_with_retry(label="merge_agent_states", db=db, op=_op)


__all__ = ["update_agent_states", "merge_agent_states", "get_agent_states", "mark_run_attention"]
__all__.append("decode_agent_states")


def decode_agent_states(value: Any) -> Dict[str, Any]:
    """Public helper to decode/decompress agent_states payloads."""
    return _decompress_agent_states(value)


def get_agent_states(
    run_id: str,
    *,
    db: Optional[Session] = None,
) -> Dict[str, Any]:
    """
    Read the current agent_states for a workflow run.

    Args:
        run_id: workflow_runs.id to read
        db: optional existing Session; if omitted, a session is created/closed

    Returns:
        The agent_states dict (empty dict if run_id not found or no states stored)
    """
    if not run_id:
        raise ValueError("run_id is required")

    owns_session = db is None
    session = db or SessionLocal()
    try:
        row = session.execute(
            text("SELECT agent_states FROM workflow_runs WHERE id = :run_id"),
            {"run_id": run_id},
        ).scalar_one_or_none()
        if row is None:
            return {}
        return _decompress_agent_states(row)
    finally:
        if owns_session:
            session.close()


def mark_run_attention(
    run_id: str,
    *,
    summary: Optional[str] = None,
    db: Optional[Session] = None,
) -> int:
    """
    Set workflow_runs.status to 'attention' for the given run_id.

    Args:
        run_id: workflow_runs.id
        summary: optional summary to store
        db: optional Session to reuse

    Returns:
        Number of rows updated (0 when run_id not found)
    """
    if not run_id:
        raise ValueError("run_id is required")

    owns_session = db is None
    session = db or SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        result = session.execute(
            text(
                """
                UPDATE workflow_runs
                SET status = 'attention',
                    summary = COALESCE(:summary, summary),
                    ended_at = COALESCE(ended_at, :now),
                    updated_at = :now
                WHERE id = :run_id
                """
            ),
            {"run_id": run_id, "summary": summary, "now": now},
        )
        if owns_session:
            session.commit()
        return result.rowcount or 0
    except Exception:
        if owns_session:
            session.rollback()
        raise
    finally:
        if owns_session:
            session.close()


def _parse_json_dict(value: Any) -> Dict[str, Any]:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
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


def get_environment(db: Session, *, run_id: str, user_id: Optional[str] = None) -> Dict[str, Any] | None:
    """
    Fetch workflow_runs.environment as a dict.

    Returns None if the run is not found (or not owned by user_id when provided).
    """
    sql = "SELECT environment FROM workflow_runs WHERE id = :run_id"
    params: Dict[str, Any] = {"run_id": run_id}
    if user_id is not None:
        sql += " AND user_id = :user_id"
        params["user_id"] = user_id
    row = execute_text(db, sql, params).scalar_one_or_none()
    if row is None:
        return None
    return _parse_json_dict(row)


def get_user_id(db: Session, *, run_id: str) -> str | None:
    return execute_text(
        db,
        "SELECT user_id FROM workflow_runs WHERE id = :run_id",
        {"run_id": run_id},
    ).scalar_one_or_none()


def merge_environment(db: Session, *, run_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    """
    Read/merge/write workflow_runs.environment using a shallow dict update.
    """
    env = get_environment(db, run_id=run_id) or {}
    env.update(patch or {})
    execute_text(
        db,
        """
        UPDATE workflow_runs
        SET environment = :env,
            updated_at = NOW()
        WHERE id = :run_id
        """,
        {"env": json.dumps(env), "run_id": run_id},
    )
    return env


def touch_run(db: Session, *, run_id: str) -> int:
    result = execute_text(
        db,
        """
        UPDATE workflow_runs
        SET last_heartbeat_at = NOW(), updated_at = NOW()
        WHERE id = :run_id
        """,
        {"run_id": run_id},
    )
    return result.rowcount or 0


def update_status(
    db: Session,
    *,
    run_id: str,
    status: str,
    summary: Optional[str] = None,
    updated_at: Optional[datetime] = None,
    terminal_statuses: Optional[set[str]] = None,
) -> int:
    terminal_set = terminal_statuses or {"success", "error", "attention", "cancelled"}
    terminal = status in terminal_set
    if updated_at is None:
        result = execute_text(
            db,
            """
            UPDATE workflow_runs
            SET status = :status,
                summary = COALESCE(:summary, summary),
                ended_at = CASE WHEN :terminal THEN NOW() ELSE ended_at END,
                updated_at = NOW()
            WHERE id = :run_id
            """,
            {"status": status, "summary": summary, "run_id": run_id, "terminal": terminal},
        )
        return result.rowcount or 0

    result = execute_text(
        db,
        """
        UPDATE workflow_runs
        SET status = :status,
            summary = COALESCE(:summary, summary),
            ended_at = CASE WHEN :terminal THEN :updated_at ELSE ended_at END,
            updated_at = :updated_at
        WHERE id = :run_id
        """,
        {
            "status": status,
            "summary": summary,
            "run_id": run_id,
            "terminal": terminal,
            "updated_at": updated_at,
        },
    )
    return result.rowcount or 0


def set_vm_id(db: Session, *, run_id: str, vm_id: str) -> int:
    result = execute_text(
        db,
        """
        UPDATE workflow_runs
        SET vm_id = :vm_id,
            updated_at = NOW()
        WHERE id = :run_id
        """,
        {"vm_id": vm_id, "run_id": run_id},
    )
    return result.rowcount or 0


def is_owned(db: Session, *, run_id: str, user_id: str) -> bool:
    row = (
        execute_text(
            db,
            """
            SELECT id FROM workflow_runs
            WHERE id = :run_id AND user_id = :user_id
            """,
            {"run_id": run_id, "user_id": user_id},
        ).fetchone()
        or None
    )
    return bool(row)


def insert_run(
    db: Session,
    *,
    run_id: str,
    workflow_id: str,
    user_id: str,
    folder_id: Optional[str],
    trigger_source: Optional[str],
    metadata: Dict[str, Any],
    environment: Dict[str, Any],
) -> None:
    execute_text(
        db,
        """
        INSERT INTO workflow_runs (
            id, workflow_id, user_id, folder_id, status, trigger_source,
            metadata, environment, created_at, updated_at
        )
        VALUES (
            :id, :workflow_id, :user_id, :folder_id, 'queued', :trigger_source,
            :metadata, :environment, NOW(), NOW()
        )
        """,
        {
            "id": run_id,
            "workflow_id": workflow_id,
            "user_id": user_id,
            "folder_id": folder_id,
            "trigger_source": trigger_source,
            "metadata": json.dumps(metadata or {}),
            "environment": json.dumps(environment or {}),
        },
    )


def notify_run_queued(db: Session, *, run_id: str, user_id: str) -> None:
    if not DB_URL.startswith("postgres"):
        return
    execute_text(
        db,
        """
        SELECT pg_notify(
            'workflow_run_queued',
            json_build_object('run_id', :run_id, 'user_id', :user_id)::text
        )
        """,
        {"run_id": run_id, "user_id": user_id},
    )


def list_runs_with_workflow(
    db: Session,
    *,
    user_id: str,
    status_filter: Optional[str],
    folder_id: Optional[str],
    limit: int,
) -> list[Dict[str, Any]]:
    limit = max(1, min(int(limit), 200))
    query = """
        SELECT wr.id,
               wr.workflow_id,
               wr.user_id,
               wr.folder_id,
               wr.status,
               wr.vm_id,
               wr.trigger_source,
               wr.metadata,
               wr.environment,
               wr.started_at,
               wr.ended_at,
               wr.created_at,
               wr.updated_at,
               wr.summary,
               w.name AS workflow_name,
               w.prompt AS workflow_prompt
        FROM workflow_runs wr
        LEFT JOIN workflows w ON w.id = wr.workflow_id
        WHERE wr.user_id = :user_id
    """
    params: Dict[str, Any] = {"user_id": user_id, "limit": limit}
    if status_filter:
        query += " AND status = :status"
        params["status"] = status_filter
    if folder_id:
        query += " AND folder_id = :folder_id"
        params["folder_id"] = folder_id

    query += " ORDER BY COALESCE(wr.started_at, wr.created_at) DESC LIMIT :limit"
    rows = execute_text(db, query, params).mappings().all()
    return [dict(r) for r in rows]


def get_run_vm_endpoint(db: Session, *, run_id: str, user_id: str) -> Dict[str, Any] | None:
    row = (
        execute_text(
            db,
            """
            SELECT wr.user_id, wr.vm_id, wr.environment, vi.endpoint
            FROM workflow_runs wr
            LEFT JOIN vm_instances vi ON vi.id = wr.vm_id
            WHERE wr.id = :run_id AND wr.user_id = :user_id
            """,
            {"run_id": run_id, "user_id": user_id},
        )
        .mappings()
        .first()
    )
    if not row:
        return None

    endpoint = row.get("endpoint")
    env_raw = row.get("environment")
    if env_raw and not endpoint:
        env_json = _parse_json_dict(env_raw)
        endpoint = env_json.get("endpoint")

    if isinstance(endpoint, str):
        try:
            endpoint = json.loads(endpoint)
        except Exception:
            endpoint = {}
    return endpoint if isinstance(endpoint, dict) else {}


def get_controller_base_url(db: Session, *, run_id: str, user_id: Optional[str] = None) -> str | None:
    env = get_environment(db, run_id=run_id, user_id=user_id)
    if env is None:
        return None
    endpoint = env.get("endpoint") if isinstance(env, dict) else None
    if isinstance(endpoint, str):
        try:
            endpoint = json.loads(endpoint)
        except Exception:
            endpoint = None
    if not isinstance(endpoint, dict):
        return None
    base_url = endpoint.get("controller_base_url") or endpoint.get("base_url")
    return str(base_url) if base_url else None


def get_resume_row(db: Session, *, run_id: str) -> Dict[str, Any] | None:
    row = (
        execute_text(
            db,
            """
            SELECT id, user_id, status, agent_states, environment
            FROM workflow_runs
            WHERE id = :run_id
            """,
            {"run_id": run_id},
        )
        .mappings()
        .first()
    )
    return dict(row) if row else None


__all__.extend(
    [
        "get_controller_base_url",
        "get_environment",
        "get_user_id",
        "get_resume_row",
        "get_run_vm_endpoint",
        "insert_run",
        "is_owned",
        "list_runs_with_workflow",
        "merge_environment",
        "notify_run_queued",
        "set_vm_id",
        "touch_run",
        "update_status",
    ]
)
