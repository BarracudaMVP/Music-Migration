"""FastAPI dependencies."""
from fastapi import Header, HTTPException, status

from config import settings


async def verify_internal_token(x_internal_token: str = Header(default="")) -> None:
    """Проверяет X-Internal-Token для bot→API запросов."""
    expected = settings.api_internal_token
    if expected and x_internal_token != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid internal token")


def arq_pool_dep():
    """Returns the shared ARQ Redis pool (set during API startup)."""
    from api.main import get_arq_pool
    return get_arq_pool()
