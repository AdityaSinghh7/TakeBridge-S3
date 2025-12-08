from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import text
from postgrest.exceptions import APIError

from server.api.auth import CurrentUser, get_current_user
from shared.db.engine import SessionLocal, DB_URL
from shared.supabase_client import get_supabase_client
from uuid import UUID

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["workflows"])

RUN_CREDIT_COST = 10
TERMINAL_STATUSES = {"success", "error", "attention", "cancelled"}
VNC_DEFAULT_PASSWORD = os.getenv("VNC_DEFAULT_PASSWORD", "password")


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
    try:
        UUID(str(workflow_id))
    except Exception:
        raise HTTPException(status_code=400, detail="invalid_workflow_id")

    user_id = current_user.sub
    trigger_source = payload.get("trigger_source") or "manual"
    metadata = payload.get("metadata") or {}
    environment = payload.get("environment") or {}

    # Validate workflow ownership via Supabase (RLS-protected)
    client = get_supabase_client(current_user.token)
    try:
        wf_res = (
            client.table("workflows")
            .select("id,folder_id")
            .eq("id", workflow_id)
            .maybe_single()
            .execute()
        )
    except APIError as exc:  # pragma: no cover - validation guard
        # Supabase returns PGRST116 when single() finds 0 rows; treat as 404
        if getattr(exc, "code", "") == "PGRST116":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workflow_not_found") from exc
        raise
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
                    id, workflow_id, user_id, folder_id, status, trigger_source,
                    metadata, environment, created_at, updated_at
                )
                VALUES (
                    :id, :workflow_id, :user_id, :folder_id, 'queued', :trigger_source,
                    :metadata, :environment, NOW(), NOW()
                )
                """
            ),
            {
                "id": run_id,
                "workflow_id": workflow_id,
                "user_id": user_id,
                "folder_id": (wf_res.data or {}).get("folder_id"),
                "trigger_source": trigger_source,
                "metadata": json.dumps(metadata),
                "environment": json.dumps(environment),
            },
        )

        # Notify listeners (Postgres only) that a run was enqueued.
        if DB_URL.startswith("postgres"):
            db.execute(
                text(
                    """
                    SELECT pg_notify(
                        'workflow_run_queued',
                        json_build_object('run_id', :run_id, 'user_id', :user_id)::text
                    )
                    """
                ),
                {"run_id": run_id, "user_id": user_id},
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


@router.get("/workflows")
def list_workflows(
    folder_id: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    List workflows for the current user (filtered by folder when provided).
    """
    client = get_supabase_client(current_user.token)
    q = client.table("workflows").select(
        "id,name,prompt,description,status,folder_id,updated_at,created_at"
    ).order("updated_at", desc=True)
    if folder_id:
        q = q.eq("folder_id", folder_id)
    res = q.execute()
    workflows = res.data or []
    for wf in workflows:
        if isinstance(wf, dict):
            wf["plan"] = wf.get("definition_json")
    return {"workflows": workflows}


@router.get("/workflows/{workflow_id}")
def get_workflow(
    workflow_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Fetch a single workflow by id.
    """
    client = get_supabase_client(current_user.token)
    try:
        res = (
            client.table("workflows")
            .select(
                "id,name,prompt,description,status,folder_id,definition_json,metadata,updated_at,created_at"
            )
            .eq("id", workflow_id)
            .single()
            .execute()
        )
    except APIError as exc:
        if getattr(exc, "code", "") == "PGRST116":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workflow_not_found") from exc
        raise

    if not res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workflow_not_found")
    workflow = res.data
    workflow["plan"] = workflow.get("definition_json")
    return {"workflow": workflow}




@router.get("/runs/{run_id}/vm")
def get_run_vm(
    run_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Return VNC connection info for a run (host, port, password, secure?, path?).
    """
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                """
                SELECT wr.user_id, wr.vm_id, wr.environment, vi.endpoint
                FROM workflow_runs wr
                LEFT JOIN vm_instances vi ON vi.id = wr.vm_id
                WHERE wr.id = :run_id
                """
            ),
            {"run_id": run_id},
        )
        res = row.mappings().all()
        match = next((dict(r) for r in res if str(r.get("user_id")) == current_user.sub), None)
        if not match:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run_not_found")

        endpoint = match.get("endpoint")
        env = match.get("environment")
        if env and not endpoint:
            try:
                env_json = json.loads(env) if isinstance(env, str) else env
                endpoint = env_json.get("endpoint")
            except Exception:
                endpoint = None

        if isinstance(endpoint, str):
            try:
                endpoint = json.loads(endpoint)
            except Exception:
                endpoint = {}

        endpoint = endpoint or {}

        vnc_url = endpoint.get("vnc_url")
        host = endpoint.get("host")
        port = endpoint.get("port")
        password = endpoint.get("password") or VNC_DEFAULT_PASSWORD
        path = endpoint.get("path") or ""
        secure = None

        if vnc_url:
            parsed = urlparse(vnc_url)
            host = parsed.hostname or host
            port = parsed.port or port
            path = parsed.path or path
            secure = parsed.scheme in {"wss", "https"}
        elif endpoint.get("controller_base_url"):
            parsed = urlparse(endpoint.get("controller_base_url"))
            host = host or parsed.hostname
            port = port or parsed.port
            secure = parsed.scheme in {"wss", "https"}

        vm_info = {
            "host": host,
            "port": port,
            "password": password,
            "secure": secure,
            "path": path,
            "vnc_url": vnc_url,
        }

        return {"vm": vm_info}
    finally:
        db.close()


