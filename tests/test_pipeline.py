"""
Unit tests for migration/tracks.py pipeline logic.

All external dependencies (SoundCloud client, DB CRUD calls) are mocked so
these tests run without any network access or database.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, call, patch

from core.matcher import MatchResult


def _make_sc_track(sc_id=1, url="http://sc/1", artist="Artist", title="Title"):
    t = MagicMock()
    t.id = sc_id
    t.url = url
    t.artist = artist
    t.title = title
    return t


def _make_match(sc_id=1, score=90.0, matched=True, uncertain=False):
    return MatchResult(
        sc_id=sc_id,
        sc_url=f"http://sc/{sc_id}",
        sc_artist="Artist",
        sc_title="Title",
        score=score,
        matched=matched,
        uncertain=uncertain,
    )


# ---------------------------------------------------------------------------
# _process_one_track
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_process_track_liked():
    """Happy path: SC returns results, match found, like succeeds → 'liked'."""
    from migration.tracks import _process_one_track

    sc_client = MagicMock()
    sc_client.search_tracks = AsyncMock(return_value=[_make_sc_track(sc_id=42)])
    sc_client.like_track = AsyncMock(return_value=True)

    row = {"id": 1, "ym_id": "ym1", "ym_artist": "Radiohead", "ym_title": "Creep"}

    with patch("migration.tracks.find_best_match", return_value=_make_match(sc_id=42)), \
         patch("migration.tracks.update_track", new_callable=AsyncMock) as mock_update:
        result = await _process_one_track(sc_client, row)

    assert result == "liked"
    sc_client.like_track.assert_called_once_with(42)
    mock_update.assert_called_once_with(
        1, status="liked", sc_id=42, sc_url="http://sc/42", match_score=90.0
    )


@pytest.mark.asyncio
async def test_process_track_no_sc_results():
    """SC returns empty list → 'not_found'."""
    from migration.tracks import _process_one_track

    sc_client = MagicMock()
    sc_client.search_tracks = AsyncMock(return_value=[])

    row = {"id": 2, "ym_id": "ym2", "ym_artist": "Unknown", "ym_title": "Unknown"}

    with patch("migration.tracks.update_track", new_callable=AsyncMock) as mock_update:
        result = await _process_one_track(sc_client, row)

    assert result == "not_found"
    mock_update.assert_called_once_with(2, status="not_found")


@pytest.mark.asyncio
async def test_process_track_find_best_match_returns_none():
    """find_best_match returns None (candidates list empty internally) → 'not_found'."""
    from migration.tracks import _process_one_track

    sc_client = MagicMock()
    sc_client.search_tracks = AsyncMock(return_value=[_make_sc_track()])

    row = {"id": 3, "ym_id": "ym3", "ym_artist": "A", "ym_title": "T"}

    with patch("migration.tracks.find_best_match", return_value=None), \
         patch("migration.tracks.update_track", new_callable=AsyncMock) as mock_update:
        result = await _process_one_track(sc_client, row)

    assert result == "not_found"
    mock_update.assert_called_once_with(3, status="not_found")


@pytest.mark.asyncio
async def test_process_track_uncertain():
    """Score in uncertain zone (matched=False, uncertain=True) → 'uncertain', sc_id saved."""
    from migration.tracks import _process_one_track

    sc_client = MagicMock()
    sc_client.search_tracks = AsyncMock(return_value=[_make_sc_track(sc_id=99)])

    row = {"id": 5, "ym_id": "ym5", "ym_artist": "Radiohead", "ym_title": "Creep"}

    uncertain_match = _make_match(sc_id=99, score=68.0, matched=False, uncertain=True)

    with patch("migration.tracks.find_best_match", return_value=uncertain_match), \
         patch("migration.tracks.update_track", new_callable=AsyncMock) as mock_update:
        result = await _process_one_track(sc_client, row)

    assert result == "uncertain"
    mock_update.assert_called_once_with(
        5, status="not_found", sc_id=99, sc_url="http://sc/99", match_score=68.0
    )


@pytest.mark.asyncio
async def test_process_track_below_threshold_not_uncertain():
    """Score below threshold AND below uncertain floor → 'not_found', match_score saved."""
    from migration.tracks import _process_one_track

    sc_client = MagicMock()
    sc_client.search_tracks = AsyncMock(return_value=[_make_sc_track()])

    row = {"id": 6, "ym_id": "ym6", "ym_artist": "Beatles", "ym_title": "Hey Jude"}

    low_match = _make_match(sc_id=1, score=20.0, matched=False, uncertain=False)

    with patch("migration.tracks.find_best_match", return_value=low_match), \
         patch("migration.tracks.update_track", new_callable=AsyncMock) as mock_update:
        result = await _process_one_track(sc_client, row)

    assert result == "not_found"
    mock_update.assert_called_once_with(6, status="not_found", match_score=20.0)


@pytest.mark.asyncio
async def test_process_track_like_fails():
    """like_track returns False → 'error'."""
    from migration.tracks import _process_one_track

    sc_client = MagicMock()
    sc_client.search_tracks = AsyncMock(return_value=[_make_sc_track(sc_id=77)])
    sc_client.like_track = AsyncMock(return_value=False)

    row = {"id": 7, "ym_id": "ym7", "ym_artist": "A", "ym_title": "T"}

    with patch("migration.tracks.find_best_match", return_value=_make_match(sc_id=77)), \
         patch("migration.tracks.update_track", new_callable=AsyncMock) as mock_update:
        result = await _process_one_track(sc_client, row)

    assert result == "error"
    mock_update.assert_called_once_with(7, status="error")


@pytest.mark.asyncio
async def test_process_track_search_query_format():
    """Primary query is '{artist} {title}'. When empty, fallback to title-only."""
    from migration.tracks import _process_one_track

    sc_client = MagicMock()
    sc_client.search_tracks = AsyncMock(return_value=[])

    row = {"id": 8, "ym_id": "ym8", "ym_artist": "Radiohead", "ym_title": "Creep"}

    with patch("migration.tracks.update_track", new_callable=AsyncMock):
        await _process_one_track(sc_client, row)

    # Primary query uses "{artist} {title}" format
    sc_client.search_tracks.assert_any_call("Radiohead Creep")
    # Fallback to title-only when primary returns empty
    sc_client.search_tracks.assert_any_call("Creep")


@pytest.mark.asyncio
async def test_process_compound_artist_parallel_queries():
    """Compound artist (feat.) → multiple parallel search queries."""
    from migration.tracks import _process_one_track

    sc_client = MagicMock()
    sc_client.search_tracks = AsyncMock(return_value=[_make_sc_track(sc_id=5)])
    sc_client.like_track = AsyncMock(return_value=True)

    row = {"id": 9, "ym_id": "ym9", "ym_artist": "Artist1 feat. Artist2", "ym_title": "Song"}

    with patch("migration.tracks.find_best_match", return_value=_make_match(sc_id=5)), \
         patch("migration.tracks.update_track", new_callable=AsyncMock):
        await _process_one_track(sc_client, row)

    calls = [c.args[0] for c in sc_client.search_tracks.call_args_list]
    assert "Artist1 Song" in calls
    assert "Artist2 Song" in calls


@pytest.mark.asyncio
async def test_process_dedup_candidates_by_sc_id():
    """Same sc_id from multiple queries → find_best_match receives deduplicated list."""
    from migration.tracks import _process_one_track

    shared_track = _make_sc_track(sc_id=77)
    sc_client = MagicMock()
    sc_client.search_tracks = AsyncMock(return_value=[shared_track])
    sc_client.like_track = AsyncMock(return_value=True)

    row = {"id": 10, "ym_id": "ym10", "ym_artist": "A feat. B", "ym_title": "T"}

    captured = {}

    def fake_find_best_match(artist, title, candidates):
        captured["candidates"] = candidates
        return _make_match(sc_id=77)

    with patch("migration.tracks.find_best_match", side_effect=fake_find_best_match), \
         patch("migration.tracks.update_track", new_callable=AsyncMock):
        await _process_one_track(sc_client, row)

    assert len([c for c in captured["candidates"] if c.sc_id == 77]) == 1


@pytest.mark.asyncio
async def test_process_title_only_fallback_when_compound_empty():
    """When all compound queries return empty → fallback to title-only."""
    from migration.tracks import _process_one_track

    call_log = []

    async def mock_search(query):
        call_log.append(query)
        return []

    sc_client = MagicMock()
    sc_client.search_tracks = AsyncMock(side_effect=mock_search)

    row = {"id": 11, "ym_id": "ym11", "ym_artist": "A feat. B", "ym_title": "Song"}

    with patch("migration.tracks.update_track", new_callable=AsyncMock):
        await _process_one_track(sc_client, row)

    assert "Song" in call_log


# ---------------------------------------------------------------------------
# MigrationStats
# ---------------------------------------------------------------------------

def test_migration_stats_str():
    from migration.tracks import MigrationStats
    stats = MigrationStats(total=100, liked=80, not_found=15, errors=3, uncertain=2)
    s = str(stats)
    assert "100" in s
    assert "80" in s
    assert "15" in s
    assert "3" in s


def test_migration_stats_defaults():
    from migration.tracks import MigrationStats
    stats = MigrationStats()
    assert stats.total == 0
    assert stats.liked == 0
    assert stats.not_found == 0
    assert stats.errors == 0
    assert stats.uncertain == 0
