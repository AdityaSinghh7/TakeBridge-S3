from __future__ import annotations

import hashlib
import io
import json
import logging
import mimetypes
import os
import posixpath
import posixpath
import uuid
from datetime import datetime, timezone
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

from shared.db.engine import SessionLocal
from shared.db.models import WorkflowRunDriveChange, WorkflowRunFile
from shared.db.models import WorkflowRunDriveChange, WorkflowRunFile
from shared.db import workflow_run_drive_changes, workflow_run_files, workflow_runs
from shared.storage import get_attachment_storage, AttachmentStorageError
from server.api.controller_client import VMControllerClient
from server.api.drive_utils import build_drive_changes_key, build_drive_key, normalize_drive_path

logger = logging.getLogger(__name__)

DRIVE_VM_BASE_PATH = os.path.expanduser(os.getenv("DRIVE_VM_BASE_PATH", "/home/user/session/drive"))
DRIVE_MANIFEST_PATH_OVERRIDE = os.getenv("DRIVE_MANIFEST_PATH")
DOWNLOAD_CHUNK_BYTES = 4 * 1024 * 1024
DOWNLOAD_TIMEOUT = int(os.getenv("DRIVE_DOWNLOAD_TIMEOUT", "300"))
DEFAULT_ATTACHMENT_CONTENT_TYPE = "application/octet-stream"
DEFAULT_ATTACHMENT_CONTENT_TYPE = "application/octet-stream"


class DriveStageError(RuntimeError):
    """Raised when drive files cannot be staged on the run VM."""


def _is_windows_path(path: str) -> bool:
    return ":" in path or "\\" in path


def _build_drive_vm_path(drive_path: str, *, base_path: str, windows: bool) -> str:
    parts = [part for part in drive_path.split("/") if part]
    if windows:
        return str(PureWindowsPath(base_path, *parts))
    return str(PurePosixPath(base_path, *parts))


def _manifest_path(base_path: str, *, windows: bool) -> str:
    if DRIVE_MANIFEST_PATH_OVERRIDE:
        return DRIVE_MANIFEST_PATH_OVERRIDE
    if windows:
        return str(PureWindowsPath(base_path).parent / "manifest.json")
    return str(PurePosixPath(base_path).parent / "manifest.json")


def _lookup_run_user_id(db: Any, run_id: str) -> Optional[str]:
    row = (
        db.execute(
            text("SELECT user_id FROM workflow_runs WHERE id = :run_id"),
            {"run_id": run_id},
        )
        .mappings()
        .first()
    )
    if not row:
        return None
    return row.get("user_id")


