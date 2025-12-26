from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.db.models import WorkflowRunArtifact
from shared.db.sql import execute_text


def delete_for_run_filename(db: Session, *, run_id: str, filename: str) -> None:
    execute_text(
        db,
        """
        DELETE FROM workflow_run_artifacts
        WHERE run_id = :run_id AND filename = :filename
        """,
        {"run_id": run_id, "filename": filename},
    )


def list_for_run(db: Session, *, run_id: str) -> list[WorkflowRunArtifact]:
    return (
        db.execute(
            select(WorkflowRunArtifact)
            .where(WorkflowRunArtifact.run_id == run_id)
            .order_by(WorkflowRunArtifact.created_at.asc())
        )
        .scalars()
        .all()
    )


def add(db: Session, artifact: WorkflowRunArtifact) -> None:
    db.add(artifact)


__all__ = ["add", "delete_for_run_filename", "list_for_run"]
