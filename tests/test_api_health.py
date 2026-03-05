"""Tests for API endpoints that don't require DB/Redis (health, pure logic)."""
import pytest


@pytest.mark.asyncio
async def test_health_returns_ok():
    """GET /health → {"status": "ok", "version": "9.0.0"}"""
    from api.main import health

    result = await health()
    assert result == {"status": "ok", "version": "9.0.0"}


@pytest.mark.asyncio
async def test_health_version_is_string():
    from api.main import health

    result = await health()
    assert isinstance(result["version"], str)
    assert result["version"].count(".") == 2  # semantic version x.y.z


def test_health_sync_callable():
    """Ensure health is an async function (not a sync one)."""
    import asyncio
    from api.main import health

    assert asyncio.iscoroutinefunction(health)
