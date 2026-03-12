"""rename file_csv to file in migrations from_service/to_service

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Create Date: 2026-03-12

"""
from alembic import op

revision = 'i9j0k1l2m3n4'
down_revision = 'h8i9j0k1l2m3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE migrations SET from_service = 'file' WHERE from_service = 'file_csv'")
    op.execute("UPDATE migrations SET to_service = 'file' WHERE to_service = 'file_csv'")


def downgrade() -> None:
    op.execute("UPDATE migrations SET from_service = 'file_csv' WHERE from_service = 'file'")
    op.execute("UPDATE migrations SET to_service = 'file_csv' WHERE to_service = 'file'")
