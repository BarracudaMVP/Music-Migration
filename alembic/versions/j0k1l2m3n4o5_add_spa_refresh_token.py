"""add spa_refresh_token to user_sessions (MM-81)

Revision ID: j0k1l2m3n4o5
Revises: i9j0k1l2m3n4
Create Date: 2026-03-13

"""
from alembic import op
import sqlalchemy as sa

revision = 'j0k1l2m3n4o5'
down_revision = 'i9j0k1l2m3n4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'user_sessions',
        sa.Column('spa_refresh_token', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('user_sessions', 'spa_refresh_token')
