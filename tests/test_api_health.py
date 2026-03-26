"""Tests for GET /health endpoint."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import Response


@pytest.mark.asyncio
async def test_health_ok_when_redis_and_db_up():
    """Returns status=ok and 200 when Redis and DB are available."""
    from api.main import health

    mock_arq = AsyncMock()
    mock_arq.ping = AsyncMock()
    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_conn.execute = AsyncMock()
    mock_engine = MagicMock()
    mock_engine.connect = MagicMock(return_value=mock_conn)

    response = Response()
    with patch("api.main.get_arq_pool", return_value=mock_arq):
        with patch("core.db.session.engine", mock_engine):
            result = await health(response)

    assert result["status"] == "ok"
    assert result["redis"] == "ok"
    assert result["db"] == "ok"
    assert response.status_code == 200
    assert isinstance(result["version"], str)
    assert result["version"].count(".") == 2


@pytest.mark.asyncio
async def test_health_degraded_when_redis_down():
    """Returns status=degraded and 503 when Redis is unavailable."""
    from api.main import health

    mock_arq = AsyncMock()
    mock_arq.ping = AsyncMock(side_effect=Exception("connection refused"))
    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_conn.execute = AsyncMock()
    mock_engine = MagicMock()
    mock_engine.connect = MagicMock(return_value=mock_conn)

    response = Response()
    with patch("api.main.get_arq_pool", return_value=mock_arq):
        with patch("core.db.session.engine", mock_engine):
            result = await health(response)

    assert result["status"] == "degraded"
    assert result["redis"] == "error"
    assert response.status_code == 503


def test_health_is_async():
    """Ensure health is an async function."""
    from api.main import health
    assert asyncio.iscoroutinefunction(health)
