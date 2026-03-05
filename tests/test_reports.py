"""Tests for the reports endpoint (DB-based, not file-based)."""
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_not_found_report_returns_tracks():
    """GET /migrations/{id}/not-found returns not_found tracks as plain text."""
    from api.routes.reports import get_not_found_report

    fake_tracks = [
        {"ym_artist": "Radiohead", "ym_title": "Creep", "status": "not_found",
         "match_score": None, "sc_url": None},
        {"ym_artist": "Beatles", "ym_title": "Hey Jude", "status": "not_found",
         "match_score": 68.0, "sc_url": "http://sc/123"},
        {"ym_artist": "Drake", "ym_title": "Gods Plan", "status": "liked",
         "match_score": 95.0, "sc_url": "http://sc/456"},
    ]

    with patch("api.routes.reports.get_all_tracks", new_callable=AsyncMock, return_value=fake_tracks):
        response = await get_not_found_report(migration_id=1)

    assert "Radiohead" in response
    assert "Hey Jude" in response
    # Liked track must not appear
    assert "Gods Plan" not in response


@pytest.mark.asyncio
async def test_not_found_report_includes_score_for_uncertain():
    """Tracks with match_score and sc_url get extra annotation."""
    from api.routes.reports import get_not_found_report

    fake_tracks = [
        {"ym_artist": "Artist", "ym_title": "Song", "status": "not_found",
         "match_score": 68.0, "sc_url": "http://sc/99"},
    ]

    with patch("api.routes.reports.get_all_tracks", new_callable=AsyncMock, return_value=fake_tracks):
        response = await get_not_found_report(migration_id=1)

    assert "score=68" in response
    assert "http://sc/99" in response


@pytest.mark.asyncio
async def test_not_found_report_404_when_empty():
    """404 if no not_found tracks exist."""
    from fastapi import HTTPException
    from api.routes.reports import get_not_found_report

    fake_tracks = [
        {"ym_artist": "Artist", "ym_title": "Song", "status": "liked",
         "match_score": 95.0, "sc_url": "http://sc/1"},
    ]

    with patch("api.routes.reports.get_all_tracks", new_callable=AsyncMock, return_value=fake_tracks):
        with pytest.raises(HTTPException) as exc_info:
            await get_not_found_report(migration_id=1)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_not_found_report_404_when_migration_empty():
    """404 if migration has no tracks at all."""
    from fastapi import HTTPException
    from api.routes.reports import get_not_found_report

    with patch("api.routes.reports.get_all_tracks", new_callable=AsyncMock, return_value=[]):
        with pytest.raises(HTTPException) as exc_info:
            await get_not_found_report(migration_id=999)

    assert exc_info.value.status_code == 404
