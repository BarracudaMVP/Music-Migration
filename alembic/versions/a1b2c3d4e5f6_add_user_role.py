"""add user role

Revision ID: a1b2c3d4e5f6
Revises: 7bf3e87e8eca
Create Date: 2026-03-06 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "7bf3e87e8eca"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user_sessions") as batch_op:
        batch_op.add_column(
            sa.Column("role", sa.String(), nullable=False, server_default="user")
        )


def downgrade() -> None:
    with op.batch_alter_table("user_sessions") as batch_op:
        batch_op.drop_column("role")
