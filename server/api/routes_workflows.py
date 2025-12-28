from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import os
import posixpath
import re
import time
import uuid
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from uuid import UUID

import httpcore
import httpx
from botocore.exceptions import ClientError
from fastapi import APIRouter, Body, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from postgrest.exceptions import APIError
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from server.api.auth import CurrentUser, get_current_user
from server.api.controller_client import VMControllerClient
from server.api.drive_utils import build_drive_backup_key, build_drive_key, normalize_drive_path
from server.api.run_drive import DOWNLOAD_CHUNK_BYTES, DRIVE_VM_BASE_PATH
from shared.db import (
    profiles,
    workflow_files,
    workflow_run_drive_changes,
    workflow_run_files,
    workflow_runs,
)
from shared.db.engine import DB_URL, SessionLocal
from shared.db.models import WorkflowFile
from shared.storage import AttachmentStorageError, get_attachment_storage
from shared.supabase_client import get_supabase_client

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
    rows, missing = workflow_files.load_ready_for_workflow(
        db,
        workflow_id=workflow_id,
        user_id=user_id,
        file_ids=file_ids,
    )
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


def _get_run_controller_base_url(db: Session, run_id: str, user_id: str) -> str:
    env = workflow_runs.get_environment(db, run_id=run_id, user_id=user_id)
    if env is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run_not_found")
    endpoint = env.get("endpoint") if isinstance(env, dict) else None
    if isinstance(endpoint, str):
        try:
            endpoint = json.loads(endpoint)
        except Exception:
            endpoint = {}
    controller_base_url = None
    if isinstance(endpoint, dict):
        controller_base_url = endpoint.get("controller_base_url") or endpoint.get("base_url")
    if not controller_base_url:
        raise HTTPException(status_code=400, detail="controller_base_url_missing")
    return str(controller_base_url)


