"""
core.db — SQLAlchemy 2.x async DB layer.
Реэкспортирует все публичные функции из crud.py для обратной совместимости.
"""
from core.db.crud import (
    init_db,
    create_migration,
    update_migration,
    get_migration,
    bulk_insert_tracks,
    get_pending_tracks,
    update_track,
    get_track_stats,
    get_liked_sc_tracks,
    create_playlist_record,
    update_playlist,
    get_pending_playlists,
    bulk_insert_artists,
    get_pending_artists,
    update_artist,
    get_artist_stats,
    save_user_session,
    load_user_session,
    delete_user_session,
)

__all__ = [
    "init_db",
    "create_migration",
    "update_migration",
    "get_migration",
    "bulk_insert_tracks",
    "get_pending_tracks",
    "update_track",
    "get_track_stats",
    "get_liked_sc_tracks",
    "create_playlist_record",
    "update_playlist",
    "get_pending_playlists",
    "bulk_insert_artists",
    "get_pending_artists",
    "update_artist",
    "get_artist_stats",
    "save_user_session",
    "load_user_session",
    "delete_user_session",
]
