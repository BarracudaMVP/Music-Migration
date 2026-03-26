"""Auth routes: Yandex OAuth code exchange + SoundCloud token validation.

Also contains bot-specific OAuth redirect routes (moved from oauth.py — MM-82):
- GET /auth/yandex/bot               — start Yandex OAuth for Telegram bot (public, no token required)
- GET /api/auth/yandex/poll/{state}  — bot polls for Yandex token (requires X-Internal-Token)
"""
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from api.deps import verify_internal_token

router = APIRouter(dependencies=[Depends(verify_internal_token)])

# Public bot routes — no X-Internal-Token required (browser redirect entry points)
router_public = APIRouter()


class YandexCodeRequest(BaseModel):
    code: str


class YandexTokenResponse(BaseModel):
    token: str
    login: str


class SoundCloudValidateRequest(BaseModel):
    token: str


class SoundCloudValidateResponse(BaseModel):
    user_id: int
    username: str


@router.post("/yandex/token", response_model=YandexTokenResponse)
async def exchange_yandex_code(body: YandexCodeRequest):
    """Обменивает код авторизации Яндекса на access token."""
    try:
        from bot.oauth.yandex import exchange_code
        token = await exchange_code(body.code)
        from core.yandex.client import YandexMusicClient
        from config import settings
        client = await YandexMusicClient(token, proxy_url=settings.ym_proxy_url or None).init()
        account = client._client.me.account if client._client.me else None
        login = (
            getattr(account, "login", None)
            or getattr(account, "display_name", None)
            or ""
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    return YandexTokenResponse(token=token, login=login)


@router.post("/soundcloud/validate", response_model=SoundCloudValidateResponse)
async def validate_soundcloud_token(body: SoundCloudValidateRequest):
    """Проверяет токен SoundCloud и возвращает user_id + username."""
    try:
        from core.soundcloud.client import SoundCloudClient
        sc = await SoundCloudClient(body.token).init()
        user_id = sc._user_id
        username = sc._username
        await sc.close()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return SoundCloudValidateResponse(user_id=user_id, username=username)


@router.get("/yandex/poll/{state_id}")
async def poll_yandex_bot_token(state_id: str, request: Request):
    """Internal: bot polls this to get Yandex token after web OAuth (MM-44)."""
    from api.main import get_arq_pool

    arq = get_arq_pool()
    if not arq:
        raise HTTPException(status_code=503, detail="Redis unavailable")

    raw = await arq.get(f"ym_auth:{state_id}")
    if not raw:
        raise HTTPException(status_code=404, detail="Token not found")

    await arq.delete(f"ym_auth:{state_id}")
    token = raw.decode() if isinstance(raw, bytes) else raw
    return {"token": token}


@router_public.get("/auth/yandex/bot")
async def auth_yandex_bot_start(state: str = ""):
    """Start Yandex OAuth for Telegram bot flow. state must begin with 'bot_'."""
    from bot.oauth.yandex import get_callback_auth_url
    from config import settings

    if not settings.yandex_redirect_uri or not state.startswith("bot_"):
        return RedirectResponse(
            f"/?error={quote('Некорректный запрос авторизации')}",
            status_code=303,
        )
    return RedirectResponse(get_callback_auth_url(state), status_code=303)
