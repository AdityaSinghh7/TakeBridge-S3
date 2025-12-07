"""add metadata to workflows if missing

Revision ID: add_workflow_metadata_001
Revises: add_folder_to_runs_001
Create Date: 2024-12-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "add_workflow_metadata_001"
down_revision: Union[str, Sequence[str], None] = "add_folder_to_runs_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add metadata JSON column to workflows if missing."""
    from sqlalchemy import inspect

    bind = op.get_bind()
    inspector = inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("workflows")}
    if "metadata" not in cols:
        op.add_column("workflows", sa.Column("metadata", sa.JSON(), server_default="{}", nullable=False))


def downgrade() -> None:
    """Drop metadata column."""
    from sqlalchemy import inspect

    bind = op.get_bind()
    inspector = inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("workflows")}
    if "metadata" in cols:
        op.drop_column("workflows", "metadata")
