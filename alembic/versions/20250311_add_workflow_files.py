"""create workflow file tables

Revision ID: add_workflow_files_001
Revises: add_agent_states_001
Create Date: 2025-03-11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "add_workflow_files_001"
down_revision: Union[str, Sequence[str], None] = "add_agent_states_001"
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

    if "workflow_files" not in tables:
        op.create_table(
            "workflow_files",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("workflow_id", sa.String(length=64), nullable=False),
            sa.Column("user_id", sa.String(length=64), nullable=False),
            sa.Column("source_type", sa.String(length=32), nullable=False, server_default="upload"),
            sa.Column("storage_key", sa.Text(), nullable=False),
            sa.Column("filename", sa.Text(), nullable=False),
            sa.Column("content_type", sa.Text(), nullable=True),
            sa.Column("size_bytes", sa.BigInteger(), nullable=True),
            sa.Column("checksum", sa.String(length=128), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        tables.add("workflow_files")

    if "workflow_files" in tables and not _has_index("workflow_files", "ix_workflow_files_workflow_id"):
        op.create_index("ix_workflow_files_workflow_id", "workflow_files", ["workflow_id"])
    if "workflow_files" in tables and not _has_index("workflow_files", "ix_workflow_files_user_id"):
        op.create_index("ix_workflow_files_user_id", "workflow_files", ["user_id"])

    if "workflow_run_files" not in tables:
        op.create_table(
            "workflow_run_files",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("run_id", sa.String(length=64), nullable=False),
            sa.Column(
                "workflow_file_id",
                sa.String(length=64),
                sa.ForeignKey("workflow_files.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("user_id", sa.String(length=64), nullable=False),
            sa.Column("source_type", sa.String(length=32), nullable=False, server_default="upload"),
            sa.Column("storage_key", sa.Text(), nullable=False),
            sa.Column("filename", sa.Text(), nullable=False),
            sa.Column("content_type", sa.Text(), nullable=True),
            sa.Column("size_bytes", sa.BigInteger(), nullable=True),
            sa.Column("checksum", sa.String(length=128), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("vm_path", sa.Text(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        tables.add("workflow_run_files")

    if "workflow_run_files" in tables and not _has_index("workflow_run_files", "ix_workflow_run_files_run_id"):
        op.create_index("ix_workflow_run_files_run_id", "workflow_run_files", ["run_id"])
    if "workflow_run_files" in tables and not _has_index("workflow_run_files", "ix_workflow_run_files_user_id"):
        op.create_index("ix_workflow_run_files_user_id", "workflow_run_files", ["user_id"])


def downgrade() -> None:
    from sqlalchemy import inspect

    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "workflow_run_files" in tables:
        op.drop_table("workflow_run_files")
    if "workflow_files" in tables:
        op.drop_table("workflow_files")
