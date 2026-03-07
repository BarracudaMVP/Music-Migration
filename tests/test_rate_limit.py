"""Unit tests for check_migration_rate_limit (api/deps.py)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


async def _run_check(user_id: str, count_after_incr: int) -> bool:
    """Helper: patches get_arq_pool with a fake Redis that returns count_after_incr."""
    fake_redis = MagicMock()
    fake_redis.incr = AsyncMock(return_value=count_after_incr)
    fake_redis.expire = AsyncMock()

    with patch("api.main.get_arq_pool", return_value=fake_redis):
        from api.deps import check_migration_rate_limit
        return await check_migration_rate_limit(user_id)


# ---------------------------------------------------------------------------
# Basic allow / deny
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_first_migration_allowed():
    assert await _run_check("user_1", count_after_incr=1) is True


@pytest.mark.asyncio
async def test_tenth_migration_allowed():
    assert await _run_check("user_1", count_after_incr=10) is True


@pytest.mark.asyncio
async def test_eleventh_migration_denied():
    assert await _run_check("user_1", count_after_incr=11) is False


@pytest.mark.asyncio
async def test_high_count_denied():
    assert await _run_check("user_1", count_after_incr=100) is False


# ---------------------------------------------------------------------------
# TTL set only on first call
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ttl_set_on_first_call():
    """expire() is called when count == 1 (first migration in the window)."""
    fake_redis = MagicMock()
    fake_redis.incr = AsyncMock(return_value=1)
    fake_redis.expire = AsyncMock()

    with patch("api.main.get_arq_pool", return_value=fake_redis):
        from api.deps import check_migration_rate_limit
        await check_migration_rate_limit("user_x")

    fake_redis.expire.assert_called_once_with("ratelimit:migrate:user_x", 3600)


@pytest.mark.asyncio
async def test_ttl_not_set_on_subsequent_calls():
    """expire() is NOT called when count > 1."""
    fake_redis = MagicMock()
    fake_redis.incr = AsyncMock(return_value=5)
    fake_redis.expire = AsyncMock()

    with patch("api.main.get_arq_pool", return_value=fake_redis):
        from api.deps import check_migration_rate_limit
        await check_migration_rate_limit("user_y")

    fake_redis.expire.assert_not_called()


# ---------------------------------------------------------------------------
# Redis unavailable
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_redis_pool_allows_all():
    """If Redis pool is None (not ready), allow the request."""
    with patch("api.main.get_arq_pool", return_value=None):
        from api.deps import check_migration_rate_limit
        result = await check_migration_rate_limit("user_z")

    assert result is True


# ---------------------------------------------------------------------------
# Key format
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_redis_key_includes_user_id():
    """Redis key must be 'ratelimit:migrate:{user_id}'."""
    fake_redis = MagicMock()
    fake_redis.incr = AsyncMock(return_value=1)
    fake_redis.expire = AsyncMock()

    with patch("api.main.get_arq_pool", return_value=fake_redis):
        from api.deps import check_migration_rate_limit
        await check_migration_rate_limit("tg_42")

    fake_redis.incr.assert_called_once_with("ratelimit:migrate:tg_42")
