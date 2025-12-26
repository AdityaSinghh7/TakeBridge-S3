from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.db.models import WorkflowFile


def list_for_workflow(db: Session, *, workflow_id: str, user_id: str) -> list[WorkflowFile]:
    return (
        db.execute(
            select(WorkflowFile)
            .where(
                WorkflowFile.workflow_id == workflow_id,
                WorkflowFile.user_id == user_id,
            )
            .order_by(WorkflowFile.created_at.asc())
        )
        .scalars()
        .all()
    )


def load_ready_for_workflow(
    db: Session,
    *,
    workflow_id: str,
    user_id: str,
    file_ids: list[str] | None,
) -> tuple[list[WorkflowFile], list[str]]:
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
        return rows, missing
    return rows, []


def get_for_user(
    db: Session, *, workflow_id: str, user_id: str, file_id: str
) -> WorkflowFile | None:
    return (
        db.execute(
            select(WorkflowFile).where(
                WorkflowFile.id == file_id,
                WorkflowFile.workflow_id == workflow_id,
                WorkflowFile.user_id == user_id,
            )
        )
        .scalars()
        .first()
    )


def create_pending(
    db: Session,
    *,
    file_id: str,
    workflow_id: str,
    user_id: str,
    storage_key: str,
    filename: str,
    content_type: str | None,
    size_bytes: int | None,
    checksum: str | None,
    metadata: dict[str, Any] | None,
) -> WorkflowFile:
    record = WorkflowFile(
        id=file_id,
        workflow_id=workflow_id,
        user_id=user_id,
        source_type="upload",
        storage_key=storage_key,
        filename=filename,
        content_type=content_type,
        size_bytes=size_bytes,
        checksum=checksum,
        status="pending",
        metadata_json=metadata or {},
    )
    db.add(record)
    return record


def finalize(
    db: Session,
    record: WorkflowFile,
    *,
    size_bytes: int,
    checksum: str | None,
    metadata: dict[str, Any] | None,
    content_type: str | None,
) -> WorkflowFile:
    record.size_bytes = size_bytes
    if checksum:
        record.checksum = checksum
    if metadata is not None:
        record.metadata_json = metadata
    if content_type:
        record.content_type = content_type
    record.status = "ready"
    record.updated_at = datetime.now(timezone.utc)
    db.add(record)
    return record


def delete(db: Session, record: WorkflowFile) -> None:
    db.delete(record)


__all__ = [
    "create_pending",
    "delete",
    "finalize",
    "get_for_user",
    "load_ready_for_workflow",
    "list_for_workflow",
]
