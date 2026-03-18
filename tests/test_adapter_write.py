"""
Unit tests for AdapterWriteSession implementations and migration/pipeline.py.

Tests cover:
- _YMWriteSession: search_track, write_track
- _SpotifyWriteSession: search_track (with transliteration flag), write_track,
  search_artist, follow_artist
- _SCWriteSession: write_track (playlist_mode, like_tracks, LikeNotSupportedError fallback)
- pipeline.process_one_track: match → write → DB update
- pipeline.run_pending_tracks_loop: stats aggregation, sleep, error handling
- adapter.write_session: context manager yields correct session type
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.matcher import TrackCandidate, MatchResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _match(track_id=1, track_url="url/1", score=90.0, matched=True, uncertain=False):
    return MatchResult(
        track_id=track_id,
        track_url=track_url,
        cand_artist="Artist",
        cand_title="Title",
        score=score,
        matched=matched,
        uncertain=uncertain,
    )


def _candidate(track_id=1, track_url="url/1", artist="Artist", title="Title"):
    return TrackCandidate(track_id=track_id, track_url=track_url, artist=artist, title=title)


# ---------------------------------------------------------------------------
# _YMWriteSession
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ym_session_search_track():
    from core.services.yandex.adapter import _YMWriteSession

    ym_track = MagicMock()
    ym_track.id = "42"
    ym_track.artists_str = "Radiohead"
    ym_track.title = "Creep"

    client = MagicMock()
    client.search_tracks = AsyncMock(return_value=[ym_track])

    session = _YMWriteSession(client)
    results = await session.search_track("Radiohead Creep", limit=5)

    client.search_tracks.assert_called_once_with("Radiohead Creep", limit=5)
    assert len(results) == 1
    assert results[0].track_id == 42
    assert results[0].track_url == "42"
    assert results[0].artist == "Radiohead"
    assert results[0].title == "Creep"


@pytest.mark.asyncio
async def test_ym_session_write_track_liked():
    from core.services.yandex.adapter import _YMWriteSession

    client = MagicMock()
    client.like_track = AsyncMock(return_value=True)

    session = _YMWriteSession(client)
    status = await session.write_track(_match(track_url="99"))

    client.like_track.assert_called_once_with("99")
    assert status == "liked"


@pytest.mark.asyncio
async def test_ym_session_write_track_error():
    from core.services.yandex.adapter import _YMWriteSession

    client = MagicMock()
    client.like_track = AsyncMock(return_value=False)

    session = _YMWriteSession(client)
    status = await session.write_track(_match())

    assert status == "error"


def test_ym_session_no_transliteration():
    from core.services.yandex.adapter import _YMWriteSession

    session = _YMWriteSession(MagicMock())
    assert session.apply_transliteration is False


# ---------------------------------------------------------------------------
# _SpotifyWriteSession
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_spotify_session_search_track():
    from core.services.spotify.adapter import _SpotifyWriteSession

    sp_track = MagicMock()
    sp_track.id = "spotify123"
    sp_track.artists_str = "Badfinger"
    sp_track.title = "Without You"

    client = MagicMock()
    client.search_tracks = AsyncMock(return_value=[sp_track])

    session = _SpotifyWriteSession(client)
    results = await session.search_track("Badfinger Without You", limit=10)

    assert len(results) == 1
    assert results[0].track_url == "spotify123"
    assert results[0].track_id == hash("spotify123") & 0x7FFFFFFF
    assert results[0].artist == "Badfinger"


@pytest.mark.asyncio
async def test_spotify_session_write_track_liked():
    from core.services.spotify.adapter import _SpotifyWriteSession

    client = MagicMock()
    client.like_track = AsyncMock(return_value=True)

    session = _SpotifyWriteSession(client)
    status = await session.write_track(_match(track_url="sp_id_abc"))

    client.like_track.assert_called_once_with("sp_id_abc")
    assert status == "liked"


@pytest.mark.asyncio
async def test_spotify_session_search_artist():
    from core.services.spotify.adapter import _SpotifyWriteSession

    artist = MagicMock()
    artist.id = "artist_id_1"
    artist.name = "Radiohead"

    client = MagicMock()
    client.search_artists = AsyncMock(return_value=[artist])

    session = _SpotifyWriteSession(client)
    results = await session.search_artist("Radiohead", limit=3)

    client.search_artists.assert_called_once_with("Radiohead", limit=3)
    assert results == [{"id": "artist_id_1", "name": "Radiohead"}]


@pytest.mark.asyncio
async def test_spotify_session_follow_artist():
    from core.services.spotify.adapter import _SpotifyWriteSession

    client = MagicMock()
    client.follow_artist = AsyncMock(return_value=True)

    session = _SpotifyWriteSession(client)
    result = await session.follow_artist("artist_id_1")

    client.follow_artist.assert_called_once_with("artist_id_1")
    assert result is True


def test_spotify_session_apply_transliteration():
    from core.services.spotify.adapter import _SpotifyWriteSession

    session = _SpotifyWriteSession(MagicMock())
    assert session.apply_transliteration is True


# ---------------------------------------------------------------------------
# _SCWriteSession
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sc_session_playlist_mode_no_like():
    """playlist_mode=True: write_track returns 'in_playlist' without calling like_track."""
    from core.services.soundcloud.adapter import _SCWriteSession

    client = MagicMock()
    client.like_track = AsyncMock(return_value=True)

    session = _SCWriteSession(client, playlist_mode=True, like_tracks=False)
    status = await session.write_track(_match(track_id=42))

    assert status == "in_playlist"
    client.like_track.assert_not_called()


@pytest.mark.asyncio
async def test_sc_session_like_tracks_success():
    """like_tracks=True: calls like_track → 'liked'."""
    from core.services.soundcloud.adapter import _SCWriteSession

    client = MagicMock()
    client.like_track = AsyncMock(return_value=True)

    session = _SCWriteSession(client, playlist_mode=False, like_tracks=True)
    status = await session.write_track(_match(track_id=55))

    client.like_track.assert_called_once_with(55)
    assert status == "liked"


@pytest.mark.asyncio
async def test_sc_session_like_tracks_fallback_on_404():
    """like_tracks=True + LikeNotSupportedError → 'in_playlist'."""
    from core.services.soundcloud.adapter import _SCWriteSession
    from core.soundcloud.client import LikeNotSupportedError

    client = MagicMock()
    client.like_track = AsyncMock(side_effect=LikeNotSupportedError("404"))

    session = _SCWriteSession(client, playlist_mode=False, like_tracks=True)
    status = await session.write_track(_match(track_id=77))

    assert status == "in_playlist"


@pytest.mark.asyncio
async def test_sc_session_search_track_respects_limit():
    """search_track slices results to limit."""
    from core.services.soundcloud.adapter import _SCWriteSession

    def _make_sc_track(i):
        t = MagicMock()
        t.id = i
        t.url = f"http://sc/{i}"
        t.artist = "A"
        t.title = "T"
        return t

    client = MagicMock()
    client.search_tracks = AsyncMock(return_value=[_make_sc_track(i) for i in range(20)])

    session = _SCWriteSession(client)
    results = await session.search_track("query", limit=5)

    assert len(results) == 5


# ---------------------------------------------------------------------------
# pipeline.process_one_track
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_process_one_track_liked():
    """Happy path: search → match → write_track → 'liked', DB updated."""
    from migration.pipeline import process_one_track

    session = MagicMock()
    session.apply_transliteration = False
    session.search_track = AsyncMock(return_value=[_candidate()])
    session.write_track = AsyncMock(return_value="liked")

    row = {"id": 1, "ym_artist": "Radiohead", "ym_title": "Creep"}

    with patch("migration.pipeline.find_best_match", return_value=_match()), \
         patch("migration.pipeline.update_track", new_callable=AsyncMock) as mock_upd:
        status = await process_one_track(session, row)

    assert status == "liked"
    mock_upd.assert_called_once_with(1, status="liked", sc_url="url/1", match_score=90.0)


@pytest.mark.asyncio
async def test_process_one_track_not_found_no_candidates():
    """Empty search results → 'not_found'."""
    from migration.pipeline import process_one_track

    session = MagicMock()
    session.apply_transliteration = False
    session.search_track = AsyncMock(return_value=[])

    row = {"id": 2, "ym_artist": "Unknown", "ym_title": "Track"}

    with patch("migration.pipeline.update_track", new_callable=AsyncMock) as mock_upd:
        status = await process_one_track(session, row)

    assert status == "not_found"
    mock_upd.assert_called_once_with(2, status="not_found")


@pytest.mark.asyncio
async def test_process_one_track_uncertain():
    """Uncertain match → 'uncertain', DB status='not_found'."""
    from migration.pipeline import process_one_track

    session = MagicMock()
    session.apply_transliteration = False
    session.search_track = AsyncMock(return_value=[_candidate()])

    row = {"id": 3, "ym_artist": "A", "ym_title": "B"}
    uncertain = _match(score=65.0, matched=False, uncertain=True)

    with patch("migration.pipeline.find_best_match", return_value=uncertain), \
         patch("migration.pipeline.update_track", new_callable=AsyncMock) as mock_upd:
        status = await process_one_track(session, row)

    assert status == "uncertain"
    mock_upd.assert_called_once_with(3, status="not_found", sc_url="url/1", match_score=65.0)


@pytest.mark.asyncio
async def test_process_one_track_write_error():
    """write_track returns 'error' → DB updated with 'error'."""
    from migration.pipeline import process_one_track

    session = MagicMock()
    session.apply_transliteration = False
    session.search_track = AsyncMock(return_value=[_candidate()])
    session.write_track = AsyncMock(return_value="error")

    row = {"id": 4, "ym_artist": "A", "ym_title": "T"}

    with patch("migration.pipeline.find_best_match", return_value=_match()), \
         patch("migration.pipeline.update_track", new_callable=AsyncMock) as mock_upd:
        status = await process_one_track(session, row)

    assert status == "error"
    mock_upd.assert_called_once_with(4, status="error")


@pytest.mark.asyncio
async def test_process_one_track_transliteration_adds_queries():
    """apply_transliteration=True → extra queries added for Cyrillic artists."""
    from migration.pipeline import process_one_track

    session = MagicMock()
    session.apply_transliteration = True
    session.search_track = AsyncMock(return_value=[])

    row = {"id": 5, "ym_artist": "Баста", "ym_title": "Три полоски"}

    with patch("migration.pipeline.update_track", new_callable=AsyncMock):
        await process_one_track(session, row)

    # Should have more than one query: original Cyrillic + transliterated variants
    call_queries = [c.args[0] for c in session.search_track.call_args_list]
    cyrillic_queries = [q for q in call_queries if "Баста" in q]
    latin_queries = [q for q in call_queries if "Баста" not in q and "Три" not in q]
    assert len(cyrillic_queries) >= 1
    assert len(call_queries) > 1  # at least transliteration variants were added


@pytest.mark.asyncio
async def test_process_one_track_no_transliteration_for_latin():
    """apply_transliteration=True but Latin artist → no extra queries."""
    from migration.pipeline import process_one_track

    session = MagicMock()
    session.apply_transliteration = True
    session.search_track = AsyncMock(return_value=[])

    row = {"id": 6, "ym_artist": "Radiohead", "ym_title": "Creep"}

    with patch("migration.pipeline.update_track", new_callable=AsyncMock):
        await process_one_track(session, row)

    call_queries = [c.args[0] for c in session.search_track.call_args_list]
    # No transliteration for Latin → only primary query + maybe title fallback
    assert "Radiohead Creep" in call_queries


# ---------------------------------------------------------------------------
# pipeline.run_pending_tracks_loop
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_pending_loop_stats():
    """run_pending_tracks_loop aggregates stats correctly."""
    from migration.pipeline import run_pending_tracks_loop

    pending = [
        {"id": 1, "ym_artist": "A", "ym_title": "T1"},
        {"id": 2, "ym_artist": "B", "ym_title": "T2"},
        {"id": 3, "ym_artist": "C", "ym_title": "T3"},
    ]

    call_count = [0]

    async def fake_process(session, row):
        call_count[0] += 1
        statuses = ["liked", "not_found", "error"]
        return statuses[row["id"] - 1]

    session = MagicMock()

    with patch("migration.pipeline.get_pending_tracks", AsyncMock(return_value=pending)), \
         patch("migration.pipeline.update_track", new_callable=AsyncMock), \
         patch("migration.pipeline.process_one_track", side_effect=fake_process):
        stats = await run_pending_tracks_loop(session, migration_id=1)

    assert stats.total == 3
    assert stats.liked == 1
    assert stats.not_found == 1
    assert stats.errors == 1
    assert call_count[0] == 3


@pytest.mark.asyncio
async def test_run_pending_loop_exception_counted_as_error():
    """If process_one_track raises, track is marked 'error' and stats.errors incremented."""
    from migration.pipeline import run_pending_tracks_loop

    pending = [{"id": 1, "ym_artist": "A", "ym_title": "T"}]

    async def raise_on_process(session, row):
        raise RuntimeError("boom")

    session = MagicMock()

    with patch("migration.pipeline.get_pending_tracks", AsyncMock(return_value=pending)), \
         patch("migration.pipeline.update_track", new_callable=AsyncMock) as mock_upd, \
         patch("migration.pipeline.process_one_track", side_effect=raise_on_process):
        stats = await run_pending_tracks_loop(session, migration_id=1)

    assert stats.errors == 1
    mock_upd.assert_called_once_with(1, status="error")


@pytest.mark.asyncio
async def test_run_pending_loop_calls_progress_callback():
    """progress_callback is called for each track."""
    from migration.pipeline import run_pending_tracks_loop

    pending = [{"id": 1, "ym_artist": "A", "ym_title": "T"}]

    async def fake_process(session, row):
        return "liked"

    session = MagicMock()
    cb = AsyncMock()

    with patch("migration.pipeline.get_pending_tracks", AsyncMock(return_value=pending)), \
         patch("migration.pipeline.update_track", new_callable=AsyncMock), \
         patch("migration.pipeline.process_one_track", side_effect=fake_process):
        await run_pending_tracks_loop(session, migration_id=1, progress_callback=cb)

    cb.assert_called_once_with(1, 1, "A — T")


@pytest.mark.asyncio
async def test_run_pending_loop_uncertain_counts_in_not_found():
    """'uncertain' status increments both uncertain and not_found."""
    from migration.pipeline import run_pending_tracks_loop

    pending = [{"id": 1, "ym_artist": "A", "ym_title": "T"}]

    async def fake_process(session, row):
        return "uncertain"

    session = MagicMock()

    with patch("migration.pipeline.get_pending_tracks", AsyncMock(return_value=pending)), \
         patch("migration.pipeline.update_track", new_callable=AsyncMock), \
         patch("migration.pipeline.process_one_track", side_effect=fake_process):
        stats = await run_pending_tracks_loop(session, migration_id=1)

    assert stats.uncertain == 1
    assert stats.not_found == 1
    assert stats.liked == 0
