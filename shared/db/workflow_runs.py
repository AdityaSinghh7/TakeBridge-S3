from __future__ import annotations

import base64
import gzip
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
                "agent_states": _json_safe(compressed),
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
    except Exception:
        if owns_session:
            session.rollback()
        raise
    finally:
        if owns_session:
            session.close()


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
