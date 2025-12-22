from __future__ import annotations

import os
import logging
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List

import requests
from sqlalchemy import text

from shared.db.engine import SessionLocal
from shared.storage import get_attachment_storage, AttachmentStorageError
from server.api.controller_client import VMControllerClient

logger = logging.getLogger(__name__)

ATTACHMENT_VM_BASE_PATH = os.path.expanduser(os.getenv("ATTACHMENTS_VM_BASE_PATH", "/home/user/context"))
DOWNLOAD_CHUNK_BYTES = 4 * 1024 * 1024
DOWNLOAD_TIMEOUT = int(os.getenv("ATTACHMENTS_DOWNLOAD_TIMEOUT", "300"))


class AttachmentStageError(RuntimeError):
    """Raised when attachments cannot be staged on the run VM."""


def _default_vm_path(run_id: str, filename: str) -> str:
    safe_name = os.path.basename(filename) or "file"
    return os.path.join(ATTACHMENT_VM_BASE_PATH, safe_name)


def _download_to_temp(url: str) -> tempfile.SpooledTemporaryFile:
    logger.info("[attachments] downloading from %s", url)
    tmp = tempfile.SpooledTemporaryFile(max_size=64 * 1024 * 1024)
    with requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT) as resp:
        resp.raise_for_status()
        for chunk in resp.iter_content(chunk_size=DOWNLOAD_CHUNK_BYTES):
            if chunk:
                tmp.write(chunk)
    size = tmp.tell()
    tmp.seek(0)
    logger.info("[attachments] download complete (%s bytes)", size)
    return tmp


def _transfer_to_vm(controller: VMControllerClient, dest_path: str, download_url: str) -> None:
    logger.info("[attachments] transferring to VM path=%s", dest_path)
    tmp_file = _download_to_temp(download_url)
    try:
        controller.upload_file(dest_path, tmp_file)
        logger.info("[attachments] upload complete path=%s", dest_path)
    finally:
        try:
            tmp_file.close()
        except Exception:
            pass


def stage_files_for_run(run_id: str, workspace: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Download and upload workflow files for a run into its VM workspace."""
    controller_url = workspace.get("controller_base_url")
    if not controller_url:
        raise AttachmentStageError("workspace missing controller_base_url")

    db = SessionLocal()
    try:
        rows = (
            db.execute(
                text(
                    """
                    SELECT id, workflow_file_id, storage_key, filename, content_type,
                           size_bytes, status, vm_path
                    FROM workflow_run_files
                    WHERE run_id = :run_id
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
        logger.info("[attachments] staging %s files for run %s", len(rows), run_id)

        try:
            storage = get_attachment_storage()
        except AttachmentStorageError as exc:
            raise AttachmentStageError(str(exc)) from exc

        controller = VMControllerClient(base_url=controller_url)
        controller.wait_for_health()
        manifest: List[Dict[str, Any]] = []

        for row in rows:
            if row["status"] == "ready" and row.get("vm_path"):
                manifest.append(
                    {
                        "id": row["id"],
                        "workflow_file_id": row.get("workflow_file_id"),
                        "filename": row["filename"],
                        "vm_path": row["vm_path"],
                        "size_bytes": row.get("size_bytes"),
                        "content_type": row.get("content_type"),
                    }
                )
                continue

            dest_path = row.get("vm_path") or _default_vm_path(run_id, row["filename"])
            download_url = storage.generate_presigned_get(row["storage_key"])
            now = datetime.now(timezone.utc)

            try:
                _transfer_to_vm(controller, dest_path, download_url)
            except Exception as exc:
                logger.exception("[attachments] failed transfer id=%s path=%s", row["id"], dest_path)
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
                        "id": row["id"],
                    },
                )
                db.commit()
                logger.exception("Failed to stage attachment %s: %s", row["id"], exc)
                raise AttachmentStageError(f"failed_to_stage_attachment:{row['filename']}") from exc

            db.execute(
                text(
                    """
                    UPDATE workflow_run_files
                    SET status = :status, vm_path = :vm_path, error = NULL, updated_at = :updated_at
                    WHERE id = :id
                    """
                ),
                {
                    "status": "ready",
                    "vm_path": dest_path,
                    "updated_at": now,
                    "id": row["id"],
                },
            )
            db.commit()

            manifest.append(
                {
                    "id": row["id"],
                    "workflow_file_id": row.get("workflow_file_id"),
                    "filename": row["filename"],
                    "vm_path": dest_path,
                    "size_bytes": row.get("size_bytes"),
                    "content_type": row.get("content_type"),
                }
            )

        return manifest
    finally:
        db.close()
