from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.db.models import WorkflowRunDriveChange
from shared.db.sql import execute_text


def mark_committed(
    db: Session,
    *,
    run_id: str,
    path: str,
    committed_at,
    status: str = "committed",
) -> None:
    execute_text(
        db,
        """
        UPDATE workflow_run_drive_changes
        SET status = :status, committed_at = :committed_at, updated_at = :updated_at
        WHERE run_id = :run_id AND path = :path
        """,
        {
            "status": status,
            "committed_at": committed_at,
            "updated_at": committed_at,
            "run_id": run_id,
            "path": path,
        },
    )


def mark_failed(
    db: Session,
    *,
    run_id: str,
    path: str,
    error: str,
    updated_at,
    status: str = "failed",
) -> None:
    execute_text(
        db,
        """
        UPDATE workflow_run_drive_changes
        SET status = :status, updated_at = :updated_at
        WHERE run_id = :run_id AND path = :path
        """,
        {
            "status": status,
            "updated_at": updated_at,
            "run_id": run_id,
            "path": path,
        },
    )


def delete_for_run_path(db: Session, *, run_id: str, path: str) -> None:
    execute_text(
        db,
        """
        DELETE FROM workflow_run_drive_changes
        WHERE run_id = :run_id AND path = :path
        """,
        {"run_id": run_id, "path": path},
    )


def list_for_run_user(
    db: Session, *, run_id: str, user_id: str
) -> list[WorkflowRunDriveChange]:
    user_id = str(user_id)
    return (
        db.execute(
            select(WorkflowRunDriveChange)
            .where(
                WorkflowRunDriveChange.run_id == run_id,
                WorkflowRunDriveChange.user_id == user_id,
            )
            .order_by(WorkflowRunDriveChange.created_at.asc())
        )
        .scalars()
        .all()
    )


def add(db: Session, change: WorkflowRunDriveChange) -> None:
    db.add(change)


__all__ = ["add", "delete_for_run_path", "list_for_run_user", "mark_committed", "mark_failed"]
