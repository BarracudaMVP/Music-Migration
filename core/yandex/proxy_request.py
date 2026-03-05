"""
Подкласс Request из yandex_music с поддержкой SOCKS5-прокси через aiohttp-socks.
"""
import asyncio
import aiohttp
from yandex_music.utils.request_async import Request, USER_AGENT, default_timeout
from yandex_music.exceptions import (
    TimedOutError, NetworkError, UnauthorizedError,
    BadRequestError, NotFoundError, YandexMusicError,
)


class SocksProxyRequest(Request):
    """Request с поддержкой socks4:// / socks5:// через ProxyConnector."""

    async def _request_wrapper(self, *args, **kwargs):
        proxy = kwargs.pop("proxy", None)

        if not proxy or not (proxy.startswith("socks4") or proxy.startswith("socks5")):
            if proxy:
                kwargs["proxy"] = proxy
            return await super()._request_wrapper(*args, **kwargs)

        from aiohttp_socks import ProxyConnector

        if "headers" not in kwargs:
            kwargs["headers"] = {}
        kwargs["headers"]["User-Agent"] = USER_AGENT

        timeout_val = kwargs.get("timeout", default_timeout)
        kwargs["timeout"] = (
            aiohttp.ClientTimeout(total=self._timeout)
            if timeout_val is default_timeout
            else aiohttp.ClientTimeout(total=timeout_val)
        )

        try:
            connector = ProxyConnector.from_url(proxy)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.request(*args, **kwargs) as resp:
                    content = await resp.content.read()
        except asyncio.TimeoutError as e:
            raise TimedOutError from e
        except aiohttp.ClientError as e:
            raise NetworkError(e) from e

        if 200 <= resp.status <= 299:
            return content

        try:
            parse = self._parse(content)
            message = parse.get_error()
        except YandexMusicError:
            message = "Unknown HTTPError"

        if resp.status in (401, 403):
            raise UnauthorizedError(message)
        if resp.status == 400:
            raise BadRequestError(message)
        if resp.status == 404:
            raise NotFoundError(message)
        if resp.status in (409, 413):
            raise NetworkError(message)
        if resp.status == 502:
            raise NetworkError("Bad Gateway")

        raise NetworkError(f"{message} ({resp.status}): {content}")
