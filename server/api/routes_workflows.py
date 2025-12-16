from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
import httpx
import httpcore
from typing import Any, Dict, Optional
from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import text, select
from sqlalchemy.orm import Session
from botocore.exceptions import ClientError
from postgrest.exceptions import APIError
from pydantic import BaseModel, Field

from server.api.auth import CurrentUser, get_current_user
from shared.db.engine import SessionLocal, DB_URL
from shared.supabase_client import get_supabase_client
from uuid import UUID
from shared.storage import get_attachment_storage, AttachmentStorageError
from shared.db.models import WorkflowFile, WorkflowRunFile, WorkflowRunArtifact

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["workflows"])

RUN_CREDIT_COST = 10
TERMINAL_STATUSES = {"success", "error", "attention", "cancelled"}
VNC_DEFAULT_PASSWORD = os.getenv("VNC_DEFAULT_PASSWORD", "password")
DEFAULT_ATTACHMENT_CONTENT_TYPE = "application/octet-stream"


class WorkflowFileUploadRequest(BaseModel):
    filename: str = Field(..., max_length=255)
    content_type: Optional[str] = None
    size_bytes: Optional[int] = Field(default=None, ge=0)
    checksum: Optional[str] = Field(default=None, max_length=128)
    metadata: Optional[Dict[str, Any]] = None


class WorkflowFileFinalizeRequest(BaseModel):
    size_bytes: int = Field(..., ge=0)
    checksum: Optional[str] = Field(default=None, max_length=128)
    metadata: Optional[Dict[str, Any]] = None
    content_type: Optional[str] = None


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r"[\\/#?%*:|\"<>]", "_", os.path.basename(name or "file"))
    cleaned = cleaned.strip() or "file"
    return cleaned[:255]


def _serialize_workflow_file(data: Any) -> Dict[str, Any]:
    if isinstance(data, WorkflowFile):
        payload = {
            "id": data.id,
            "workflow_id": data.workflow_id,
            "user_id": data.user_id,
            "source_type": data.source_type,
            "storage_key": data.storage_key,
            "filename": data.filename,
            "content_type": data.content_type,
            "size_bytes": data.size_bytes,
            "checksum": data.checksum,
            "status": data.status,
            "created_at": data.created_at,
            "updated_at": data.updated_at,
            "metadata_json": data.metadata_json,
        }
    else:
        payload = dict(data)
    payload["metadata"] = payload.pop("metadata_json", None) or {}
    return payload


def _serialize_run_file(data: Any) -> Dict[str, Any]:
    if isinstance(data, WorkflowRunFile):
        payload = {
            "id": data.id,
            "run_id": data.run_id,
            "workflow_file_id": data.workflow_file_id,
            "user_id": data.user_id,
            "source_type": data.source_type,
            "storage_key": data.storage_key,
            "filename": data.filename,
            "content_type": data.content_type,
            "size_bytes": data.size_bytes,
            "checksum": data.checksum,
            "status": data.status,
            "vm_path": data.vm_path,
            "error": data.error,
            "created_at": data.created_at,
            "updated_at": data.updated_at,
            "metadata_json": data.metadata_json,
        }
    else:
        payload = dict(data)
    payload["metadata"] = payload.pop("metadata_json", None) or {}
    return payload


def _get_supabase_workflow(client, workflow_id: str) -> Dict[str, Any]:
    try:
        res = (
            client.table("workflows")
            .select("id,folder_id")
            .eq("id", workflow_id)
            .maybe_single()
            .execute()
        )
    except APIError as exc:
        if getattr(exc, "code", "") == "PGRST116":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workflow_not_found") from exc
        raise
    if not res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workflow_not_found")
    return res.data


def _load_ready_workflow_files(
    db: Session,
    workflow_id: str,
    user_id: str,
    file_ids: Optional[List[str]] = None,
) -> List[WorkflowFile]:
    stmt = (
        select(WorkflowFile)
        .where(
            WorkflowFile.workflow_id == workflow_id,
            WorkflowFile.user_id == user_id,
            WorkflowFile.status == "ready",
        )
        .order_by(WorkflowFile.created_at.asc())
    )
    if file_ids:
        stmt = stmt.where(WorkflowFile.id.in_(file_ids))
    rows = db.execute(stmt).scalars().all()
    if file_ids:
        found_ids = {wf.id for wf in rows}
        missing = [fid for fid in file_ids if fid not in found_ids]
        if missing:
            raise HTTPException(status_code=400, detail="invalid_or_unready_file_ids")
    return rows


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


