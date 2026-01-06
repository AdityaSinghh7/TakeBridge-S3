from __future__ import annotations

import json
import logging
import os
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Header, HTTPException, Request, status

from shared.db.engine import SessionLocal
from shared.db import vm_instances, workflow_runs, workflow_run_files, workflow_run_drive_changes
from shared.db.models import WorkflowRunDriveChange, WorkflowRunFile
from shared.db.sql import execute_text
from shared.storage import get_attachment_storage, AttachmentStorageError
from shared.supabase_client import get_service_supabase_client
from server.api.drive_utils import build_drive_key
from orchestrator_agent.capabilities import fetch_mcp_capabilities

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal-runtime"])

PERSISTED_EVENTS = {
    "orchestrator.planning.completed",
    "orchestrator.step.completed",
    "orchestrator.task.completed",
    "orchestrator.summary.created",
    "runner.started",
    "runner.step.agent_response",
    "runner.step.behavior",
    "runner.step.completed",
    "runner.completed",
    "worker.reflection.summary",
    "worker.step.ready",
    "code_agent.session.started",
    "code_agent.session.completed",
    "code_agent.step.response",
    "code_agent.step.execution",
    "code_agent.step.completed",
    "grounding.generate_coords.service_failed",
    "grounding.generate_text_coords.started",
    "grounding.generate_text_coords.completed",
    "mcp.task.started",
    "mcp.planner.started",
    "mcp.task.completed",
    "mcp.planner.failed",
    "mcp.search.completed",
    "mcp.action.planned",
    "mcp.action.failed",
    "mcp.action.started",
    "mcp.action.completed",
    "mcp.sandbox.run",
    "mcp.observation_processor.completed",
    "mcp.summary.created",
    "mcp.high_signal",
    "mcp.step.recorded",
    "human_attention.required",
    "human_attention.resumed",
    "response.failed",
    "error",
    "workspace.attachments",
}


def _token_fingerprint(token: str) -> str:
    if not token:
        return "unset"
    import hashlib

    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:10]


def _require_internal_token(
    token: Optional[str],
    *,
    run_id: Optional[str] = None,
    user_agent: Optional[str] = None,
    token_source: Optional[str] = None,
) -> None:
    expected = (os.getenv("INTERNAL_API_TOKEN") or "").strip()
    provided = (token or "").strip()
    if not expected or not secrets.compare_digest(provided, expected):
        logger.warning(
            "Internal runtime API forbidden run_id=%s token_source=%s expected_set=%s expected_len=%s expected_fp=%s provided_len=%s provided_fp=%s user_agent=%s",
            run_id,
            token_source or "unknown",
            bool(expected),
            len(expected),
            _token_fingerprint(expected),
            len(provided),
            _token_fingerprint(provided),
            (user_agent or "")[:120],
        )
        raise HTTPException(status_code=403, detail="forbidden")


def _extract_token(
    x_internal_token: Optional[str],
    authorization: Optional[str],
) -> tuple[Optional[str], str]:
    if x_internal_token:
        return x_internal_token, "x-internal-token"
    if authorization:
        auth = authorization.strip()
        if auth.lower().startswith("bearer "):
            return auth[7:].strip(), "authorization"
        return auth, "authorization"
    return None, "missing"


def _parse_json_dict(value: Any) -> Dict[str, Any]:
    if not value:
        return {}
    if isinstance(value, dict):
        return dict(value)
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


def _json_safe(val: Any) -> Any:
    try:
        json.dumps(val)
        return val
    except Exception:
        if isinstance(val, dict):
            return {k: _json_safe(v) for k, v in val.items()}
        if isinstance(val, (list, tuple)):
            return [_json_safe(v) for v in val]
        return str(val)


def _event_indicates_error(kind: str, payload: Optional[Dict[str, Any]]) -> bool:
    payload = payload or {}
    if kind in {"mcp.action.failed", "mcp.planner.failed", "response.failed", "error"}:
        return True
    if payload.get("error"):
        return True
    if payload.get("success") is False:
        return True
    status_val = payload.get("status")
    if isinstance(status_val, str) and status_val.lower() in {"failed", "error", "attention"}:
        return True
    completion_reason = payload.get("completion_reason")
    if isinstance(completion_reason, str) and completion_reason.upper() in {"FAIL", "HANDOFF_TO_HUMAN"}:
        return True
    return False


