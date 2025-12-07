"""add workflow + run tables

Revision ID: add_workflow_entities_001
Revises: add_workspaces_001
Create Date: 2024-12-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "add_workflow_entities_001"
down_revision: Union[str, Sequence[str], None] = "add_workspaces_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create workflow + run related tables."""
    from sqlalchemy import inspect

    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())

    def _has_index(table: str, name: str) -> bool:
        try:
            return any(idx.get("name") == name for idx in inspector.get_indexes(table))
        except Exception:
            return False

    # profiles (Supabase auth.users mirror)
    if "profiles" not in existing_tables:
        op.create_table(
            "profiles",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("name", sa.Text(), nullable=True),
            sa.Column("avatar_url", sa.Text(), nullable=True),
            sa.Column("credits", sa.Integer(), server_default="0", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    if "folders" not in existing_tables:
        op.create_table(
            "folders",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), sa.ForeignKey("profiles.id", ondelete="cascade"), nullable=False),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("position", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    if "folders" in existing_tables and not _has_index("folders", "ix_folders_user_position"):
        op.create_index("ix_folders_user_position", "folders", ["user_id", "position"], unique=False)

    if "workflows" not in existing_tables:
        op.create_table(
            "workflows",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), sa.ForeignKey("profiles.id", ondelete="cascade"), nullable=False),
            sa.Column("folder_id", sa.String(), sa.ForeignKey("folders.id", ondelete="set null"), nullable=True),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("prompt", sa.Text(), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("status", sa.String(), nullable=False, server_default="draft"),
            sa.Column("definition_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), onupdate=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    if "workflows" in existing_tables and not _has_index("workflows", "ix_workflows_user_folder_updated"):
        op.create_index("ix_workflows_user_folder_updated", "workflows", ["user_id", "folder_id", "updated_at"], unique=False)

    if "workflow_runs" not in existing_tables:
        op.create_table(
            "workflow_runs",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("workflow_id", sa.String(), sa.ForeignKey("workflows.id", ondelete="cascade"), nullable=False),
            sa.Column("user_id", sa.String(), sa.ForeignKey("profiles.id", ondelete="cascade"), nullable=False),
            sa.Column("folder_id", sa.String(), nullable=True),
            sa.Column("status", sa.String(), nullable=False, server_default="queued"),
            sa.Column("vm_id", sa.String(), nullable=True),
            sa.Column("claimed_by", sa.String(), nullable=True),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("trigger_source", sa.String(), nullable=True),
            sa.Column("metadata", sa.JSON(), server_default="{}", nullable=False),
            sa.Column("environment", sa.JSON(), server_default="{}", nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), onupdate=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    if "workflow_runs" in existing_tables and not _has_index("workflow_runs", "ix_workflow_runs_user_status_started"):
        op.create_index("ix_workflow_runs_user_status_started", "workflow_runs", ["user_id", "status", "started_at"], unique=False)

    if "run_events" not in existing_tables:
        op.create_table(
            "run_events",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("run_id", sa.String(), sa.ForeignKey("workflow_runs.id", ondelete="cascade"), nullable=False),
            sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.Column("kind", sa.String(), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("payload", sa.JSON(), server_default="{}", nullable=False),
            sa.Column("step_id", sa.String(), nullable=True),
            sa.Column("actor", sa.String(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
    if "run_events" in existing_tables and not _has_index("run_events", "ix_run_events_run_ts"):
        op.create_index("ix_run_events_run_ts", "run_events", ["run_id", "ts"], unique=False)

    if "vm_instances" not in existing_tables:
        op.create_table(
            "vm_instances",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("run_id", sa.String(), sa.ForeignKey("workflow_runs.id", ondelete="cascade"), nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("provider", sa.Text(), nullable=True),
            sa.Column("spec", sa.JSON(), nullable=True),
            sa.Column("endpoint", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.Column("terminated_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
    if "vm_instances" in existing_tables and not _has_index("vm_instances", "ix_vm_instances_run_id"):
        op.create_index("ix_vm_instances_run_id", "vm_instances", ["run_id"], unique=False)


def downgrade() -> None:
    """Drop workflow + run related tables."""
    op.drop_index("ix_vm_instances_run_id", table_name="vm_instances")
    op.drop_table("vm_instances")

    op.drop_index("ix_run_events_run_ts", table_name="run_events")
    op.drop_table("run_events")

    op.drop_index("ix_workflow_runs_user_status_started", table_name="workflow_runs")
    op.drop_table("workflow_runs")

    op.drop_index("ix_workflows_user_folder_updated", table_name="workflows")
    op.drop_table("workflows")

    op.drop_index("ix_folders_user_position", table_name="folders")
    op.drop_table("folders")

    op.drop_table("profiles")
