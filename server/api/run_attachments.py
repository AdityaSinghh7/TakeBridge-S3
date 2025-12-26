from __future__ import annotations

import os
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from shared.db.engine import SessionLocal
from shared.db import workflow_run_files
from shared.storage import get_attachment_storage, AttachmentStorageError
from server.api.controller_client import VMControllerClient

logger = logging.getLogger(__name__)

ATTACHMENT_VM_BASE_PATH = os.path.expanduser(os.getenv("ATTACHMENTS_VM_BASE_PATH", "/home/user/context"))
DOWNLOAD_TIMEOUT = int(os.getenv("ATTACHMENTS_DOWNLOAD_TIMEOUT", "300"))


class AttachmentStageError(RuntimeError):
    """Raised when attachments cannot be staged on the run VM."""


def _default_vm_path(run_id: str, filename: str) -> str:
    safe_name = os.path.basename(filename) or "file"
    return os.path.join(ATTACHMENT_VM_BASE_PATH, safe_name)


def _transfer_to_vm(controller: VMControllerClient, dest_path: str, download_url: str) -> None:
    logger.info("[attachments] downloading to VM path=%s", dest_path)
    controller.download_file(download_url, dest_path, timeout=DOWNLOAD_TIMEOUT)
    logger.info("[attachments] download complete path=%s", dest_path)


def stage_files_for_run(run_id: str, workspace: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Download and upload workflow files for a run into its VM workspace."""
    controller_url = workspace.get("controller_base_url")
    if not controller_url:
        raise AttachmentStageError("workspace missing controller_base_url")

    db = SessionLocal()
    try:
        rows = workflow_run_files.list_non_drive_files_for_run(db, run_id=run_id)
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
                workflow_run_files.mark_failed(
                    db,
                    run_file_id=row["id"],
                    error=str(exc),
                    updated_at=now,
                )
                db.commit()
                logger.exception("Failed to stage attachment %s: %s", row["id"], exc)
                raise AttachmentStageError(f"failed_to_stage_attachment:{row['filename']}") from exc

            workflow_run_files.mark_ready_attachment(
                db,
                run_file_id=row["id"],
                vm_path=dest_path,
                updated_at=now,
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