def _touch_run_row(run_id: str) -> None:
    db = SessionLocal()
    try:
        workflow_runs.touch_run(db, run_id=run_id)
        try:
            from shared.db.user_metadata import record_run_heartbeat

            record_run_heartbeat(db, run_id=run_id)
        except Exception:
            pass
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def _insert_run_event(
    run_id: str,
    kind: str,
    message: str,
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    try:
        client = get_service_supabase_client()
        client.table("run_events").insert(
            {
                "id": str(uuid.uuid4()),
                "run_id": run_id,
                "kind": kind,
                "message": message,
                "payload": _json_safe(payload) if payload else {},
            }
        ).execute()
    except Exception:
        logger.debug("Failed to insert run_event run_id=%s kind=%s", run_id, kind)
    _touch_run_row(run_id)
    if _event_indicates_error(kind, payload):
        db = SessionLocal()
        try:
            from shared.db.user_metadata import record_run_event

            record_run_event(
                db,
                run_id=run_id,
                kind=kind,
                message=message,
                payload=payload or {},
            )
            db.commit()
        except Exception:
            db.rollback()
            logger.debug("Failed to update user metadata for run_event run_id=%s kind=%s", run_id, kind)
        finally:
            db.close()


def _serialize_drive_change(row: WorkflowRunDriveChange) -> Dict[str, Any]:
    def _iso(dt: Any) -> Optional[str]:
        if isinstance(dt, datetime):
            return dt.isoformat()
        return None

    return {
        "id": row.id,
        "run_id": row.run_id,
        "user_id": row.user_id,
        "path": row.path,
        "r2_key": row.r2_key,
        "baseline_hash": row.baseline_hash,
        "new_hash": row.new_hash,
        "size_bytes": row.size_bytes,
        "content_type": row.content_type,
        "status": row.status,
        "committed_at": _iso(row.committed_at),
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


@router.get("/runs/{run_id}/context")
def get_run_context(
    run_id: str,
    request: Request,
    x_internal_token: Optional[str] = Header(default=None, alias="X-Internal-Token"),
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    token_value, token_source = _extract_token(x_internal_token, authorization)
    _require_internal_token(token_value, run_id=run_id, token_source=token_source, user_agent=request.headers.get("user-agent"))

    db = SessionLocal()
    try:
        row = (
            execute_text(
                db,
                """
                SELECT id, workflow_id, user_id, metadata, environment
                FROM workflow_runs
                WHERE id = :run_id
                """,
                {"run_id": run_id},
            )
            .mappings()
            .first()
        )
        if not row:
            raise HTTPException(status_code=404, detail="run_not_found")
        metadata = _parse_json_dict(row.get("metadata"))
        environment = _parse_json_dict(row.get("environment"))
        tool_constraints = metadata.get("tool_constraints") if isinstance(metadata, dict) else None
        endpoint = environment.get("endpoint") if isinstance(environment, dict) else None
        return {
            "run_id": row.get("id"),
            "workflow_id": row.get("workflow_id"),
            "user_id": row.get("user_id"),
            "metadata": metadata,
            "environment": environment,
            "tool_constraints": tool_constraints,
            "endpoint": endpoint,
        }
    finally:
        db.close()


@router.get("/runs/{run_id}/resume-context")
def get_resume_context(
    run_id: str,
    request: Request,
    x_internal_token: Optional[str] = Header(default=None, alias="X-Internal-Token"),
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    token_value, token_source = _extract_token(x_internal_token, authorization)
    _require_internal_token(token_value, run_id=run_id, token_source=token_source, user_agent=request.headers.get("user-agent"))

    db = SessionLocal()
    try:
        row = workflow_runs.get_resume_row(db, run_id=run_id)
        if not row:
            raise HTTPException(status_code=404, detail="run_not_found")
        environment = _parse_json_dict(row.get("environment"))
        return {
            "run_id": run_id,
            "user_id": row.get("user_id"),
            "status": row.get("status"),
            "agent_states": row.get("agent_states"),
            "environment": environment,
        }
    finally:
        db.close()


@router.get("/runs/{run_id}/agent-states")
def get_agent_states(
    run_id: str,
    request: Request,
    x_internal_token: Optional[str] = Header(default=None, alias="X-Internal-Token"),
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    token_value, token_source = _extract_token(x_internal_token, authorization)
    _require_internal_token(token_value, run_id=run_id, token_source=token_source, user_agent=request.headers.get("user-agent"))

    db = SessionLocal()
    try:
        agent_states = workflow_runs.get_agent_states(run_id, db=db)
        return {"agent_states": agent_states}
    finally:
        db.close()


@router.post("/runs/{run_id}/events")
def persist_run_event(
    run_id: str,
    request: Request,
    payload: Dict[str, Any] = Body(default_factory=dict),
    x_internal_token: Optional[str] = Header(default=None, alias="X-Internal-Token"),
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    token_value, token_source = _extract_token(x_internal_token, authorization)
    _require_internal_token(token_value, run_id=run_id, token_source=token_source, user_agent=request.headers.get("user-agent"))

    event = payload.get("event")
    if not event:
        raise HTTPException(status_code=400, detail="event_required")
    if event not in PERSISTED_EVENTS:
        return {"persisted": False}
    message = payload.get("message") or str(payload.get("payload") or event)
    data = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
    _insert_run_event(run_id=run_id, kind=str(event), message=str(message), payload=data)
    return {"persisted": True}


@router.post("/runs/{run_id}/status")
def update_run_status(
    run_id: str,
    request: Request,
    payload: Dict[str, Any] = Body(default_factory=dict),
    x_internal_token: Optional[str] = Header(default=None, alias="X-Internal-Token"),
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    token_value, token_source = _extract_token(x_internal_token, authorization)
    _require_internal_token(token_value, run_id=run_id, token_source=token_source, user_agent=request.headers.get("user-agent"))

    status_val = payload.get("status")
    if not status_val:
        raise HTTPException(status_code=400, detail="status_required")
    summary = payload.get("summary")
    db = SessionLocal()
    try:
        workflow_runs.update_status(
            db,
            run_id=run_id,
            status=str(status_val),
            summary=str(summary) if summary is not None else None,
            terminal_statuses={"success", "error", "attention", "cancelled", "partial"},
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return {"updated": True}


@router.post("/runs/{run_id}/environment")
def merge_run_environment(
    run_id: str,
    request: Request,
    payload: Dict[str, Any] = Body(default_factory=dict),
    x_internal_token: Optional[str] = Header(default=None, alias="X-Internal-Token"),
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    token_value, token_source = _extract_token(x_internal_token, authorization)
    _require_internal_token(token_value, run_id=run_id, token_source=token_source, user_agent=request.headers.get("user-agent"))

    patch = payload.get("patch")
    if not isinstance(patch, dict):
        raise HTTPException(status_code=400, detail="patch_required")
    db = SessionLocal()
    try:
        merged = workflow_runs.merge_environment(db, run_id=run_id, patch=patch)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return {"environment": merged}


@router.post("/runs/{run_id}/vm")
def register_vm_instance(
    run_id: str,
    request: Request,
    payload: Dict[str, Any] = Body(default_factory=dict),
    x_internal_token: Optional[str] = Header(default=None, alias="X-Internal-Token"),
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    token_value, token_source = _extract_token(x_internal_token, authorization)
    _require_internal_token(token_value, run_id=run_id, token_source=token_source, user_agent=request.headers.get("user-agent"))

    vm_id = payload.get("vm_id") or str(uuid.uuid4())
    endpoint = payload.get("endpoint") or {}
    provider = payload.get("provider") or "unknown"
    spec = payload.get("spec") or {}

    db = SessionLocal()
    try:
        vm_instances.insert_vm_instance(
            db,
            vm_id=vm_id,
            run_id=run_id,
            status="ready",
            provider=str(provider),
            spec=spec,
            endpoint=endpoint,
        )
        workflow_runs.set_vm_id(db, run_id=run_id, vm_id=vm_id)
        workflow_runs.merge_environment(db, run_id=run_id, patch={"endpoint": endpoint})
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    return {"vm_id": vm_id, "registered": True}


@router.post("/runs/{run_id}/agent-states")
def merge_agent_states(
    run_id: str,
    request: Request,
    payload: Dict[str, Any] = Body(default_factory=dict),
    x_internal_token: Optional[str] = Header(default=None, alias="X-Internal-Token"),
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    token_value, token_source = _extract_token(x_internal_token, authorization)
    _require_internal_token(token_value, run_id=run_id, token_source=token_source, user_agent=request.headers.get("user-agent"))

    patch = payload.get("patch")
    if not isinstance(patch, dict):
        raise HTTPException(status_code=400, detail="patch_required")
    path = payload.get("path")
    if path is not None and not isinstance(path, list):
        raise HTTPException(status_code=400, detail="path_must_be_list")
    from shared.db.workflow_runs import merge_agent_states as _merge_agent_states

    _merge_agent_states(run_id, patch, path=path)
    return {"merged": True}


@router.get("/runs/{run_id}/drive-files")
def get_drive_files(
    run_id: str,
    request: Request,
    ensure_full: bool = False,
    x_internal_token: Optional[str] = Header(default=None, alias="X-Internal-Token"),
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    token_value, token_source = _extract_token(x_internal_token, authorization)
    _require_internal_token(token_value, run_id=run_id, token_source=token_source, user_agent=request.headers.get("user-agent"))

    db = SessionLocal()
    try:
        rows = workflow_run_files.list_drive_files_for_run(db, run_id=run_id)
        if rows or not ensure_full:
            return {"files": [dict(r) for r in rows]}

        user_id = workflow_runs.get_user_id(db, run_id=run_id)
        if not user_id:
            return {"files": []}
        try:
            storage = get_attachment_storage()
        except AttachmentStorageError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        prefix = build_drive_key(user_id, "")
        drive_items: list[dict[str, Any]] = []
        token = None
        while True:
            resp = storage.list_objects(prefix=prefix, continuation_token=token)
            for entry in resp.get("Contents") or []:
                key = entry.get("Key")
                if not key or not key.startswith(prefix):
                    continue
                rel = key[len(prefix) :]
                if not rel or rel.endswith("/"):
                    continue
                drive_items.append(
                    {
                        "drive_path": rel,
                        "r2_key": key,
                        "size_bytes": entry.get("Size"),
                        "etag": (entry.get("ETag") or "").strip('"') or None,
                    }
                )
            if not resp.get("IsTruncated"):
                break
            token = resp.get("NextContinuationToken")
            if not token:
                break

        if drive_items:
            records = workflow_run_files.build_pending_for_drive_items(
                run_id=run_id,
                user_id=user_id,
                items=drive_items,
            )
            if records:
                workflow_run_files.add_many(db, records)
                db.commit()
            rows = workflow_run_files.list_drive_files_for_run(db, run_id=run_id)
        return {"files": [dict(r) for r in rows]}
    finally:
        db.close()


@router.post("/runs/{run_id}/drive-files/status")
def update_drive_file_status(
    run_id: str,
    request: Request,
    payload: Dict[str, Any] = Body(default_factory=dict),
    x_internal_token: Optional[str] = Header(default=None, alias="X-Internal-Token"),
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    token_value, token_source = _extract_token(x_internal_token, authorization)
    _require_internal_token(token_value, run_id=run_id, token_source=token_source, user_agent=request.headers.get("user-agent"))

    file_id = payload.get("file_id")
    status_val = payload.get("status")
    if not file_id or not status_val:
        raise HTTPException(status_code=400, detail="file_id_and_status_required")

    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        if status_val == "ready":
            workflow_run_files.mark_ready_drive(
                db,
                run_file_id=str(file_id),
                status="ready",
                vm_path=str(payload.get("vm_path") or ""),
                size_bytes=int(payload.get("size_bytes") or 0),
                checksum=str(payload.get("checksum") or ""),
                content_type=payload.get("content_type"),
                updated_at=now,
                r2_key=str(payload.get("r2_key") or ""),
                drive_path=str(payload.get("drive_path") or ""),
            )
        elif status_val == "failed":
            workflow_run_files.mark_failed(
                db,
                run_file_id=str(file_id),
                error=str(payload.get("error") or "unknown_error"),
                updated_at=now,
            )
        else:
            raise HTTPException(status_code=400, detail="unsupported_status")
        db.commit()
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    return {"updated": True}


@router.get("/runs/{run_id}/drive-changes")
def list_drive_changes(
    run_id: str,
    request: Request,
    x_internal_token: Optional[str] = Header(default=None, alias="X-Internal-Token"),
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    token_value, token_source = _extract_token(x_internal_token, authorization)
    _require_internal_token(token_value, run_id=run_id, token_source=token_source, user_agent=request.headers.get("user-agent"))

    db = SessionLocal()
    try:
        user_id = workflow_runs.get_user_id(db, run_id=run_id)
        if not user_id:
            raise HTTPException(status_code=404, detail="run_not_found")
        rows = workflow_run_drive_changes.list_for_run_user(db, run_id=run_id, user_id=user_id)
        drive_rows = workflow_run_files.list_drive_files_for_run(db, run_id=run_id)
        return {
            "user_id": user_id,
            "changes": [_serialize_drive_change(row) for row in rows],
            "drive_files": [dict(r) for r in drive_rows],
        }
    finally:
        db.close()


@router.post("/runs/{run_id}/drive-changes/upsert")
def upsert_drive_changes(
    run_id: str,
    request: Request,
    payload: Dict[str, Any] = Body(default_factory=dict),
    x_internal_token: Optional[str] = Header(default=None, alias="X-Internal-Token"),
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    token_value, token_source = _extract_token(x_internal_token, authorization)
    _require_internal_token(token_value, run_id=run_id, token_source=token_source, user_agent=request.headers.get("user-agent"))

    changes = payload.get("changes") or []
    new_files = payload.get("new_files") or []
    if not isinstance(changes, list) or not isinstance(new_files, list):
        raise HTTPException(status_code=400, detail="changes_and_new_files_must_be_lists")

    db = SessionLocal()
    try:
        user_id = workflow_runs.get_user_id(db, run_id=run_id)
        if not user_id:
            raise HTTPException(status_code=404, detail="run_not_found")
        now = datetime.now(timezone.utc)

        for change in changes:
            if not isinstance(change, dict):
                continue
            path = change.get("path")
            if not path:
                continue
            workflow_run_drive_changes.delete_for_run_path(db, run_id=run_id, path=str(path))
            entry = WorkflowRunDriveChange(
                id=str(uuid.uuid4()),
                run_id=run_id,
                user_id=user_id,
                path=str(path),
                r2_key=str(change.get("r2_key") or ""),
                baseline_hash=change.get("baseline_hash"),
                new_hash=change.get("new_hash"),
                size_bytes=change.get("size_bytes"),
                content_type=change.get("content_type"),
                status="pending",
                committed_at=None,
                created_at=now,
                updated_at=now,
            )
            workflow_run_drive_changes.add(db, entry)

        for item in new_files:
            if not isinstance(item, dict):
                continue
            drive_path = item.get("drive_path") or item.get("path")
            r2_key = item.get("r2_key")
            if not drive_path or not r2_key:
                continue
            record = WorkflowRunFile(
                id=str(uuid.uuid4()),
                run_id=run_id,
                workflow_file_id=None,
                user_id=user_id,
                source_type="drive",
                storage_key=str(r2_key),
                r2_key=str(r2_key),
                drive_path=str(drive_path),
                filename=str(item.get("filename") or os.path.basename(str(drive_path)) or "file"),
                content_type=item.get("content_type"),
                size_bytes=item.get("size_bytes"),
                checksum=item.get("checksum"),
                status="ready",
                vm_path=item.get("vm_path"),
                metadata_json={},
            )
            db.add(record)

        db.commit()
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    return {"updated": True}


@router.post("/runs/{run_id}/drive-changes/status")
def update_drive_change_status(
    run_id: str,
    request: Request,
    payload: Dict[str, Any] = Body(default_factory=dict),
    x_internal_token: Optional[str] = Header(default=None, alias="X-Internal-Token"),
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    token_value, token_source = _extract_token(x_internal_token, authorization)
    _require_internal_token(token_value, run_id=run_id, token_source=token_source, user_agent=request.headers.get("user-agent"))

    path = payload.get("path")
    status_val = payload.get("status")
    if not path or not status_val:
        raise HTTPException(status_code=400, detail="path_and_status_required")

    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        if status_val == "committed":
            workflow_run_drive_changes.mark_committed(
                db,
                run_id=run_id,
                path=str(path),
                committed_at=now,
            )
        elif status_val == "failed":
            workflow_run_drive_changes.mark_failed(
                db,
                run_id=run_id,
                path=str(path),
                error=str(payload.get("error") or ""),
                updated_at=now,
            )
        else:
            raise HTTPException(status_code=400, detail="unsupported_status")
        db.commit()
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    return {"updated": True}


@router.get("/users/{user_id}/mcp-capabilities")
def get_mcp_capabilities(
    user_id: str,
    request: Request,
    force_refresh: bool = False,
    x_internal_token: Optional[str] = Header(default=None, alias="X-Internal-Token"),
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    token_value, token_source = _extract_token(x_internal_token, authorization)
    _require_internal_token(token_value, run_id=None, token_source=token_source, user_agent=request.headers.get("user-agent"))
    return fetch_mcp_capabilities(user_id, force_refresh=bool(force_refresh))
