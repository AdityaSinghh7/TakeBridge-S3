"""add workspaces table

Revision ID: add_workspaces_001
Revises: df7656705064
Create Date: 2025-11-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_workspaces_001'
down_revision: Union[str, Sequence[str], None] = 'df7656705064'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create workspaces table."""
    # Check if table already exists
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()
    
    if 'workspaces' not in tables:
        op.create_table(
            'workspaces',
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('user_id', sa.String(), nullable=False),
            sa.Column('status', sa.String(), nullable=True, server_default='running'),
            sa.Column('controller_base_url', sa.String(), nullable=False),
            sa.Column('vnc_url', sa.String(), nullable=True),
            sa.Column('vm_instance_id', sa.String(), nullable=True),
            sa.Column('cloud_region', sa.String(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('last_used_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
            sa.PrimaryKeyConstraint('id')
        )
    
    # Check if index exists before creating
    indexes = [idx['name'] for idx in inspector.get_indexes('workspaces')] if 'workspaces' in tables else []
    if 'ix_workspaces_user_id' not in indexes:
        op.create_index(op.f('ix_workspaces_user_id'), 'workspaces', ['user_id'], unique=False)


def downgrade() -> None:
    """Drop workspaces table."""
    op.drop_index(op.f('ix_workspaces_user_id'), table_name='workspaces')
    op.drop_table('workspaces')
