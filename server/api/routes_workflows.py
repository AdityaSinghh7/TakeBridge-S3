from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from server.api.auth import CurrentUser, get_current_user
from shared.db.engine import SessionLocal
from shared.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["workflows"])

RUN_CREDIT_COST = 10
TERMINAL_STATUSES = {"success", "error", "attention", "cancelled"}


def _format_sse(event: str, data: Optional[Any] = None) -> bytes:
    parts = [f"event: {event}"]
    if data is not None:
        try:
            payload = json.dumps(data, separators=(",", ":"))
        except Exception:
            payload = json.dumps({"message": str(data)})
        parts.append(f"data: {payload}")
    parts.append("")
    return "\n".join(parts).encode("utf-8")


@router.post("/workflows/{workflow_id}/run")
def enqueue_workflow_run(
    workflow_id: str,
    payload: Dict[str, Any] = Body(default_factory=dict),
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Enqueue a workflow run and debit credits in one transaction.
    """
    user_id = current_user.sub
    trigger_source = payload.get("trigger_source") or "manual"
    metadata = payload.get("metadata") or {}
    environment = payload.get("environment") or {}

    # Validate workflow ownership via Supabase (RLS-protected)
    client = get_supabase_client(current_user.token)
    wf_res = client.table("workflows").select("id").eq("id", workflow_id).single().execute()
    if not wf_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workflow_not_found")

    run_id = str(uuid.uuid4())

    db = SessionLocal()
    try:
        # Debit credits atomically
        credit_row = db.execute(
            text(
                """
                UPDATE profiles
                SET credits = credits - :cost
                WHERE id = :user_id AND credits >= :cost
                RETURNING credits
                """
            ),
            {"cost": RUN_CREDIT_COST, "user_id": user_id},
        ).fetchone()

        if not credit_row:
            db.rollback()
            raise HTTPException(status_code=402, detail="insufficient_credits")

        # Insert run row
        db.execute(
            text(
                """
                INSERT INTO workflow_runs (
                    id, workflow_id, user_id, status, trigger_source,
                    metadata, environment, created_at, updated_at
                )
                VALUES (
                    :id, :workflow_id, :user_id, 'queued', :trigger_source,
                    :metadata, :environment, NOW(), NOW()
                )
                """
            ),
            {
                "id": run_id,
                "workflow_id": workflow_id,
                "user_id": user_id,
                "trigger_source": trigger_source,
                "metadata": json.dumps(metadata),
                "environment": json.dumps(environment),
            },
        )

        db.commit()

    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to enqueue workflow run: %s", exc)
        raise HTTPException(status_code=500, detail="failed_to_enqueue_run")
    finally:
        db.close()

    return {"run_id": run_id, "status": "queued", "credits_remaining": credit_row[0]}


@router.get("/runs/{run_id}/events")
async def stream_run_events(
    run_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    """
    SSE stream of run_events mirrored in Supabase.
    Polls every ~1s; emits events in order.
    """
    client = get_supabase_client(current_user.token)
    last_ts: Optional[str] = None

    async def _event_stream():
        nonlocal last_ts
        while True:
            # Fetch new events
            q = client.table("run_events").select("*").eq("run_id", run_id).order("ts", desc=False).limit(200)
            if last_ts:
                q = q.gt("ts", last_ts)
            res = q.execute()
            events = res.data or []
            for evt in events:
                last_ts = evt.get("ts") or last_ts
                yield _format_sse("run_event", evt)

            # Check run status to decide whether to continue streaming
            status_res = client.table("workflow_runs").select("status").eq("id", run_id).single().execute()
            status_val = (status_res.data or {}).get("status")
            if status_val in TERMINAL_STATUSES:
                yield _format_sse("run_completed", {"status": status_val})
                break

            await asyncio.sleep(1.0)

    return StreamingResponse(_event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


__all__ = ["router"]
