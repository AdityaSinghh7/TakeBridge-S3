from __future__ import annotations

import hashlib
import io
import json
import logging
import mimetypes
import os
import posixpath
from datetime import datetime, timezone
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Dict, List, Optional, Tuple

from server.api.controller_client import VMControllerClient
from server.api.drive_utils import build_drive_changes_key, normalize_drive_path
from shared.storage import get_attachment_storage, AttachmentStorageError

from runtime.api.control_plane_client import ControlPlaneClient

logger = logging.getLogger(__name__)

DRIVE_VM_BASE_PATH = os.path.expanduser(os.getenv("DRIVE_VM_BASE_PATH", "/home/user/session/drive"))
DRIVE_MANIFEST_PATH_OVERRIDE = os.getenv("DRIVE_MANIFEST_PATH")
DOWNLOAD_CHUNK_BYTES = 4 * 1024 * 1024
DOWNLOAD_TIMEOUT = int(os.getenv("DRIVE_DOWNLOAD_TIMEOUT", "300"))
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


def _upload_manifest(controller: VMControllerClient, manifest: List[Dict[str, Any]], *, windows: bool) -> None:
    payload = json.dumps(manifest, separators=(",", ":")).encode("utf-8")
    manifest_path = _manifest_path(DRIVE_VM_BASE_PATH, windows=windows)
    _ensure_vm_dir(controller, manifest_path, windows=windows)
    controller.upload_file(manifest_path, io.BytesIO(payload))


def stage_drive_files_for_run(run_id: str, workspace: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Download drive files for a run into its VM workspace."""
    controller_url = workspace.get("controller_base_url")
    if not controller_url:
        raise DriveStageError("workspace missing controller_base_url")

    client = ControlPlaneClient()
    try:
        storage = get_attachment_storage()
    except AttachmentStorageError as exc:
        raise DriveStageError(str(exc)) from exc

    response = client.get_drive_files(run_id, ensure_full=True)
    rows = response.get("files") or []
    if not rows:
        return []

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
            client.update_drive_file_status(
                run_id,
                {
                    "file_id": row.get("id"),
                    "status": "failed",
                    "error": str(exc),
                },
            )
            raise DriveStageError(f"failed_to_stage_drive_file:{drive_path}") from exc

        client.update_drive_file_status(
            run_id,
            {
                "file_id": row.get("id"),
                "status": "ready",
                "vm_path": dest_path,
                "size_bytes": size,
                "checksum": checksum,
                "content_type": content_type,
                "r2_key": r2_key,
                "drive_path": drive_path,
            },
        )

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


def detect_drive_changes(run_id: str, workspace: Dict[str, Any]) -> List[Dict[str, Any]]:
    controller_url = workspace.get("controller_base_url")
    if not controller_url or not run_id:
        return []

    client = ControlPlaneClient()
    response = client.get_drive_files(run_id, ensure_full=False)
    rows = response.get("files") or []
    if not rows:
        return []

    controller = VMControllerClient(base_url=controller_url)
    controller.wait_for_health()
    windows = _is_windows_path(DRIVE_VM_BASE_PATH)
    now = datetime.now(timezone.utc)
    changes: List[Dict[str, Any]] = []
    new_files: List[Dict[str, Any]] = []

    known_paths = {
        (row.get("drive_path") or row.get("filename"))
        for row in rows
        if row.get("drive_path") or row.get("filename")
    }

    user_id = rows[0].get("user_id") if rows else None

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

        changes.append(
            {
                "path": drive_path,
                "r2_key": change_key,
                "baseline_hash": baseline_hash,
                "new_hash": new_hash,
                "size_bytes": size,
                "content_type": content_type,
                "change_type": "modified" if baseline_hash else "new",
                "updated_at": now.isoformat(),
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

            changes.append(
                {
                    "path": drive_path,
                    "r2_key": change_key,
                    "baseline_hash": None,
                    "new_hash": new_hash,
                    "size_bytes": size,
                    "content_type": content_type,
                    "change_type": "new",
                    "updated_at": now.isoformat(),
                }
            )
            new_files.append(
                {
                    "drive_path": drive_path,
                    "r2_key": change_key,
                    "checksum": new_hash,
                    "size_bytes": size,
                    "content_type": content_type,
                    "vm_path": vm_path,
                    "filename": posixpath.basename(drive_path) or "file",
                }
            )

    if changes or new_files:
        client.upsert_drive_changes(run_id, changes=changes, new_files=new_files)

    return changes


def commit_drive_changes_for_run(run_id: str, workspace: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Upload detected drive changes to R2 under the run-scoped changes prefix."""
    controller_url = workspace.get("controller_base_url")
    if not controller_url or not run_id:
        return []

    client = ControlPlaneClient()
    response = client.list_drive_changes(run_id)
    user_id = response.get("user_id")
    rows = response.get("changes") or []
    drive_rows = response.get("drive_files") or []
    if not user_id or not rows:
        return []

    try:
        storage = get_attachment_storage()
    except AttachmentStorageError as exc:
        raise DriveStageError(str(exc)) from exc

    controller = VMControllerClient(base_url=controller_url)
    controller.wait_for_health()
    windows = _is_windows_path(DRIVE_VM_BASE_PATH)

    drive_map = {
        (row.get("drive_path") or row.get("filename")): row
        for row in drive_rows
        if row.get("drive_path") or row.get("filename")
    }

    results: List[Dict[str, Any]] = []

    for row in rows:
        if row.get("status") == "committed":
            continue
        drive_path = row.get("path")
        r2_key = row.get("r2_key")
        if not drive_path or not r2_key:
            continue

        change_type = "new" if not row.get("baseline_hash") else "modified"
        content_type = row.get("content_type") or mimetypes.guess_type(drive_path)[0] or DEFAULT_ATTACHMENT_CONTENT_TYPE

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
            client.update_drive_change_status(run_id, path=drive_path, status="failed", error=str(exc))
            continue

        client.update_drive_change_status(run_id, path=drive_path, status="committed")
        results.append(
            {
                "path": drive_path,
                "r2_key": r2_key,
                "change_type": change_type,
                "content_type": content_type,
            }
        )

    return results


__all__ = [
    "DRIVE_VM_BASE_PATH",
    "DOWNLOAD_CHUNK_BYTES",
    "DriveStageError",
    "stage_drive_files_for_run",
    "detect_drive_changes",
    "commit_drive_changes_for_run",
]
