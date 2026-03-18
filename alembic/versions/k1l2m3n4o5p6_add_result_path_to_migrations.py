"""add result_path to migrations (MM-78)

Revision ID: k1l2m3n4o5p6
Revises: j0k1l2m3n4o5
Create Date: 2026-03-18

"""
from alembic import op
import sqlalchemy as sa

revision = 'k1l2m3n4o5p6'
down_revision = 'j0k1l2m3n4o5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'migrations',
        sa.Column('result_path', sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('migrations', 'result_path')
