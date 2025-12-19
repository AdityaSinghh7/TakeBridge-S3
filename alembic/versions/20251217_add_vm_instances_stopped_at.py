"""add stopped_at to vm_instances

Revision ID: add_vm_instances_stopped_at_001
Revises: add_workflow_run_artifacts_001
Create Date: 2025-12-17
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "add_vm_instances_stopped_at_001"
down_revision: Union[str, Sequence[str], None] = "add_workflow_run_artifacts_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add stopped_at column to vm_instances when absent."""
    from sqlalchemy import inspect

    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "vm_instances" not in tables:
        return
    cols = {c["name"] for c in inspector.get_columns("vm_instances")}
    if "stopped_at" not in cols:
        op.add_column(
            "vm_instances",
            sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    """Drop stopped_at column."""
    from sqlalchemy import inspect

    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "vm_instances" not in tables:
        return
    cols = {c["name"] for c in inspector.get_columns("vm_instances")}
    if "stopped_at" in cols:
        op.drop_column("vm_instances", "stopped_at")

