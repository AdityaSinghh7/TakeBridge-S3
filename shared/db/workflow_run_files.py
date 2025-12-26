from __future__ import annotations

import posixpath
import mimetypes
import uuid
from datetime import datetime

from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session

from shared.db.models import WorkflowFile, WorkflowRunFile
from shared.db.sql import execute_text


def list_non_drive_files_for_run(db: Session, *, run_id: str) -> list[RowMapping]:
    return (
        execute_text(
            db,
            """
            SELECT id, workflow_file_id, storage_key, filename, content_type,
                   size_bytes, status, vm_path
            FROM workflow_run_files
            WHERE run_id = :run_id AND (drive_path IS NULL AND source_type != 'drive')
            ORDER BY created_at ASC
            """,
            {"run_id": run_id},
        )
        .mappings()
        .all()
    )


def mark_failed(db: Session, *, run_file_id: str, error: str, updated_at: datetime) -> None:
    execute_text(
        db,
        """
        UPDATE workflow_run_files
        SET status = :status, error = :error, updated_at = :updated_at
        WHERE id = :id
        """,
        {"status": "failed", "error": error, "updated_at": updated_at, "id": run_file_id},
    )


def mark_ready_attachment(db: Session, *, run_file_id: str, vm_path: str, updated_at: datetime) -> None:
    execute_text(
        db,
        """
        UPDATE workflow_run_files
        SET status = :status, vm_path = :vm_path, error = NULL, updated_at = :updated_at
        WHERE id = :id
        """,
        {"status": "ready", "vm_path": vm_path, "updated_at": updated_at, "id": run_file_id},
    )


def list_drive_files_for_run(db: Session, *, run_id: str) -> list[RowMapping]:
    return (
        execute_text(
            db,
            """
            SELECT id, user_id, drive_path, r2_key, storage_key, filename, content_type,
                   size_bytes, checksum, status, vm_path
            FROM workflow_run_files
            WHERE run_id = :run_id AND (drive_path IS NOT NULL OR source_type = 'drive')
            ORDER BY created_at ASC
            """,
            {"run_id": run_id},
        )
        .mappings()
        .all()
    )


def list_drive_files_for_changes(db: Session, *, run_id: str) -> list[RowMapping]:
    return (
        execute_text(
            db,
            """
            SELECT id, user_id, drive_path, r2_key, storage_key, filename,
                   checksum, vm_path, content_type
            FROM workflow_run_files
            WHERE run_id = :run_id AND (drive_path IS NOT NULL OR source_type = 'drive')
            ORDER BY created_at ASC
            """,
            {"run_id": run_id},
        )
        .mappings()
        .all()
    )


def mark_ready_drive(
    db: Session,
    *,
    run_file_id: str,
    status: str,
    vm_path: str,
    size_bytes: int,
    checksum: str,
    content_type: str | None,
    updated_at: datetime,
    r2_key: str,
    drive_path: str,
) -> None:
    execute_text(
        db,
        """
        UPDATE workflow_run_files
        SET status = :status, vm_path = :vm_path, size_bytes = :size_bytes,
            checksum = :checksum, content_type = :content_type, error = NULL,
            updated_at = :updated_at, r2_key = :r2_key, drive_path = :drive_path
        WHERE id = :id
        """,
        {
            "status": status,
            "vm_path": vm_path,
            "size_bytes": size_bytes,
            "checksum": checksum,
            "content_type": content_type,
            "updated_at": updated_at,
            "r2_key": r2_key,
            "drive_path": drive_path,
            "id": run_file_id,
        },
    )


def get_drive_file_row(
    db: Session,
    *,
    run_id: str,
    user_id: str,
    drive_path: str,
) -> RowMapping | None:
    return (
        execute_text(
            db,
            """
            SELECT drive_path, vm_path, content_type
            FROM workflow_run_files
            WHERE run_id = :run_id AND user_id = :user_id AND drive_path = :drive_path
            """,
            {"run_id": run_id, "user_id": user_id, "drive_path": drive_path},
        )
        .mappings()
        .first()
    )


def build_pending_for_workflow_files(
    *,
    run_id: str,
    user_id: str,
    workflow_files: list[WorkflowFile],
) -> list[WorkflowRunFile]:
    records: list[WorkflowRunFile] = []
    for wf_file in workflow_files:
        records.append(
            WorkflowRunFile(
                id=str(uuid.uuid4()),
                run_id=run_id,
                workflow_file_id=wf_file.id,
                user_id=user_id,
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
    return records


def build_pending_for_drive_paths(
    *,
    run_id: str,
    user_id: str,
    drive_paths: list[str],
    r2_key_by_path: dict[str, str],
) -> list[WorkflowRunFile]:
    records: list[WorkflowRunFile] = []
    for drive_path in drive_paths:
        r2_key = r2_key_by_path.get(drive_path)
        if not r2_key:
            continue
        records.append(
            WorkflowRunFile(
                id=str(uuid.uuid4()),
                run_id=run_id,
                workflow_file_id=None,
                user_id=user_id,
                source_type="drive",
                storage_key=r2_key,
                r2_key=r2_key,
                drive_path=drive_path,
                filename=posixpath.basename(drive_path) or "file",
                content_type=None,
                size_bytes=None,
                checksum=None,
                status="pending",
                metadata_json={},
            )
        )
    return records


def build_pending_for_drive_items(
    *,
    run_id: str,
    user_id: str,
    items: list[dict[str, object]],
) -> list[WorkflowRunFile]:
    records: list[WorkflowRunFile] = []
    for item in items:
        drive_path = item.get("drive_path")
        r2_key = item.get("r2_key")
        if not isinstance(drive_path, str) or not drive_path:
            continue
        if not isinstance(r2_key, str) or not r2_key:
            continue
        content_type = None
        raw_content_type = item.get("content_type")
        if isinstance(raw_content_type, str) and raw_content_type:
            content_type = raw_content_type
        if not content_type:
            content_type = mimetypes.guess_type(drive_path)[0]
        records.append(
            WorkflowRunFile(
                id=str(uuid.uuid4()),
                run_id=run_id,
                workflow_file_id=None,
                user_id=user_id,
                source_type="drive",
                storage_key=r2_key,
                r2_key=r2_key,
                drive_path=drive_path,
                filename=posixpath.basename(drive_path) or "file",
                content_type=content_type,
                size_bytes=item.get("size_bytes"),
                checksum=None,
                status="pending",
                metadata_json={},
            )
        )
    return records


def add_many(db: Session, records: list[WorkflowRunFile]) -> None:
    for record in records:
        db.add(record)


__all__ = [
    "get_drive_file_row",
    "add_many",
    "build_pending_for_drive_paths",
    "build_pending_for_drive_items",
    "build_pending_for_workflow_files",
    "list_drive_files_for_changes",
    "list_drive_files_for_run",
    "list_non_drive_files_for_run",
    "mark_failed",
    "mark_ready_attachment",
    "mark_ready_drive",
]
