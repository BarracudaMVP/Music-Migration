"""Auth routes: Yandex OAuth code exchange + SoundCloud token validation."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.deps import verify_internal_token

router = APIRouter(dependencies=[Depends(verify_internal_token)])


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
