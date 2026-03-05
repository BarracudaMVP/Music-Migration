"""
Яндекс OAuth 2.0 — Authorization Code Flow.

Используем redirect_uri = https://oauth.yandex.ru/verification_code
Это специальная страница Яндекса: после входа пользователь видит
короткий код прямо в браузере и вставляет его в бота.
Нам не нужен свой сервер для callback.

Настройка приложения на oauth.yandex.ru:
  1. Создать приложение → Веб-сервисы
  2. Redirect URI: https://oauth.yandex.ru/verification_code
  3. Права: login:info + Яндекс.Музыка (все на чтение)
  4. Скопировать ClientID и Client secret → в .env
"""
import aiohttp
from config import settings

_AUTH_URL = "https://oauth.yandex.ru/authorize"
_TOKEN_URL = "https://oauth.yandex.ru/token"
_REDIRECT_URI = "https://oauth.yandex.ru/verification_code"


def get_auth_url() -> str:
    """
    Возвращает URL авторизации. Пользователь переходит по нему,
    входит в Яндекс и получает код на странице Яндекса.
    """
    from urllib.parse import urlencode
    params = {
        "response_type": "code",
        "client_id": settings.yandex_client_id,
        "redirect_uri": _REDIRECT_URI,
        "force_confirm": "yes",  # всегда показывать экран подтверждения
    }
    return f"{_AUTH_URL}?{urlencode(params)}"


async def exchange_code(code: str) -> str:
    """
    Обменивает код авторизации на access token.
    Возвращает токен или выбрасывает ValueError с описанием ошибки.
    """
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
                "redirect_uri": _REDIRECT_URI,
            },
        )
        body = await resp.json(content_type=None)

    if "access_token" in body:
        return body["access_token"]

    error = body.get("error_description") or body.get("error") or str(body)
    raise ValueError(f"Яндекс вернул ошибку: {error}")
