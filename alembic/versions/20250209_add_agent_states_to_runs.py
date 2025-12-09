"""add agent_states to workflow_runs

Revision ID: add_agent_states_001
Revises: add_workflow_metadata_001
Create Date: 2025-02-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "add_agent_states_001"
down_revision: Union[str, Sequence[str], None] = "add_workflow_metadata_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add agent_states snapshot column to workflow_runs."""
    from sqlalchemy import inspect, text

    bind = op.get_bind()
    inspector = inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("workflow_runs")}
    is_pg = bind.dialect.name == "postgresql"
    json_default = sa.text("'{}'::jsonb") if is_pg else "{}"

    if "agent_states" not in cols:
        op.add_column(
            "workflow_runs",
            sa.Column(
                "agent_states",
                sa.JSON(),
                nullable=False,
                server_default=json_default,
            ),
        )

    if "agent_states_updated_at" not in cols:
        op.add_column(
            "workflow_runs",
            sa.Column("agent_states_updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        # Backfill to current updated_at to avoid nulls for existing rows
        op.execute(
            text(
                """
                UPDATE workflow_runs
                SET agent_states_updated_at = updated_at
                WHERE agent_states_updated_at IS NULL
                """
            )
        )


def downgrade() -> None:
    """Drop agent_states columns."""
    from sqlalchemy import inspect

    bind = op.get_bind()
    inspector = inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("workflow_runs")}

    if "agent_states_updated_at" in cols:
        op.drop_column("workflow_runs", "agent_states_updated_at")
    if "agent_states" in cols:
        op.drop_column("workflow_runs", "agent_states")
