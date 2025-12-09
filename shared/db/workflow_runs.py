from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from .engine import SessionLocal

logger = logging.getLogger(__name__)


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


def _json_safe(val: Any) -> Any:
    """
    Ensure the payload is JSON-serializable. Falls back to string conversion for
    unsupported types to avoid crashing the checkpoint write.
    """
    try:
        return json.loads(json.dumps(val))
    except Exception:
        try:
            return json.loads(json.dumps(val, default=str))
        except Exception:
            logger.warning("agent_states payload not JSON-serializable; coercing to string")
            return str(val)


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

    owns_session = db is None
    session = db or SessionLocal()
    try:
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
                "agent_states": _json_safe(agent_states),
                "updated_at": now,
            },
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

    owns_session = db is None
    session = db or SessionLocal()
    try:
        row = session.execute(
            text("SELECT agent_states FROM workflow_runs WHERE id = :run_id FOR UPDATE"),
            {"run_id": run_id},
        ).scalar_one_or_none()
        if row is None:
            return 0

        try:
            current = row if isinstance(row, dict) else json.loads(row)
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
                "agent_states": _json_safe(current),
                "updated_at": now,
            },
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


__all__ = ["update_agent_states", "merge_agent_states", "get_agent_states", "mark_run_attention"]


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
        if isinstance(row, dict):
            return row
        try:
            return json.loads(row) if row else {}
        except Exception:
            return {}
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
