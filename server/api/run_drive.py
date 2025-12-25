from __future__ import annotations

import hashlib
import io
import json
import logging
import mimetypes
import os
import posixpath
import uuid
from datetime import datetime, timezone
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

from shared.db.engine import SessionLocal
from shared.db.models import WorkflowRunDriveChange, WorkflowRunFile
from shared.storage import get_attachment_storage, AttachmentStorageError
from server.api.controller_client import VMControllerClient
from server.api.drive_utils import build_drive_key

logger = logging.getLogger(__name__)

DRIVE_VM_BASE_PATH = os.path.expanduser(os.getenv("DRIVE_VM_BASE_PATH", "/home/user/session/drive"))
DRIVE_MANIFEST_PATH_OVERRIDE = os.getenv("DRIVE_MANIFEST_PATH")
DOWNLOAD_CHUNK_BYTES = 4 * 1024 * 1024
DOWNLOAD_TIMEOUT = int(os.getenv("DRIVE_DOWNLOAD_TIMEOUT", "300"))


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


def stage_drive_files_for_run(run_id: str, workspace: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Download drive files for a run into its VM workspace."""
    controller_url = workspace.get("controller_base_url")
    if not controller_url:
        raise DriveStageError("workspace missing controller_base_url")

    db = SessionLocal()
    try:
        rows = (
            db.execute(
                text(
                    """
                    SELECT id, user_id, drive_path, r2_key, storage_key, filename, content_type,
                           size_bytes, checksum, status, vm_path
                    FROM workflow_run_files
                    WHERE run_id = :run_id AND (drive_path IS NOT NULL OR source_type = 'drive')
                    ORDER BY created_at ASC
                    """
                ),
                {"run_id": run_id},
            )
            .mappings()
            .all()
        )
        try:
            storage = get_attachment_storage()
        except AttachmentStorageError as exc:
            raise DriveStageError(str(exc)) from exc

        if not rows:
            user_id = _lookup_run_user_id(db, run_id)
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
            _insert_drive_rows_for_run(db, run_id=run_id, user_id=user_id, items=drive_items)
            rows = (
                db.execute(
                    text(
                        """
                        SELECT id, user_id, drive_path, r2_key, storage_key, filename, content_type,
                               size_bytes, checksum, status, vm_path
                        FROM workflow_run_files
                        WHERE run_id = :run_id AND (drive_path IS NOT NULL OR source_type = 'drive')
                        ORDER BY created_at ASC
                        """
                    ),
                    {"run_id": run_id},
                )
                .mappings()
                .all()
            )
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
                db.execute(
                    text(
                        """
                        UPDATE workflow_run_files
                        SET status = :status, error = :error, updated_at = :updated_at
                        WHERE id = :id
                        """
                    ),
                    {
                        "status": "failed",
                        "error": str(exc),
                        "updated_at": now,
                        "id": row.get("id"),
                    },
                )
                db.commit()
                raise DriveStageError(f"failed_to_stage_drive_file:{drive_path}") from exc

            db.execute(
                text(
                    """
                    UPDATE workflow_run_files
                    SET status = :status, vm_path = :vm_path, size_bytes = :size_bytes,
                        checksum = :checksum, content_type = :content_type, error = NULL,
                        updated_at = :updated_at, r2_key = :r2_key, drive_path = :drive_path
                    WHERE id = :id
                    """
                ),
                {
                    "status": "ready",
                    "vm_path": dest_path,
                    "size_bytes": size,
                    "checksum": checksum,
                    "content_type": content_type,
                    "updated_at": now,
                    "r2_key": r2_key,
                    "drive_path": drive_path,
                    "id": row.get("id"),
                },
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
        rows = (
            db.execute(
                text(
                    """
                    SELECT id, user_id, drive_path, r2_key, storage_key, filename,
                           checksum, vm_path, content_type
                    FROM workflow_run_files
                    WHERE run_id = :run_id AND (drive_path IS NOT NULL OR source_type = 'drive')
                    ORDER BY created_at ASC
                    """
                ),
                {"run_id": run_id},
            )
            .mappings()
            .all()
        )
        if not rows:
            return []

        controller = VMControllerClient(base_url=controller_url)
        controller.wait_for_health()
        windows = _is_windows_path(DRIVE_VM_BASE_PATH)
        now = datetime.now(timezone.utc)
        changes: List[Dict[str, Any]] = []

        for row in rows:
            drive_path = row.get("drive_path") or row.get("filename")
            r2_key = row.get("r2_key") or row.get("storage_key")
            if not drive_path or not r2_key:
                continue
            vm_path = row.get("vm_path") or _build_drive_vm_path(
                drive_path,
                base_path=DRIVE_VM_BASE_PATH,
                windows=windows,
            )
            baseline_hash = row.get("checksum")
            try:
                new_hash, size = _hash_vm_file(controller, vm_path)
            except Exception as exc:
                logger.warning("[drive] failed to hash %s: %s", vm_path, exc)
                continue

            if baseline_hash and baseline_hash == new_hash:
                continue

            db.execute(
                text(
                    """
                    DELETE FROM workflow_run_drive_changes
                    WHERE run_id = :run_id AND path = :path
                    """
                ),
                {"run_id": run_id, "path": drive_path},
            )
            change = WorkflowRunDriveChange(
                id=str(uuid.uuid4()),
                run_id=run_id,
                user_id=row.get("user_id") or "",
                path=drive_path,
                r2_key=r2_key,
                baseline_hash=baseline_hash,
                new_hash=new_hash,
                size_bytes=size,
                content_type=row.get("content_type"),
                status="pending",
                committed_at=None,
                created_at=now,
                updated_at=now,
            )
            db.add(change)
            changes.append(
                {
                    "path": drive_path,
                    "r2_key": r2_key,
                    "baseline_hash": baseline_hash,
                    "new_hash": new_hash,
                    "size": size,
                    "content_type": row.get("content_type"),
                }
            )

        db.commit()
        return changes
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