@router.post("/workflows/{workflow_id}/run")
def enqueue_workflow_run(
    workflow_id: str,
    payload: Dict[str, Any] = Body(default_factory=dict),
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Enqueue a workflow run and debit credits in one transaction.
    """
    request_start = time.monotonic()
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
    drive_paths_raw = payload.get("drive_paths")
    if drive_paths_raw is not None and not isinstance(drive_paths_raw, list):
        raise HTTPException(status_code=400, detail="drive_paths_must_be_list")
    drive_paths: List[str] = []
    if isinstance(drive_paths_raw, list):
        seen_paths = set()
        for raw in drive_paths_raw:
            if raw is None:
                continue
            try:
                normalized = normalize_drive_path(str(raw))
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            if normalized in seen_paths:
                continue
            seen_paths.add(normalized)
            drive_paths.append(normalized)

    metadata_keys = sorted(metadata.keys()) if isinstance(metadata, dict) else [f"<{type(metadata).__name__}>"]
    environment_keys = (
        sorted(environment_payload.keys()) if isinstance(environment_payload, dict) else [f"<{type(environment_payload).__name__}>"]
    )
    file_ids_summary: Any
    if requested_file_ids is None:
        file_ids_summary = "default"
    else:
        file_ids_summary = {"count": len(requested_file_ids), "preview": requested_file_ids[:3]}
    if drive_paths_raw is None:
        drive_paths_summary: Any = "none"
    else:
        drive_paths_summary = {"count": len(drive_paths), "preview": drive_paths[:3]}
    logger.info(
        "Enqueue requested workflow_id=%s user_id=%s trigger_source=%s file_ids=%s drive_paths=%s metadata_keys=%s environment_keys=%s",
        workflow_id,
        user_id,
        trigger_source,
        file_ids_summary,
        drive_paths_summary,
        metadata_keys,
        environment_keys,
    )

    # Validate workflow ownership via Supabase (RLS-protected)
    client = get_supabase_client(current_user.token)
    wf_res = _get_supabase_workflow(client, workflow_id)

    run_id = str(uuid.uuid4())
    logger.info("Enqueue allocated run_id=%s workflow_id=%s user_id=%s", run_id, workflow_id, user_id)

    db = SessionLocal()
    try:
        attachments: List[WorkflowFile] = []
        if requested_file_ids is None:
            attachments = _load_ready_workflow_files(db, workflow_id, current_user.sub, None)
        elif requested_file_ids:
            attachments = _load_ready_workflow_files(db, workflow_id, current_user.sub, requested_file_ids)

        run_file_records = workflow_run_files.build_pending_for_workflow_files(
            run_id=run_id,
            user_id=current_user.sub,
            workflow_files=attachments,
        )
        r2_key_by_path = {drive_path: build_drive_key(current_user.sub, drive_path) for drive_path in drive_paths}
        run_file_records.extend(
            workflow_run_files.build_pending_for_drive_paths(
                run_id=run_id,
                user_id=current_user.sub,
                drive_paths=drive_paths,
                r2_key_by_path=r2_key_by_path,
            )
        )

        logger.info(
            "Enqueue attachments resolved run_id=%s workflow_id=%s files=%s",
            run_id,
            workflow_id,
            len(run_file_records),
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
                if rf.source_type != "drive"
            ]
            environment_payload = dict(environment_payload)
            if env_files:
                environment_payload["files"] = env_files
        if drive_paths:
            environment_payload = dict(environment_payload)
            environment_payload["drive_paths"] = drive_paths
        logger.info(
            "Enqueue payload finalized run_id=%s metadata_keys=%s environment_keys=%s",
            run_id,
            metadata_keys,
            sorted(environment_payload.keys()) if isinstance(environment_payload, dict) else [f"<{type(environment_payload).__name__}>"],
        )

        # Debit credits atomically
        credits_remaining = profiles.debit_credits(db, user_id=user_id, cost=RUN_CREDIT_COST)
        if credits_remaining is None:
            db.rollback()
            logger.warning(
                "Enqueue rejected insufficient credits workflow_id=%s user_id=%s cost=%s",
                workflow_id,
                user_id,
                RUN_CREDIT_COST,
            )
            raise HTTPException(status_code=402, detail="insufficient_credits")

        logger.info(
            "Enqueue debited credits run_id=%s user_id=%s credits_remaining=%s",
            run_id,
            user_id,
            credits_remaining,
        )

        # Insert run row
        workflow_runs.insert_run(
            db,
            run_id=run_id,
            workflow_id=workflow_id,
            user_id=user_id,
            folder_id=wf_res.get("folder_id"),
            trigger_source=trigger_source,
            metadata=metadata if isinstance(metadata, dict) else {},
            environment=environment_payload if isinstance(environment_payload, dict) else {},
        )
        logger.info("Enqueue inserted workflow_runs row run_id=%s workflow_id=%s user_id=%s", run_id, workflow_id, user_id)

        if run_file_records:
            workflow_run_files.add_many(db, run_file_records)

        # Notify listeners (Postgres only) that a run was enqueued.
        if DB_URL.startswith("postgres"):
            logger.info(
                "Enqueue notifying workers channel=%s run_id=%s user_id=%s",
                "workflow_run_queued",
                run_id,
                user_id,
            )
            workflow_runs.notify_run_queued(db, run_id=run_id, user_id=user_id)
        else:
            logger.info(
                "Enqueue skipping worker notify (DB is not Postgres) run_id=%s db=%s",
                run_id,
                urlparse(DB_URL).scheme or "unknown",
            )

        db.commit()
        elapsed_ms = int((time.monotonic() - request_start) * 1000)
        logger.info(
            "Enqueue committed run_id=%s workflow_id=%s user_id=%s status=queued credits_remaining=%s duration_ms=%s",
            run_id,
            workflow_id,
            user_id,
            credits_remaining,
            elapsed_ms,
        )

    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to enqueue workflow run: %s", exc)
        raise HTTPException(status_code=500, detail="failed_to_enqueue_run")
    finally:
        db.close()

    return {"run_id": run_id, "status": "queued", "credits_remaining": credits_remaining}


@router.get("/workflows/{workflow_id}/files")
def list_workflow_files(
    workflow_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    client = get_supabase_client(current_user.token)
    _get_supabase_workflow(client, workflow_id)

    db = SessionLocal()
    try:
        rows = workflow_files.list_for_workflow(db, workflow_id=workflow_id, user_id=current_user.sub)
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

    db = SessionLocal()
    try:
        record = workflow_files.create_pending(
            db,
            file_id=file_id,
            workflow_id=workflow_id,
            user_id=current_user.sub,
            storage_key=storage_key,
            filename=safe_name,
            content_type=content_type,
            size_bytes=payload.size_bytes,
            checksum=payload.checksum,
            metadata=payload.metadata,
        )
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
        record = workflow_files.get_for_user(
            db,
            workflow_id=workflow_id,
            user_id=current_user.sub,
            file_id=file_id,
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

        workflow_files.finalize(
            db,
            record,
            size_bytes=payload.size_bytes,
            checksum=payload.checksum,
            metadata=payload.metadata,
            content_type=payload.content_type,
        )
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
        record = workflow_files.get_for_user(
            db,
            workflow_id=workflow_id,
            user_id=current_user.sub,
            file_id=file_id,
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

        workflow_files.delete(db, record)
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
        endpoint = workflow_runs.get_run_vm_endpoint(db, run_id=run_id, user_id=current_user.sub)
        if endpoint is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run_not_found")

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


@router.post("/runs/{run_id}/commit-drive-changes")
def commit_drive_changes(
    run_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    db = SessionLocal()
    try:
        if not workflow_runs.is_owned(db, run_id=run_id, user_id=current_user.sub):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run_not_found")

        rows = workflow_run_drive_changes.list_for_run_user(
            db,
            run_id=run_id,
            user_id=current_user.sub,
        )
    finally:
        db.close()

    rows = [row for row in rows if getattr(row, "status", None) != "committed"]
    if not rows:
        return []

    try:
        storage = get_attachment_storage()
    except AttachmentStorageError as exc:
        logger.error("Attachment storage misconfigured: %s", exc)
        raise HTTPException(status_code=500, detail="attachments_not_configured")

    results: List[Dict[str, Any]] = []
    for row in rows:
        content_type = row.content_type or mimetypes.guess_type(row.path or "")[0] or DEFAULT_ATTACHMENT_CONTENT_TYPE
        presigned_put_url = storage.generate_presigned_put(row.r2_key, content_type=content_type)
        change_type = "new" if not row.baseline_hash else "modified"
        backup_presigned_get_url = None
        if change_type == "modified":
            backup_presigned_get_url = storage.generate_presigned_get(row.r2_key)
        results.append(
            {
                "path": row.path,
                "r2_key": row.r2_key,
                "presigned_put_url": presigned_put_url,
                "content_type": content_type,
                "size": row.size_bytes,
                "source_baseline_hash": row.baseline_hash,
                "new_hash": row.new_hash,
                "change_type": change_type,
                "backup_presigned_get_url": backup_presigned_get_url,
            }
        )
    return results


@router.post("/runs/{run_id}/commit-drive-file")
def commit_drive_file(
    run_id: str,
    payload: Dict[str, Any] = Body(default_factory=dict),
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    path_raw = payload.get("path") or payload.get("drive_path")
    if not path_raw:
        raise HTTPException(status_code=400, detail="drive_path_required")
    try:
        drive_path = normalize_drive_path(str(path_raw))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    db = SessionLocal()
    try:
        if not workflow_runs.is_owned(db, run_id=run_id, user_id=current_user.sub):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run_not_found")

        rows = workflow_run_drive_changes.list_for_run_user(
            db,
            run_id=run_id,
            user_id=current_user.sub,
        )
        change_row = next((row for row in rows if row.path == drive_path), None)
        if not change_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="drive_change_not_found")

        drive_row = workflow_run_files.get_drive_file_row(
            db,
            run_id=run_id,
            user_id=current_user.sub,
            drive_path=drive_path,
        )
        if not drive_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="drive_file_not_found")

        controller_base_url = _get_run_controller_base_url(db, run_id, current_user.sub)
    finally:
        db.close()

    try:
        storage = get_attachment_storage()
    except AttachmentStorageError as exc:
        logger.error("Attachment storage misconfigured: %s", exc)
        raise HTTPException(status_code=500, detail="attachments_not_configured")

    content_type = change_row.content_type or mimetypes.guess_type(drive_path)[0] or DEFAULT_ATTACHMENT_CONTENT_TYPE
    presigned_put_url = storage.generate_presigned_put(change_row.r2_key, content_type=content_type)

    controller = VMControllerClient(base_url=controller_base_url)
    controller.wait_for_health()
    windows = ":" in DRIVE_VM_BASE_PATH or "\\" in DRIVE_VM_BASE_PATH
    vm_path = drive_row.get("vm_path")
    if not vm_path:
        if windows:
            vm_path = str(PureWindowsPath(DRIVE_VM_BASE_PATH, *drive_path.split("/")))
        else:
            vm_path = str(PurePosixPath(DRIVE_VM_BASE_PATH, *drive_path.split("/")))

    try:
        controller.upload_file_to_url(vm_path, presigned_put_url, content_type=content_type)
    except Exception as exc:
        logger.error("[drive] failed to upload %s to R2: %s", vm_path, exc)
        raise HTTPException(status_code=500, detail="drive_upload_failed")

    return {
        "path": drive_path,
        "r2_key": change_row.r2_key,
        "content_type": content_type,
        "size": change_row.size_bytes,
        "status": "uploaded",
    }


@router.get("/runs/{run_id}/drive-summary")
def get_drive_summary(
    run_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        if not workflow_runs.is_owned(db, run_id=run_id, user_id=current_user.sub):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run_not_found")
        drive_rows = workflow_run_files.list_drive_files_for_run(db, run_id=run_id)
        change_rows = workflow_run_drive_changes.list_for_run_user(
            db,
            run_id=run_id,
            user_id=current_user.sub,
        )
    finally:
        db.close()

    try:
        storage = get_attachment_storage()
    except AttachmentStorageError as exc:
        logger.error("Attachment storage misconfigured: %s", exc)
        raise HTTPException(status_code=500, detail="attachments_not_configured")

    changes: List[Dict[str, Any]] = []
    new_files: List[Dict[str, Any]] = []
    unchanged: List[Dict[str, Any]] = []

    change_by_path = {row.path: row for row in change_rows if row.path}
    changed_paths = set(change_by_path.keys())

    for row in change_rows:
        drive_path = row.path
        if not drive_path:
            continue
        change_type = "new" if not row.baseline_hash else "modified"
        content_type = row.content_type or mimetypes.guess_type(drive_path)[0] or DEFAULT_ATTACHMENT_CONTENT_TYPE
        current_get_url = storage.generate_presigned_get(row.r2_key)
        backup_get_url = None
        if change_type == "modified":
            backup_key = build_drive_backup_key(current_user.sub, run_id, drive_path)
            backup_get_url = storage.generate_presigned_get(backup_key)

        change_payload = {
            "path": drive_path,
            "r2_key": row.r2_key,
            "content_type": content_type,
            "size": row.size_bytes,
            "change_type": change_type,
            "baseline_hash": row.baseline_hash,
            "new_hash": row.new_hash,
            "current_get_url": current_get_url,
            "backup_get_url": backup_get_url,
        }
        changes.append(change_payload)
        if change_type == "new":
            new_files.append(change_payload)

    for row in drive_rows:
        drive_path = row.get("drive_path") or row.get("filename")
        r2_key = row.get("r2_key") or row.get("storage_key")
        if not drive_path or not r2_key or drive_path in changed_paths:
            continue
        content_type = row.get("content_type") or mimetypes.guess_type(drive_path)[0] or DEFAULT_ATTACHMENT_CONTENT_TYPE
        unchanged.append(
            {
                "path": drive_path,
                "r2_key": r2_key,
                "content_type": content_type,
                "size": row.get("size_bytes"),
                "current_get_url": storage.generate_presigned_get(r2_key),
            }
        )

    return {
        "run_id": run_id,
        "changes": changes,
        "new_files": new_files,
        "unchanged": unchanged,
    }


@router.get("/runs/{run_id}/drive-file")
def download_drive_file(
    run_id: str,
    path: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    try:
        drive_path = normalize_drive_path(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    db = SessionLocal()
    try:
        row = workflow_run_files.get_drive_file_row(
            db,
            run_id=run_id,
            user_id=current_user.sub,
            drive_path=drive_path,
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="drive_file_not_found")
        controller_base_url = _get_run_controller_base_url(db, run_id, current_user.sub)
    finally:
        db.close()

    controller = VMControllerClient(base_url=controller_base_url)
    controller.wait_for_health()
    windows = ":" in DRIVE_VM_BASE_PATH or "\\" in DRIVE_VM_BASE_PATH
    vm_path = row.get("vm_path")
    if not vm_path:
        if windows:
            vm_path = str(PureWindowsPath(DRIVE_VM_BASE_PATH, *drive_path.split("/")))
        else:
            vm_path = str(PurePosixPath(DRIVE_VM_BASE_PATH, *drive_path.split("/")))
    content_type = row.get("content_type") or mimetypes.guess_type(drive_path)[0] or DEFAULT_ATTACHMENT_CONTENT_TYPE

    def _iter_stream():
        with controller.stream_file(vm_path) as resp:
            for chunk in resp.iter_content(chunk_size=DOWNLOAD_CHUNK_BYTES):
                if chunk:
                    yield chunk

    return StreamingResponse(_iter_stream(), media_type=content_type)


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
    db = SessionLocal()
    try:
        rows = workflow_runs.list_runs_with_workflow(
            db,
            user_id=current_user.sub,
            status_filter=status_filter,
            folder_id=folder_id,
            limit=limit,
        )
        return {"runs": rows}
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
