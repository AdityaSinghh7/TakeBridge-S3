"""add drive storage columns and change tracking

Revision ID: add_drive_storage_001
Revises: add_vm_instances_stopped_at_001
Create Date: 2025-12-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "add_drive_storage_001"
down_revision: Union[str, Sequence[str], None] = "add_vm_instances_stopped_at_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from sqlalchemy import inspect

    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    def _has_index(table: str, name: str) -> bool:
        try:
            return any(idx.get("name") == name for idx in inspector.get_indexes(table))
        except Exception:
            return False

    if "workflow_run_files" in tables:
        cols = {c["name"] for c in inspector.get_columns("workflow_run_files")}
        if "drive_path" not in cols:
            op.add_column("workflow_run_files", sa.Column("drive_path", sa.Text(), nullable=True))
        if "r2_key" not in cols:
            op.add_column("workflow_run_files", sa.Column("r2_key", sa.Text(), nullable=True))

    if "workflow_run_drive_changes" not in tables:
        op.create_table(
            "workflow_run_drive_changes",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("run_id", sa.String(length=64), nullable=False),
            sa.Column("user_id", sa.String(length=64), nullable=False),
            sa.Column("path", sa.Text(), nullable=False),
            sa.Column("r2_key", sa.Text(), nullable=False),
            sa.Column("baseline_hash", sa.String(length=128), nullable=True),
            sa.Column("new_hash", sa.String(length=128), nullable=True),
            sa.Column("size_bytes", sa.BigInteger(), nullable=True),
            sa.Column("content_type", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        tables.add("workflow_run_drive_changes")

    if "workflow_run_drive_changes" in tables and not _has_index(
        "workflow_run_drive_changes",
        "ix_workflow_run_drive_changes_run_id",
    ):
        op.create_index(
            "ix_workflow_run_drive_changes_run_id",
            "workflow_run_drive_changes",
            ["run_id"],
        )
    if "workflow_run_drive_changes" in tables and not _has_index(
        "workflow_run_drive_changes",
        "ix_workflow_run_drive_changes_user_id",
    ):
        op.create_index(
            "ix_workflow_run_drive_changes_user_id",
            "workflow_run_drive_changes",
            ["user_id"],
        )


def downgrade() -> None:
    from sqlalchemy import inspect

    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "workflow_run_drive_changes" in tables:
        op.drop_table("workflow_run_drive_changes")

    if "workflow_run_files" in tables:
        cols = {c["name"] for c in inspector.get_columns("workflow_run_files")}
        if "r2_key" in cols:
            op.drop_column("workflow_run_files", "r2_key")
        if "drive_path" in cols:
            op.drop_column("workflow_run_files", "drive_path")
