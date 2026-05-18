from __future__ import annotations

import asyncio
import os
import random
import time
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
    """Async HTTP wrapper with retries and a polite global rate limit.

    Krisha bans IPs that hammer the site. This client enforces:

      * A small concurrency cap (default 2).
      * A *global* minimum gap between request starts (default 1.0 s with
        ±30 % jitter). This holds across all concurrent tasks, so even
        burst fan-outs don't fire requests back-to-back.
      * Exponential backoff with jitter on 429 / 5xx / network errors.
      * Optional proxy via the `proxy=` argument or the `KRISHA_PROXY` /
        `HTTPS_PROXY` env vars.

    If you keep getting blocked, lower `concurrency` to 1, raise
    `min_interval`, and/or set a proxy.
    """

    def __init__(
        self,
        *,
        concurrency: int = 2,
        retries: int = 4,
        timeout: float = 30.0,
        min_interval: float = 1.0,
        jitter: float = 0.3,
        user_agent: str | None = None,
        proxy: str | None = None,
    ) -> None:
        self._semaphore = asyncio.Semaphore(concurrency)
        self._retries = retries
        self._min_interval = max(0.0, min_interval)
        self._jitter = max(0.0, jitter)
        self._next_slot = time.monotonic()
        self._slot_lock = asyncio.Lock()

        headers = dict(DEFAULT_HEADERS)
        if user_agent:
            headers["User-Agent"] = user_agent

        proxy = proxy or os.environ.get("KRISHA_PROXY") or os.environ.get("HTTPS_PROXY")

        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            # HTTP/2 multiplexes everything over one TCP connection — which
            # also makes us easier to fingerprint. Stay on HTTP/1.1 for a
            # more "browser-like" connection profile.
            http2=False,
            timeout=timeout,
            headers=headers,
            follow_redirects=True,
            proxy=proxy,
            limits=httpx.Limits(
                max_connections=max(concurrency * 2, 4),
                max_keepalive_connections=concurrency,
            ),
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._client.aclose()

    async def _wait_for_slot(self) -> None:
        """Serialise request-start times across all tasks."""
        if self._min_interval == 0:
            return
        async with self._slot_lock:
            now = time.monotonic()
            wait = self._next_slot - now
            jitter = random.uniform(-self._jitter, self._jitter) * self._min_interval
            self._next_slot = max(now, self._next_slot) + self._min_interval + jitter
        if wait > 0:
            await asyncio.sleep(wait)

    async def get_text(self, url: str, *, params: dict | None = None) -> str:
        async with self._semaphore:
            return await self._get_with_retry(url, params=params)

    async def _get_with_retry(self, url: str, *, params: dict | None) -> str:
        last_exc: Exception | None = None
        for attempt in range(self._retries + 1):
            await self._wait_for_slot()
            try:
                r = await self._client.get(url, params=params)
                if r.status_code == 429 or 500 <= r.status_code < 600:
                    retry_after = r.headers.get("Retry-After")
                    delay = (
                        float(retry_after)
                        if retry_after and retry_after.isdigit()
                        else min(60.0, 2.0 * (2**attempt))
                    )
                    await asyncio.sleep(delay + random.uniform(0, 0.5))
                    continue
                if r.status_code == 403:
                    # Likely IP block or anti-bot page. Retrying won't help;
                    # bubble up so the user sees it immediately.
                    raise httpx.HTTPStatusError(
                        f"403 Forbidden — krisha may have blocked this IP "
                        f"({url}). Try lowering --concurrency, raising "
                        f"--min-interval, or using --proxy / KRISHA_PROXY.",
                        request=r.request,
                        response=r,
                    )
                r.raise_for_status()
                return r.text
            except (httpx.TransportError, httpx.RemoteProtocolError) as exc:
                last_exc = exc
                await asyncio.sleep(min(60.0, 2.0 * (2**attempt)) + random.uniform(0, 0.5))
        if last_exc:
            raise last_exc
        raise httpx.HTTPError(f"giving up on {url} after {self._retries} retries")