@router.patch("/workflows/{workflow_id}")
def update_workflow(
    workflow_id: str,
    payload: Dict[str, Any] = Body(default_factory=dict),
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Update workflow metadata.
    """
    client = get_supabase_client(current_user.token)
    update_fields: Dict[str, Any] = {}
    if "folder_id" in payload:
        update_fields["folder_id"] = payload.get("folder_id")
    if "name" in payload:
        update_fields["name"] = payload.get("name")
    if "prompt" in payload:
        update_fields["prompt"] = payload.get("prompt")
    if "description" in payload:
        update_fields["description"] = payload.get("description")
    if "plan" in payload:
        update_fields["definition_json"] = payload.get("plan")
    elif "definition_json" in payload:
        update_fields["definition_json"] = payload.get("definition_json")
    if "status" in payload:
        update_fields["status"] = payload.get("status")
    if not update_fields:
        raise HTTPException(status_code=400, detail="no_updatable_fields")

    try:
        res = client.table("workflows").update(update_fields).eq("id", workflow_id).execute()
        updated = (res.data or [{}])[0] if isinstance(res.data, list) else res.data
    except APIError as exc:
        if getattr(exc, "code", "") == "PGRST116":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workflow_not_found") from exc
        raise

    if updated is None:
        raise HTTPException(status_code=500, detail="failed_to_update_workflow")
    updated["plan"] = updated.get("definition_json")
    return {"workflow": updated}


@router.get("/runs")
def list_runs(
    status_filter: Optional[str] = None,
    folder_id: Optional[str] = None,
    limit: int = 20,
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Fetch recent runs with optional status and folder filters.
    """
    limit = max(1, min(limit, 200))
    db = SessionLocal()
    try:
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
        params: Dict[str, Any] = {"user_id": current_user.sub}
        if status_filter:
            query += " AND status = :status"
            params["status"] = status_filter
        if folder_id:
            query += " AND folder_id = :folder_id"
            params["folder_id"] = folder_id

        query += " ORDER BY COALESCE(wr.started_at, wr.created_at) DESC LIMIT :limit"
        params["limit"] = limit

        rows = db.execute(text(query), params).mappings().all()
        return {"runs": [dict(r) for r in rows]}
    finally:
        db.close()


@router.get("/folders")
def list_folders(current_user: CurrentUser = Depends(get_current_user)) -> Dict[str, Any]:
    """
    List folders for the current user.
    """
    client = get_supabase_client(current_user.token)
    res = client.table("folders").select("*").order("position", desc=False).execute()
    return {"folders": res.data or []}


@router.post("/folders")
def create_folder(
    payload: Dict[str, Any] = Body(...),
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    name = (payload.get("name") or "").strip()
    position: Optional[int] = payload.get("position")
    if not name:
        raise HTTPException(status_code=400, detail="name_required")

    client = get_supabase_client(current_user.token)
    folder_id = str(uuid.uuid4())
    inserted = (
        client.table("folders")
        .insert(
            {
                "id": folder_id,
                "user_id": current_user.sub,
                "name": name,
                "position": position,
            }
        )
        .select("*")
        .single()
        .execute()
    )
    return {"folder": inserted.data}


@router.patch("/folders/{folder_id}")
def update_folder(
    folder_id: str,
    payload: Dict[str, Any] = Body(default_factory=dict),
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    update_fields: Dict[str, Any] = {}
    if "name" in payload:
        update_fields["name"] = payload.get("name")
    if "position" in payload:
        update_fields["position"] = payload.get("position")
    if not update_fields:
        raise HTTPException(status_code=400, detail="no_updatable_fields")

    client = get_supabase_client(current_user.token)
    try:
        res = (
            client.table("folders")
            .update(update_fields)
            .eq("id", folder_id)
            .select("*")
            .single()
            .execute()
        )
    except APIError as exc:
        if getattr(exc, "code", "") == "PGRST116":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="folder_not_found") from exc
        raise
    return {"folder": res.data}


@router.delete("/folders/{folder_id}")
def delete_folder(
    folder_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    client = get_supabase_client(current_user.token)
    client.table("folders").delete().eq("id", folder_id).execute()
    return {"deleted": True}


@router.post("/workflows")
def create_workflow(
    payload: Dict[str, Any] = Body(...),
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Create and persist a workflow from a composed plan.
    """
    client = get_supabase_client(current_user.token)
    workflow_id = str(uuid.uuid4())

    name = payload.get("name")
    prompt = payload.get("prompt")
    description = payload.get("description")
    plan_payload = payload.get("plan")
    definition_json = plan_payload if plan_payload is not None else payload.get("definition_json")
    folder_id = payload.get("folder_id")
    status_val = payload.get("status") or "active"
    metadata = payload.get("metadata") or {}

    if not name and prompt:
        name = prompt[:80]
    if not name:
        raise HTTPException(status_code=400, detail="name_required")

    insert_payload = {
        "id": workflow_id,
        "user_id": current_user.sub,
        "folder_id": folder_id,
        "name": name,
        "prompt": prompt,
        "description": description,
        "definition_json": definition_json,
        "status": status_val,
        "metadata": metadata,
    }

    try:
        res = client.table("workflows").insert(insert_payload).execute()
        created = (res.data or [{}])[0] if isinstance(res.data, list) else res.data
    except APIError as exc:
        logger.exception("Failed to create workflow: %s", exc)
        raise HTTPException(status_code=500, detail="failed_to_create_workflow")

    if created is None:
        raise HTTPException(status_code=500, detail="failed_to_create_workflow")
    created["plan"] = created.get("definition_json")
    return {"workflow": created}


__all__ = ["router"]
