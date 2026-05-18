from __future__ import annotations

import asyncio
import random
from typing import Self

import httpx

BASE_URL = "https://krisha.kz"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    # httpx decodes gzip & deflate natively; we don't add `br` to avoid
    # the optional brotli dependency.
    "Accept-Encoding": "gzip, deflate",
}


class KrishaClient:
    """Thin async wrapper around httpx with retries on 429 / 5xx."""

    def __init__(
        self,
        *,
        concurrency: int = 16,
        retries: int = 3,
        timeout: float = 20.0,
    ) -> None:
        self._semaphore = asyncio.Semaphore(concurrency)
        self._retries = retries
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            http2=True,
            timeout=timeout,
            headers=DEFAULT_HEADERS,
            follow_redirects=True,
            limits=httpx.Limits(
                max_connections=concurrency * 2,
                max_keepalive_connections=concurrency,
            ),
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._client.aclose()

    async def get_text(self, url: str, *, params: dict | None = None) -> str:
        async with self._semaphore:
            return await self._get_with_retry(url, params=params)

    async def _get_with_retry(self, url: str, *, params: dict | None) -> str:
        last_exc: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                r = await self._client.get(url, params=params)
                if r.status_code == 429 or 500 <= r.status_code < 600:
                    retry_after = r.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else 0.5 * (2**attempt)
                    await asyncio.sleep(delay + random.uniform(0, 0.25))
                    continue
                r.raise_for_status()
                return r.text
            except (httpx.TransportError, httpx.RemoteProtocolError) as exc:
                last_exc = exc
                await asyncio.sleep(0.5 * (2**attempt) + random.uniform(0, 0.25))
        if last_exc:
            raise last_exc
        raise httpx.HTTPError(f"giving up on {url} after {self._retries} retries")