def _execute_with_backoff(q, retries: int = 3, base_delay: float = 0.5, factor: float = 2.0, max_delay: float = 5.0):
    """
    Execute a Supabase/PostgREST query with exponential backoff on transient HTTP errors.
    """
    attempt = 0
    while attempt < retries:
        try:
            return q.execute()
        except (httpx.HTTPError, httpcore.RemoteProtocolError) as exc:
            attempt += 1
            if attempt >= retries:
                raise
            delay = min(max_delay, base_delay * (factor ** (attempt - 1)))
            logger.warning(
                "Supabase request failed (attempt %s/%s): %s; retrying in %.2fs",
                attempt,
                retries,
                exc,
                delay,
            )
            time.sleep(delay)


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
    environment_payload = payload.get("environment") or {}
    file_ids_raw = payload.get("file_ids")
    if file_ids_raw is not None and not isinstance(file_ids_raw, list):
        raise HTTPException(status_code=400, detail="file_ids_must_be_list")
    requested_file_ids = None
    if isinstance(file_ids_raw, list):
        requested_file_ids = [
            str(fid)
            for fid in file_ids_raw
            if fid is not None and str(fid).strip()
        ]

    # Validate workflow ownership via Supabase (RLS-protected)
    client = get_supabase_client(current_user.token)
    wf_res = _get_supabase_workflow(client, workflow_id)

    run_id = str(uuid.uuid4())

    db = SessionLocal()
    try:
        attachments: List[WorkflowFile] = []
        if requested_file_ids is None:
            attachments = _load_ready_workflow_files(db, workflow_id, current_user.sub, None)
        elif requested_file_ids:
            attachments = _load_ready_workflow_files(db, workflow_id, current_user.sub, requested_file_ids)

        run_file_records: List[WorkflowRunFile] = []
        for wf_file in attachments:
            run_file_records.append(
                WorkflowRunFile(
                    id=str(uuid.uuid4()),
                    run_id=run_id,
                    workflow_file_id=wf_file.id,
                    user_id=current_user.sub,
                    source_type=wf_file.source_type or "upload",
                    storage_key=wf_file.storage_key,
                    filename=wf_file.filename,
                    content_type=wf_file.content_type,
                    size_bytes=wf_file.size_bytes,
                    checksum=wf_file.checksum,
                    status="pending",
                    metadata_json=wf_file.metadata_json or {},
                )
            )

        if not isinstance(environment_payload, dict):
            environment_payload = {}
        if run_file_records:
            env_files = [
                {
                    "id": rf.id,
                    "workflow_file_id": rf.workflow_file_id,
                    "filename": rf.filename,
                    "size_bytes": rf.size_bytes,
                    "content_type": rf.content_type,
                    "status": rf.status,
                }
                for rf in run_file_records
            ]
            environment_payload = dict(environment_payload)
            environment_payload["files"] = env_files

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
                "folder_id": wf_res.get("folder_id"),
                "trigger_source": trigger_source,
                "metadata": json.dumps(metadata),
                "environment": json.dumps(environment_payload),
            },
        )

        if run_file_records:
            for record in run_file_records:
                db.add(record)

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


