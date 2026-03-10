"""
Яндекс OAuth 2.0 — Authorization Code Flow.

Два режима:
1. Verification code (legacy) — redirect_uri = https://oauth.yandex.ru/verification_code
   Пользователь видит код на странице Яндекса и вводит его вручную.
   Используется если YANDEX_REDIRECT_URI не задан.

2. Callback (MM-43/44) — redirect_uri = settings.yandex_redirect_uri
   Код приходит на наш сервер автоматически. Требует YANDEX_REDIRECT_URI в .env
   и регистрации этого URI в приложении на oauth.yandex.ru.

Настройка приложения на oauth.yandex.ru:
  1. Создать приложение → Веб-сервисы
  2. Redirect URI: https://oauth.yandex.ru/verification_code
                  + https://musicmigration.site/auth/yandex/callback  (для callback-режима)
  3. Права: login:info + Яндекс.Музыка (все на чтение)
  4. Скопировать ClientID и Client secret → в .env
"""
import aiohttp
from urllib.parse import urlencode

from config import settings

_AUTH_URL = "https://oauth.yandex.ru/authorize"
_TOKEN_URL = "https://oauth.yandex.ru/token"
_REDIRECT_URI_LEGACY = "https://oauth.yandex.ru/verification_code"


def get_auth_url() -> str:
    """Legacy flow: пользователь видит код на странице Яндекса."""
    params = {
        "response_type": "code",
        "client_id": settings.yandex_client_id,
        "redirect_uri": _REDIRECT_URI_LEGACY,
        "force_confirm": "yes",
    }
    return f"{_AUTH_URL}?{urlencode(params)}"


def get_callback_auth_url(state: str) -> str:
    """Callback flow (MM-43/44): код приходит на наш сервер автоматически."""
    params = {
        "response_type": "code",
        "client_id": settings.yandex_client_id,
        "redirect_uri": settings.yandex_redirect_uri,
        "state": state,
        "force_confirm": "yes",
    }
    return f"{_AUTH_URL}?{urlencode(params)}"


async def _exchange(code: str, redirect_uri: str) -> str:
    code = code.strip()
    if not code:
        raise ValueError("Код не должен быть пустым")
    async with aiohttp.ClientSession() as session:
        resp = await session.post(
            _TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": settings.yandex_client_id,
                "client_secret": settings.yandex_client_secret,
                "redirect_uri": redirect_uri,
            },
        )
        body = await resp.json(content_type=None)
    if "access_token" in body:
        return body["access_token"]
    error = body.get("error_description") or body.get("error") or str(body)
    raise ValueError(f"Яндекс вернул ошибку: {error}")


async def exchange_code(code: str) -> str:
    """Legacy flow: обменивает код (с verification_code redirect_uri)."""
    return await _exchange(code, _REDIRECT_URI_LEGACY)


async def exchange_code_callback(code: str) -> str:
    """Callback flow: обменивает код (с settings.yandex_redirect_uri)."""
    return await _exchange(code, settings.yandex_redirect_uri)
