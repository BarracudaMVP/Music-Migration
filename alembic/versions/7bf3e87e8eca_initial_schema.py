"""initial_schema

Revision ID: 7bf3e87e8eca
Revises: 
Create Date: 2026-03-05 17:42:32.315926

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7bf3e87e8eca'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'user_sessions',
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('yandex_token', sa.Text(), nullable=False),
        sa.Column('soundcloud_token', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('user_id'),
    )
    op.create_table(
        'migrations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('soundcloud_user_id', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('status', sa.String(), server_default='pending', nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'tracks',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('migration_id', sa.Integer(), sa.ForeignKey('migrations.id'), nullable=False),
        sa.Column('ym_id', sa.String(), nullable=False),
        sa.Column('ym_artist', sa.String(), nullable=False),
        sa.Column('ym_title', sa.String(), nullable=False),
        sa.Column('ym_album', sa.String(), server_default='', nullable=False),
        sa.Column('sc_id', sa.BigInteger(), nullable=True),
        sa.Column('sc_url', sa.Text(), nullable=True),
        sa.Column('match_score', sa.Float(), nullable=True),
        sa.Column('status', sa.String(), server_default='pending', nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('migration_id', 'ym_id'),
    )
    op.create_table(
        'playlists',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('migration_id', sa.Integer(), sa.ForeignKey('migrations.id'), nullable=False),
        sa.Column('ym_kind', sa.Integer(), nullable=False),
        sa.Column('ym_title', sa.String(), nullable=False),
        sa.Column('sc_playlist_id', sa.BigInteger(), nullable=True),
        sa.Column('status', sa.String(), server_default='pending', nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('migration_id', 'ym_kind'),
    )
    op.create_table(
        'playlist_tracks',
        sa.Column('playlist_id', sa.Integer(), sa.ForeignKey('playlists.id'), nullable=False),
        sa.Column('ym_track_id', sa.String(), nullable=False),
        sa.Column('sc_track_id', sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint('playlist_id', 'ym_track_id'),
    )
    op.create_table(
        'artists',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('migration_id', sa.Integer(), sa.ForeignKey('migrations.id'), nullable=False),
        sa.Column('ym_name', sa.String(), nullable=False),
        sa.Column('sc_user_id', sa.BigInteger(), nullable=True),
        sa.Column('sc_username', sa.String(), nullable=True),
        sa.Column('match_score', sa.Float(), nullable=True),
        sa.Column('status', sa.String(), server_default='pending', nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('migration_id', 'ym_name'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('artists')
    op.drop_table('playlist_tracks')
    op.drop_table('playlists')
    op.drop_table('tracks')
    op.drop_table('migrations')
    op.drop_table('user_sessions')
