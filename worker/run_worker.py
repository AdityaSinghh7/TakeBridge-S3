"""
Lightweight worker that dequeues queued workflow runs and triggers execution
via the server's internal execution endpoint. The server owns orchestration,
event persistence, and status updates; the worker only claims and triggers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, Optional

import requests
from sqlalchemy import text

from shared.db.engine import SessionLocal, DB_URL
from shared.supabase_client import get_service_supabase_client

logger = logging.getLogger(__name__)

INTERNAL_API_TOKEN = os.getenv("INTERNAL_API_TOKEN") or ""
# Default to https to match Procfile (self-signed local cert); override via env if needed.
EXECUTOR_BASE_URL = os.getenv("EXECUTOR_BASE_URL", "https://127.0.0.1:8000")
INTERNAL_VERIFY_SSL = os.getenv("INTERNAL_VERIFY_SSL", "false").lower() in {"1", "true", "yes"}
NOTIFY_CHANNEL = "workflow_run_queued"
IS_POSTGRES = DB_URL.startswith("postgres")


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
                    SELECT id, workflow_id, user_id
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
                RETURNING wr.id, wr.workflow_id, wr.user_id
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
    except Exception:
        db.rollback()
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
    headers = {"X-Internal-Token": INTERNAL_API_TOKEN} if INTERNAL_API_TOKEN else {}
    verify_arg = os.getenv("REQUESTS_CA_BUNDLE") or os.getenv("CURL_CA_BUNDLE") or os.getenv("EXECUTOR_CA_BUNDLE")
    payload = {
        "user_id": user_id,
        "workflow_id": workflow_id,
        "task": task,
        "composed_plan": composed_plan,
    }
    payload = _json_safe(payload)
    # Ensure full JSON-serializability (e.g., UUIDs) before sending
    payload = json.loads(json.dumps(payload, default=str))
    with requests.post(
        url,
        json=payload,
        headers=headers,
        stream=True,
        timeout=None,
        verify=INTERNAL_VERIFY_SSL,
    ) as resp:
        if resp.status_code >= 300:
            text_body = ""
            try:
                text_body = resp.text
            except Exception:
                pass
            raise RuntimeError(f"execution call failed: status={resp.status_code} body={text_body[:200]}")
        # Consume stream to completion to let server run fully
        for _ in resp.iter_lines():
            pass


async def run_once(claimed_by: str = "worker") -> bool:
    claim = claim_next_run(claimed_by)
    if not claim:
        return False

    run_id = claim["id"]
    workflow_id = claim["workflow_id"]
    user_id = claim["user_id"]

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
    while True:
        processed = await run_once()
        if not processed:
            await asyncio.sleep(2)


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    asyncio.run(worker_loop())