@router.get("/workflows/{workflow_id}/files")
def list_workflow_files(
    workflow_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    client = get_supabase_client(current_user.token)
    _get_supabase_workflow(client, workflow_id)

    db = SessionLocal()
    try:
        rows = (
            db.execute(
                select(WorkflowFile)
                .where(
                    WorkflowFile.workflow_id == workflow_id,
                    WorkflowFile.user_id == current_user.sub,
                )
                .order_by(WorkflowFile.created_at.asc())
            )
            .scalars()
            .all()
        )
        return {"files": [_serialize_workflow_file(row) for row in rows]}
    finally:
        db.close()


@router.post("/workflows/{workflow_id}/files/request-upload")
def request_workflow_file_upload(
    workflow_id: str,
    payload: WorkflowFileUploadRequest = Body(...),
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    client = get_supabase_client(current_user.token)
    _get_supabase_workflow(client, workflow_id)

    try:
        storage = get_attachment_storage()
    except AttachmentStorageError as exc:
        logger.error("Attachment storage misconfigured: %s", exc)
        raise HTTPException(status_code=500, detail="attachments_not_configured")

    safe_name = _safe_filename(payload.filename)
    file_id = str(uuid.uuid4())
    storage_key = f"{current_user.sub}/{workflow_id}/{file_id}/{safe_name}"
    content_type = payload.content_type or DEFAULT_ATTACHMENT_CONTENT_TYPE

    record = WorkflowFile(
        id=file_id,
        workflow_id=workflow_id,
        user_id=current_user.sub,
        source_type="upload",
        storage_key=storage_key,
        filename=safe_name,
        content_type=content_type,
        size_bytes=payload.size_bytes,
        checksum=payload.checksum,
        status="pending",
        metadata_json=payload.metadata or {},
    )

    db = SessionLocal()
    try:
        db.add(record)
        db.commit()
        db.refresh(record)
    except Exception as exc:  # pragma: no cover - DB error guard
        db.rollback()
        logger.exception("Failed to create workflow file row: %s", exc)
        raise HTTPException(status_code=500, detail="failed_to_create_workflow_file")
    finally:
        db.close()

    upload_url = storage.generate_presigned_put(storage_key, content_type=content_type)
    return {
        "file": _serialize_workflow_file(record),
        "upload": {
            "url": upload_url,
            "method": "PUT",
            "headers": {"Content-Type": content_type},
        },
    }


@router.post("/workflows/{workflow_id}/files/{file_id}/finalize")
def finalize_workflow_file(
    workflow_id: str,
    file_id: str,
    payload: WorkflowFileFinalizeRequest = Body(...),
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    client = get_supabase_client(current_user.token)
    _get_supabase_workflow(client, workflow_id)

    try:
        storage = get_attachment_storage()
    except AttachmentStorageError as exc:
        logger.error("Attachment storage misconfigured: %s", exc)
        raise HTTPException(status_code=500, detail="attachments_not_configured")

    db = SessionLocal()
    try:
        record = (
            db.execute(
                select(WorkflowFile).where(
                    WorkflowFile.id == file_id,
                    WorkflowFile.workflow_id == workflow_id,
                    WorkflowFile.user_id == current_user.sub,
                )
            )
            .scalars()
            .first()
        )
        if not record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file_not_found")

        try:
            storage.head_object(record.storage_key)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in {"404", "NoSuchKey"}:
                raise HTTPException(status_code=400, detail="file_not_uploaded") from exc
            raise

        record.size_bytes = payload.size_bytes
        if payload.checksum:
            record.checksum = payload.checksum
        if payload.metadata is not None:
            record.metadata_json = payload.metadata
        if payload.content_type:
            record.content_type = payload.content_type
        record.status = "ready"
        record.updated_at = datetime.now(timezone.utc)

        db.add(record)
        db.commit()
        db.refresh(record)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover
        db.rollback()
        logger.exception("Failed to finalize workflow file: %s", exc)
        raise HTTPException(status_code=500, detail="failed_to_finalize_file")
    finally:
        db.close()

    return {"file": _serialize_workflow_file(record)}


@router.delete("/workflows/{workflow_id}/files/{file_id}")
def delete_workflow_file(
    workflow_id: str,
    file_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    client = get_supabase_client(current_user.token)
    _get_supabase_workflow(client, workflow_id)

    db = SessionLocal()
    try:
        record = (
            db.execute(
                select(WorkflowFile).where(
                    WorkflowFile.id == file_id,
                    WorkflowFile.workflow_id == workflow_id,
                    WorkflowFile.user_id == current_user.sub,
                )
            )
            .scalars()
            .first()
        )
        if not record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file_not_found")

        try:
            storage = get_attachment_storage()
            storage.delete_object(record.storage_key)
        except AttachmentStorageError as exc:
            logger.error("Attachment storage misconfigured during delete: %s", exc)
        except Exception as exc:  # pragma: no cover - log but do not block deletion
            logger.warning("Failed to delete attachment object %s: %s", record.storage_key, exc)

        db.delete(record)
        db.commit()
    finally:
        db.close()

    return {"deleted": True}


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
    try:
        res = _execute_with_backoff(q)
    except (httpx.HTTPError, httpcore.RemoteProtocolError) as exc:
        logger.error("Failed to list workflows after retries: %s", exc)
        raise HTTPException(status_code=503, detail="upstream_unavailable") from exc
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
        q = (
            client.table("workflows")
            .select(
                "id,name,prompt,description,status,folder_id,definition_json,metadata,updated_at,created_at"
            )
            .eq("id", workflow_id)
            .single()
        )
        res = _execute_with_backoff(q)
    except APIError as exc:
        if getattr(exc, "code", "") == "PGRST116":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workflow_not_found") from exc
        raise
    except (httpx.HTTPError, httpcore.RemoteProtocolError) as exc:
        logger.error("Failed to fetch workflow after retries: %s", exc)
        raise HTTPException(status_code=503, detail="upstream_unavailable") from exc

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


@router.get("/runs/{run_id}/artifacts")
def list_run_artifacts(
    run_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        run_row = db.execute(
            text(
                """
                SELECT id FROM workflow_runs
                WHERE id = :run_id AND user_id = :user_id
                """
            ),
            {"run_id": run_id, "user_id": current_user.sub},
        ).fetchone()
        if not run_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run_not_found")

        rows = (
            db.execute(
                select(WorkflowRunArtifact)
                .where(WorkflowRunArtifact.run_id == run_id)
                .order_by(WorkflowRunArtifact.created_at.asc())
            )
            .scalars()
            .all()
        )
    finally:
        db.close()

    try:
        storage = get_attachment_storage()
    except AttachmentStorageError as exc:
        logger.error("Attachment storage misconfigured: %s", exc)
        raise HTTPException(status_code=500, detail="attachments_not_configured")

    artifacts = []
    for row in rows:
        artifacts.append(
            {
                "id": row.id,
                "filename": row.filename,
                "size_bytes": row.size_bytes,
                "content_type": row.content_type,
                "storage_key": row.storage_key,
                "source_path": row.source_path,
                "download_url": storage.generate_presigned_get(row.storage_key),
            }
        )

    return {"artifacts": artifacts}


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
