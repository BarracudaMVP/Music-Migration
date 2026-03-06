"""FastAPI dependencies."""
from fastapi import Header, HTTPException, status

from config import settings

_MAX_MIGRATIONS_PER_HOUR = 10


async def verify_internal_token(x_internal_token: str = Header(default="")) -> None:
    """Проверяет X-Internal-Token для bot→API запросов."""
    expected = settings.api_internal_token
    if expected and x_internal_token != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid internal token")


def arq_pool_dep():
    """Returns the shared ARQ Redis pool (set during API startup)."""
    from api.main import get_arq_pool
    return get_arq_pool()


async def check_migration_rate_limit(user_id: str) -> bool:
    """
    Проверяет и инкрементирует счётчик переносов пользователя.
    Возвращает True если лимит не превышен, False если превышен.
    Лимит: _MAX_MIGRATIONS_PER_HOUR запусков в час (окно — скользящий TTL 3600с).
    """
    from api.main import get_arq_pool
    arq = get_arq_pool()
    if not arq:
        return True  # Redis недоступен — пропускаем

    key = f"ratelimit:migrate:{user_id}"
    count = await arq.incr(key)
    if count == 1:
        await arq.expire(key, 3600)
    return count <= _MAX_MIGRATIONS_PER_HOUR
