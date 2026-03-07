"""add spotify token

Revision ID: c3d4e5f6a7b8
Revises: a1b2c3d4e5f6
Create Date: 2026-03-07 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user_sessions") as batch_op:
        batch_op.add_column(
            sa.Column("spotify_token", sa.Text(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("user_sessions") as batch_op:
        batch_op.drop_column("spotify_token")