def _list_drive_objects(storage: Any, user_id: str) -> List[Dict[str, Any]]:
    prefix = build_drive_key(user_id, "")
    items: List[Dict[str, Any]] = []
    token: Optional[str] = None
    while True:
        resp = storage.list_objects(prefix=prefix, continuation_token=token)
        for entry in resp.get("Contents") or []:
            key = entry.get("Key")
            if not key or not key.startswith(prefix):
                continue
            rel = key[len(prefix) :]
            if not rel or rel.endswith("/"):
                continue
            items.append(
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
    return items


def _insert_drive_rows_for_run(
    db: Any,
    *,
    run_id: str,
    user_id: str,
    items: List[Dict[str, Any]],
) -> None:
    records: List[WorkflowRunFile] = []
    for item in items:
        drive_path = item.get("drive_path")
        r2_key = item.get("r2_key")
        if not drive_path or not r2_key:
            continue
        content_type = mimetypes.guess_type(drive_path)[0]
        records.append(
            WorkflowRunFile(
                id=str(uuid.uuid4()),
                run_id=run_id,
                workflow_file_id=None,
                user_id=user_id,
                source_type="drive",
                storage_key=r2_key,
                drive_path=drive_path,
                r2_key=r2_key,
                filename=posixpath.basename(drive_path) or "file",
                content_type=content_type,
                size_bytes=item.get("size_bytes"),
                checksum=None,
                status="pending",
                metadata_json={},
            )
        )
    if records:
        db.add_all(records)
        db.commit()


def _ensure_vm_dir(controller: VMControllerClient, dest_path: str, *, windows: bool) -> None:
    parent = str(PureWindowsPath(dest_path).parent) if windows else str(PurePosixPath(dest_path).parent)
    if not parent:
        return
    if windows:
        try:
            controller.execute(
                f'powershell -NoProfile -Command "New-Item -ItemType Directory -Force -Path \\"{parent}\\""',
                shell=True,
                setup=True,
            )
        except Exception:
            controller.execute(["cmd", "/c", "mkdir", parent], setup=True)
        return
    controller.execute(["mkdir", "-p", parent], setup=True)


def _hash_vm_file(controller: VMControllerClient, path: str) -> Tuple[str, int]:
    hasher = hashlib.sha256()
    size = 0
    with controller.stream_file(path, timeout=DOWNLOAD_TIMEOUT) as resp:
        for chunk in resp.iter_content(chunk_size=DOWNLOAD_CHUNK_BYTES):
            if not chunk:
                continue
            hasher.update(chunk)
            size += len(chunk)
    return hasher.hexdigest(), size


def _list_vm_files(controller: VMControllerClient, base_path: str) -> List[str]:
    pending = [base_path]
    files: List[str] = []
    while pending:
        current = pending.pop()
        try:
            resp = controller.list_directory(current)
        except Exception as exc:
            logger.warning("[drive] list_directory failed for %s: %s", current, exc)
            continue
        entries = resp.get("entries") or []
        for entry in entries:
            path = entry.get("path")
            if not path:
                continue
            if entry.get("is_dir"):
                pending.append(path)
            else:
                files.append(path)
    return files


def _drive_path_from_vm_path(vm_path: str, *, base_path: str, windows: bool) -> Optional[str]:
    base = PureWindowsPath(base_path) if windows else PurePosixPath(base_path)
    path = PureWindowsPath(vm_path) if windows else PurePosixPath(vm_path)
    try:
        relative = path.relative_to(base)
    except ValueError:
        return None
    if not relative.parts:
        return None
    rel_path = "/".join(relative.parts)
    try:
        return normalize_drive_path(rel_path)
    except ValueError:
        return None


def stage_drive_files_for_run(run_id: str, workspace: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Download drive files for a run into its VM workspace."""
    controller_url = workspace.get("controller_base_url")
    if not controller_url:
        raise DriveStageError("workspace missing controller_base_url")

    db = SessionLocal()
    try:
        try:
            storage = get_attachment_storage()
        except AttachmentStorageError as exc:
            raise DriveStageError(str(exc)) from exc

        rows = workflow_run_files.list_drive_files_for_run(db, run_id=run_id)
        if not rows:
            user_id = workflow_runs.get_user_id(db, run_id=run_id)
            if not user_id:
                return []
            drive_items = _list_drive_objects(storage, user_id)
            if not drive_items:
                return []
            logger.info(
                "[drive] no drive paths requested; staging full drive for user %s (%s files)",
                user_id,
                len(drive_items),
            )
            run_file_records = workflow_run_files.build_pending_for_drive_items(
                run_id=run_id,
                user_id=user_id,
                items=drive_items,
            )
            if run_file_records:
                workflow_run_files.add_many(db, run_file_records)
                db.commit()
            rows = workflow_run_files.list_drive_files_for_run(db, run_id=run_id)
            if not rows:
                return []

        logger.info("[drive] staging %s files for run %s", len(rows), run_id)

        controller = VMControllerClient(base_url=controller_url)
        controller.wait_for_health()
        windows = _is_windows_path(DRIVE_VM_BASE_PATH)

        manifest: List[Dict[str, Any]] = []
        now = datetime.now(timezone.utc)

        for row in rows:
            drive_path = row.get("drive_path") or row.get("filename")
            r2_key = row.get("r2_key") or row.get("storage_key")
            if not drive_path or not r2_key:
                logger.warning("[drive] skipping row with missing path/key id=%s", row.get("id"))
                continue

            if row.get("status") == "ready" and row.get("vm_path"):
                manifest.append(
                    {
                        "path": drive_path,
                        "r2_key": r2_key,
                        "size": row.get("size_bytes"),
                        "staged_at": now.isoformat(),
                    }
                )
                continue

            dest_path = row.get("vm_path") or _build_drive_vm_path(
                drive_path,
                base_path=DRIVE_VM_BASE_PATH,
                windows=windows,
            )
            download_url = storage.generate_presigned_get(r2_key)

            etag = None
            content_type = row.get("content_type")
            try:
                head = storage.head_object(r2_key)
                etag = (head.get("ETag") or "").strip('"') or None
                if not content_type:
                    content_type = head.get("ContentType")
            except Exception:
                pass
            if not content_type:
                content_type = mimetypes.guess_type(drive_path)[0]

            try:
                _ensure_vm_dir(controller, dest_path, windows=windows)
                controller.download_file(download_url, dest_path, timeout=DOWNLOAD_TIMEOUT)
                checksum, size = _hash_vm_file(controller, dest_path)
            except Exception as exc:
                logger.exception("[drive] failed transfer id=%s path=%s", row.get("id"), dest_path)
                workflow_run_files.mark_failed(
                    db,
                    run_file_id=row.get("id") or "",
                    error=str(exc),
                    updated_at=now,
                )
                db.commit()
                raise DriveStageError(f"failed_to_stage_drive_file:{drive_path}") from exc

            workflow_run_files.mark_ready_drive(
                db,
                run_file_id=row.get("id") or "",
                status="ready",
                vm_path=dest_path,
                size_bytes=size,
                checksum=checksum,
                content_type=content_type,
                updated_at=now,
                r2_key=r2_key,
                drive_path=drive_path,
            )
            db.commit()

            manifest.append(
                {
                    "path": drive_path,
                    "r2_key": r2_key,
                    "etag": etag,
                    "size": size,
                    "staged_at": now.isoformat(),
                }
            )

        _upload_manifest(controller, manifest, windows=windows)
        return manifest
    finally:
        db.close()


def _upload_manifest(controller: VMControllerClient, manifest: List[Dict[str, Any]], *, windows: bool) -> None:
    payload = json.dumps(manifest, separators=(",", ":")).encode("utf-8")
    manifest_path = _manifest_path(DRIVE_VM_BASE_PATH, windows=windows)
    _ensure_vm_dir(controller, manifest_path, windows=windows)
    controller.upload_file(manifest_path, io.BytesIO(payload))


def detect_drive_changes(run_id: str, workspace: Dict[str, Any]) -> List[Dict[str, Any]]:
    controller_url = workspace.get("controller_base_url")
    if not controller_url or not run_id:
        return []

    db = SessionLocal()
    try:
        rows = workflow_run_files.list_drive_files_for_changes(db, run_id=run_id)

        controller = VMControllerClient(base_url=controller_url)
        controller.wait_for_health()
        windows = _is_windows_path(DRIVE_VM_BASE_PATH)
        now = datetime.now(timezone.utc)
        changes: List[Dict[str, Any]] = []
        known_paths = {
            (row.get("drive_path") or row.get("filename"))
            for row in rows
            if row.get("drive_path") or row.get("filename")
        }

        user_id = rows[0].get("user_id") if rows else None
        if not user_id:
            user_id = workflow_runs.get_user_id(db, run_id=run_id)

        for row in rows:
            drive_path = row.get("drive_path") or row.get("filename")
            if not drive_path:
                continue

            baseline_hash = row.get("checksum")
            vm_path = row.get("vm_path") or _build_drive_vm_path(
                drive_path,
                base_path=DRIVE_VM_BASE_PATH,
                windows=windows,
            )
            try:
                new_hash, size = _hash_vm_file(controller, vm_path)
            except Exception as exc:
                logger.warning("[drive] failed to hash %s: %s", vm_path, exc)
                continue

            if baseline_hash and baseline_hash == new_hash:
                continue

            change_user_id = row.get("user_id") or user_id
            if not change_user_id:
                continue

            change_key = build_drive_changes_key(change_user_id, run_id, drive_path)
            content_type = row.get("content_type") or mimetypes.guess_type(drive_path)[0]

            workflow_run_drive_changes.delete_for_run_path(
                db,
                run_id=run_id,
                path=drive_path,
            )
            change = WorkflowRunDriveChange(
                id=str(uuid.uuid4()),
                run_id=run_id,
                user_id=change_user_id,
                path=drive_path,
                r2_key=change_key,
                baseline_hash=baseline_hash,
                new_hash=new_hash,
                size_bytes=size,
                content_type=content_type,
                status="pending",
                committed_at=None,
                created_at=now,
                updated_at=now,
            )
            workflow_run_drive_changes.add(db, change)
            changes.append(
                {
                    "path": drive_path,
                    "r2_key": change_key,
                    "baseline_hash": baseline_hash,
                    "new_hash": new_hash,
                    "size": size,
                    "content_type": content_type,
                    "change_type": "modified" if baseline_hash else "new",
                }
            )

        if user_id:
            vm_files = _list_vm_files(controller, DRIVE_VM_BASE_PATH)
            for vm_path in vm_files:
                drive_path = _drive_path_from_vm_path(
                    vm_path,
                    base_path=DRIVE_VM_BASE_PATH,
                    windows=windows,
                )
                if not drive_path or drive_path in known_paths:
                    continue

                change_key = build_drive_changes_key(user_id, run_id, drive_path)
                content_type = mimetypes.guess_type(drive_path)[0]
                try:
                    new_hash, size = _hash_vm_file(controller, vm_path)
                except Exception as exc:
                    logger.warning("[drive] failed to hash new file %s: %s", vm_path, exc)
                    continue

                workflow_run_drive_changes.delete_for_run_path(
                    db,
                    run_id=run_id,
                    path=drive_path,
                )
                change = WorkflowRunDriveChange(
                    id=str(uuid.uuid4()),
                    run_id=run_id,
                    user_id=user_id,
                    path=drive_path,
                    r2_key=change_key,
                    baseline_hash=None,
                    new_hash=new_hash,
                    size_bytes=size,
                    content_type=content_type,
                    status="pending",
                    committed_at=None,
                    created_at=now,
                    updated_at=now,
                )
                workflow_run_drive_changes.add(db, change)
                changes.append(
                    {
                        "path": drive_path,
                        "r2_key": change_key,
                        "baseline_hash": None,
                        "new_hash": new_hash,
                        "size": size,
                        "content_type": content_type,
                        "change_type": "new",
                    }
                )

                new_run_file = WorkflowRunFile(
                    id=str(uuid.uuid4()),
                    run_id=run_id,
                    workflow_file_id=None,
                    user_id=user_id,
                    source_type="drive",
                    storage_key=change_key,
                    r2_key=change_key,
                    drive_path=drive_path,
                    filename=posixpath.basename(drive_path) or "file",
                    content_type=content_type,
                    size_bytes=size,
                    checksum=new_hash,
                    status="ready",
                    vm_path=vm_path,
                    metadata_json={},
                )
                db.add(new_run_file)

        db.commit()
        return changes
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def commit_drive_changes_for_run(run_id: str, workspace: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Upload detected drive changes to R2 under the run-scoped changes prefix."""
    controller_url = workspace.get("controller_base_url")
    if not controller_url or not run_id:
        return []

    db = SessionLocal()
    try:
        user_id = workflow_runs.get_user_id(db, run_id=run_id)
        if not user_id:
            return []
        rows = workflow_run_drive_changes.list_for_run_user(db, run_id=run_id, user_id=user_id)
        if not rows:
            return []
        try:
            storage = get_attachment_storage()
        except AttachmentStorageError as exc:
            raise DriveStageError(str(exc)) from exc

        controller = VMControllerClient(base_url=controller_url)
        controller.wait_for_health()
        windows = _is_windows_path(DRIVE_VM_BASE_PATH)

        drive_rows = workflow_run_files.list_drive_files_for_run(db, run_id=run_id)
        drive_map = {
            (row.get("drive_path") or row.get("filename")): row
            for row in drive_rows
            if row.get("drive_path") or row.get("filename")
        }

        now = datetime.now(timezone.utc)
        results: List[Dict[str, Any]] = []

        for row in rows:
            if getattr(row, "status", None) == "committed":
                continue
            drive_path = row.path
            r2_key = row.r2_key
            if not drive_path or not r2_key:
                continue

            change_type = "new" if not row.baseline_hash else "modified"
            content_type = row.content_type or mimetypes.guess_type(drive_path)[0] or DEFAULT_ATTACHMENT_CONTENT_TYPE

            drive_row = drive_map.get(drive_path) or {}
            vm_path = drive_row.get("vm_path") or _build_drive_vm_path(
                drive_path,
                base_path=DRIVE_VM_BASE_PATH,
                windows=windows,
            )
            presigned_put_url = storage.generate_presigned_put(r2_key, content_type=content_type)
            try:
                controller.upload_file_to_url(vm_path, presigned_put_url, content_type=content_type)
            except Exception as exc:
                logger.warning("[drive] failed to upload %s to R2: %s", vm_path, exc)
                workflow_run_drive_changes.mark_failed(
                    db,
                    run_id=run_id,
                    path=drive_path,
                    error=str(exc),
                    updated_at=now,
                )
                db.commit()
                continue

            workflow_run_drive_changes.mark_committed(
                db,
                run_id=run_id,
                path=drive_path,
                committed_at=now,
            )
            db.commit()

            results.append(
                {
                    "path": drive_path,
                    "r2_key": r2_key,
                    "change_type": change_type,
                    "content_type": content_type,
                }
            )

        return results
    finally:
        db.close()
