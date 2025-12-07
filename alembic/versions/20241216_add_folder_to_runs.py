"""add folder_id to workflow_runs if missing

Revision ID: add_folder_to_runs_001
Revises: add_workflow_entities_001
Create Date: 2024-12-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "add_folder_to_runs_001"
down_revision: Union[str, Sequence[str], None] = "add_workflow_entities_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add folder_id to workflow_runs when absent."""
    from sqlalchemy import inspect

    bind = op.get_bind()
    inspector = inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("workflow_runs")}
    if "folder_id" not in cols:
        op.add_column("workflow_runs", sa.Column("folder_id", sa.String(), nullable=True))


def downgrade() -> None:
    """Drop folder_id column."""
    from sqlalchemy import inspect

    bind = op.get_bind()
    inspector = inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("workflow_runs")}
    if "folder_id" in cols:
        op.drop_column("workflow_runs", "folder_id")
