"""add from_service and to_service to migrations

Revision ID: g7h8i9j0k1l2
Revises: f6a7b8c9d0e1
Create Date: 2026-03-11

"""
from alembic import op
import sqlalchemy as sa

revision = 'g7h8i9j0k1l2'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('migrations', sa.Column('from_service', sa.String(), nullable=True))
    op.add_column('migrations', sa.Column('to_service', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('migrations', 'to_service')
    op.drop_column('migrations', 'from_service')
