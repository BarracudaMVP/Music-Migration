"""
Integration tests for core/db CRUD operations.

Uses an isolated in-memory SQLite engine with StaticPool so all async
sessions share the same connection (required for in-memory SQLite).
"""
import pytest
from unittest.mock import patch
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from core.db.models import Base


@pytest.fixture
async def db():
    """Per-test isolated in-memory SQLite with all tables created."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    with patch("core.db.crud.AsyncSessionLocal", session_factory), \
         patch("core.db.crud.engine", engine):
        yield engine

    await engine.dispose()


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_migration_returns_id(db):
    from core.db import create_migration
    mid = await create_migration("user_1")
    assert isinstance(mid, int)
    assert mid > 0


@pytest.mark.asyncio
async def test_get_migration_default_status(db):
    from core.db import create_migration, get_migration
    mid = await create_migration("user_2")
    result = await get_migration(mid)
    assert result is not None
    assert result["user_id"] == "user_2"
    assert result["status"] == "pending"


@pytest.mark.asyncio
async def test_update_migration_status(db):
    from core.db import create_migration, update_migration, get_migration
    mid = await create_migration("user_3")
    await update_migration(mid, status="running")
    result = await get_migration(mid)
    assert result["status"] == "running"


@pytest.mark.asyncio
async def test_get_migration_nonexistent_returns_none(db):
    from core.db import get_migration
    assert await get_migration(99999) is None


@pytest.mark.asyncio
async def test_user_migration_number_increments_per_user(db):
    """Each user gets their own sequential numbering starting from 1."""
    from core.db import create_migration, get_migration
    mid1 = await create_migration("user_a")
    mid2 = await create_migration("user_a")
    mid3 = await create_migration("user_a")
    mid_other = await create_migration("user_b")

    r1 = await get_migration(mid1)
    r2 = await get_migration(mid2)
    r3 = await get_migration(mid3)
    r_other = await get_migration(mid_other)

    assert r1["user_migration_number"] == 1
    assert r2["user_migration_number"] == 2
    assert r3["user_migration_number"] == 3
    # user_b has their own counter starting at 1
    assert r_other["user_migration_number"] == 1


# ---------------------------------------------------------------------------
# Tracks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bulk_insert_and_get_pending_tracks(db):
    from core.db import create_migration, bulk_insert_tracks, get_pending_tracks
    mid = await create_migration("user_4")
    tracks = [
        {"ym_id": "t1", "ym_artist": "Radiohead", "ym_title": "Creep", "ym_album": "Pablo Honey"},
        {"ym_id": "t2", "ym_artist": "Beatles", "ym_title": "Hey Jude", "ym_album": ""},
    ]
    await bulk_insert_tracks(mid, tracks)
    pending = await get_pending_tracks(mid)
    assert len(pending) == 2
    titles = {t["ym_title"] for t in pending}
    assert titles == {"Creep", "Hey Jude"}


@pytest.mark.asyncio
async def test_bulk_insert_idempotent(db):
    """Inserting same tracks twice should not duplicate."""
    from core.db import create_migration, bulk_insert_tracks, get_pending_tracks
    mid = await create_migration("user_5")
    tracks = [{"ym_id": "t1", "ym_artist": "A", "ym_title": "B"}]
    await bulk_insert_tracks(mid, tracks)
    await bulk_insert_tracks(mid, tracks)
    pending = await get_pending_tracks(mid)
    assert len(pending) == 1


@pytest.mark.asyncio
async def test_update_track_status(db):
    from core.db import create_migration, bulk_insert_tracks, get_pending_tracks, update_track, get_track_stats
    mid = await create_migration("user_6")
    await bulk_insert_tracks(mid, [{"ym_id": "t1", "ym_artist": "A", "ym_title": "B"}])
    pending = await get_pending_tracks(mid)
    track_id = pending[0]["id"]

    await update_track(track_id, status="liked", sc_id=42, sc_url="http://sc/42", match_score=90.0)

    stats = await get_track_stats(mid)
    assert stats.get("liked") == 1
    assert "pending" not in stats


@pytest.mark.asyncio
async def test_get_track_stats_counts_by_status(db):
    from core.db import create_migration, bulk_insert_tracks, get_pending_tracks, update_track, get_track_stats
    mid = await create_migration("user_7")
    tracks = [{"ym_id": f"t{i}", "ym_artist": "A", "ym_title": f"T{i}"} for i in range(4)]
    await bulk_insert_tracks(mid, tracks)
    pending = await get_pending_tracks(mid)

    await update_track(pending[0]["id"], status="liked")
    await update_track(pending[1]["id"], status="liked")
    await update_track(pending[2]["id"], status="not_found")

    stats = await get_track_stats(mid)
    assert stats["liked"] == 2
    assert stats["not_found"] == 1
    assert stats["pending"] == 1


@pytest.mark.asyncio
async def test_get_tracks_page_pagination(db):
    from core.db import create_migration, bulk_insert_tracks, get_tracks_page
    mid = await create_migration("user_8")
    tracks = [{"ym_id": f"t{i}", "ym_artist": "A", "ym_title": f"T{i}"} for i in range(5)]
    await bulk_insert_tracks(mid, tracks)

    page1, total = await get_tracks_page(mid, page=1, per_page=3)
    assert total == 5
    assert len(page1) == 3

    page2, total2 = await get_tracks_page(mid, page=2, per_page=3)
    assert total2 == 5
    assert len(page2) == 2


@pytest.mark.asyncio
async def test_get_tracks_page_status_filter(db):
    from core.db import create_migration, bulk_insert_tracks, get_pending_tracks, update_track, get_tracks_page
    mid = await create_migration("user_9")
    tracks = [{"ym_id": f"t{i}", "ym_artist": "A", "ym_title": f"T{i}"} for i in range(3)]
    await bulk_insert_tracks(mid, tracks)
    pending = await get_pending_tracks(mid)
    await update_track(pending[0]["id"], status="liked")

    liked_page, liked_total = await get_tracks_page(mid, status="liked")
    assert liked_total == 1

    pending_page, pending_total = await get_tracks_page(mid, status="pending")
    assert pending_total == 2


# ---------------------------------------------------------------------------
# User sessions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_save_and_load_user_session(db):
    from core.db import save_user_session, load_user_session
    await save_user_session("web_abc", "ym_token_123", "sc_token_456")
    session = await load_user_session("web_abc")
    assert session is not None
    assert session["yandex_token"] == "ym_token_123"
    assert session["soundcloud_token"] == "sc_token_456"
    assert session["role"] == "user"


@pytest.mark.asyncio
async def test_load_nonexistent_session_returns_none(db):
    from core.db import load_user_session
    assert await load_user_session("nonexistent_user") is None


@pytest.mark.asyncio
async def test_save_session_upserts(db):
    """Saving same user_id twice updates the record."""
    from core.db import save_user_session, load_user_session
    await save_user_session("web_upd", "old_ym", "old_sc")
    await save_user_session("web_upd", "new_ym", "new_sc")
    session = await load_user_session("web_upd")
    assert session["yandex_token"] == "new_ym"
    assert session["soundcloud_token"] == "new_sc"


@pytest.mark.asyncio
async def test_delete_user_session(db):
    from core.db import save_user_session, load_user_session, delete_user_session
    await save_user_session("web_del", "ym", "sc")
    await delete_user_session("web_del")
    assert await load_user_session("web_del") is None


@pytest.mark.asyncio
async def test_set_user_role(db):
    from core.db import save_user_session, load_user_session, set_user_role
    await save_user_session("web_role", "ym", "sc")
    await set_user_role("web_role", "admin")
    session = await load_user_session("web_role")
    assert session["role"] == "admin"


# ---------------------------------------------------------------------------
# MM-90: get_track_stats_batch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_track_stats_batch_returns_per_migration(db):
    from core.db.crud import get_track_stats_batch, bulk_insert_tracks, create_migration

    mid1 = await create_migration("batch_u1")
    mid2 = await create_migration("batch_u2")
    await bulk_insert_tracks(mid1, [
        {"ym_id": "a1", "ym_artist": "A", "ym_title": "T1", "ym_album": ""},
        {"ym_id": "a2", "ym_artist": "A", "ym_title": "T2", "ym_album": ""},
    ])
    await bulk_insert_tracks(mid2, [
        {"ym_id": "b1", "ym_artist": "B", "ym_title": "T3", "ym_album": ""},
    ])

    result = await get_track_stats_batch([mid1, mid2])
    assert mid1 in result
    assert mid2 in result
    assert result[mid1].get("pending", 0) == 2
    assert result[mid2].get("pending", 0) == 1


@pytest.mark.asyncio
async def test_get_track_stats_batch_empty(db):
    from core.db.crud import get_track_stats_batch
    result = await get_track_stats_batch([])
    assert result == {}


# ---------------------------------------------------------------------------
# MM-93: clear_service_token
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_clear_service_token_spotify(db):
    from core.db.crud import save_spotify_token, load_user_session, clear_service_token

    await save_spotify_token("u_clr", "tok123", refresh_token="ref456")
    session = await load_user_session("u_clr")
    assert session["spotify_token"] == "tok123"

    await clear_service_token("u_clr", "spotify")
    session = await load_user_session("u_clr")
    assert not session["spotify_token"]
    assert session["spotify_refresh_token"] is None


@pytest.mark.asyncio
async def test_clear_service_token_yandex(db):
    from core.db.crud import save_yandex_token, load_user_session, clear_service_token

    await save_yandex_token("u_ym", "ym_tok")
    session = await load_user_session("u_ym")
    assert session["yandex_token"] == "ym_tok"

    await clear_service_token("u_ym", "yandex_music")
    session = await load_user_session("u_ym")
    assert not session["yandex_token"]


@pytest.mark.asyncio
async def test_clear_service_token_unknown_service(db):
    """Unknown service should be a no-op (not raise)."""
    from core.db.crud import clear_service_token
    await clear_service_token("u_x", "unknown_service")  # must not raise
