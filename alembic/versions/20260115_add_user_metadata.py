"""add metadata to users

Revision ID: add_user_metadata_001
Revises: add_drive_storage_001
Create Date: 2026-01-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "add_user_metadata_001"
down_revision: Union[str, Sequence[str], None] = "add_drive_storage_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add metadata JSON column to users when absent."""
    from sqlalchemy import inspect

    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "users" not in tables:
        return
    cols = {c["name"] for c in inspector.get_columns("users")}
    is_pg = bind.dialect.name == "postgresql"
    json_default = sa.text("'{}'::jsonb") if is_pg else "{}"
    if "metadata" not in cols:
        op.add_column(
            "users",
            sa.Column("metadata", sa.JSON(), nullable=False, server_default=json_default),
        )


def downgrade() -> None:
    """Drop metadata column."""
    from sqlalchemy import inspect

    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "users" not in tables:
        return
    cols = {c["name"] for c in inspector.get_columns("users")}
    if "metadata" in cols:
        op.drop_column("users", "metadata")
