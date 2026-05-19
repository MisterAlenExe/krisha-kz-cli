"""Rate-limited async HTTP client for the krisha.kz mobile API.

The polite-by-default settings carry over from the HTML scraper days:
small concurrency, global min-interval between request starts, retry on
429/5xx, surface 403 immediately. `appId`/`appKey` are auto-injected.
"""

from __future__ import annotations

import asyncio
import os
import random
import time
from typing import Any, Self

import httpx

from .constants import APP_ID, APP_KEY, DEFAULT_HEADERS


class ApiClient:
    """Shared HTTP client across all endpoint wrappers.

    A single instance fronts every call: the rate limit is global, not
    per-task. Even with `asyncio.gather` fan-outs, request starts are
    serialised by `_min_interval` (± jitter).
    """

    def __init__(
        self,
        *,
        concurrency: int = 2,
        retries: int = 4,
        timeout: float = 30.0,
        min_interval: float = 1.0,
        jitter: float = 0.3,
        proxy: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._semaphore = asyncio.Semaphore(concurrency)
        self._retries = retries
        self._min_interval = max(0.0, min_interval)
        self._jitter = max(0.0, jitter)
        self._next_slot = time.monotonic()
        self._slot_lock = asyncio.Lock()

        headers = dict(DEFAULT_HEADERS)
        if extra_headers:
            headers.update(extra_headers)

        proxy = (
            proxy
            or os.environ.get("KRISHA_PROXY")
            or os.environ.get("HTTPS_PROXY")
            or None
        ) or None  # collapse "" → None so httpx doesn't choke on empty URL

        self._client = httpx.AsyncClient(
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
        if self._min_interval == 0:
            return
        async with self._slot_lock:
            now = time.monotonic()
            wait = self._next_slot - now
            jitter = random.uniform(-self._jitter, self._jitter) * self._min_interval
            self._next_slot = max(now, self._next_slot) + self._min_interval + jitter
        if wait > 0:
            await asyncio.sleep(wait)

    async def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | list[tuple[str, Any]] | None = None,
        auth: bool = True,
    ) -> Any:
        """GET a URL, auto-inject auth, return parsed JSON.

        `params` may be a dict or list-of-tuples (list-of-tuples is required
        for the mobile API's repeated keys like `query[data][map.geo_id][]`).
        """
        async with self._semaphore:
            full_params = self._with_auth(params, auth=auth)
            return await self._get_with_retry(url, params=full_params)

    @staticmethod
    def _with_auth(
        params: dict[str, Any] | list[tuple[str, Any]] | None, *, auth: bool
    ) -> list[tuple[str, Any]] | None:
        if not auth:
            return _to_pairs(params)
        pairs = _to_pairs(params) or []
        pairs = [("appId", APP_ID), ("appKey", APP_KEY)] + pairs
        return pairs

    async def _get_with_retry(
        self, url: str, *, params: list[tuple[str, Any]] | None
    ) -> Any:
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
                    raise httpx.HTTPStatusError(
                        f"403 Forbidden — krisha may have blocked this IP or "
                        f"rotated appId/appKey ({url}). Try lowering "
                        f"--concurrency, raising --min-interval, or using "
                        f"--proxy / KRISHA_PROXY.",
                        request=r.request,
                        response=r,
                    )
                r.raise_for_status()
                return r.json()
            except (httpx.TransportError, httpx.RemoteProtocolError) as exc:
                last_exc = exc
                await asyncio.sleep(min(60.0, 2.0 * (2**attempt)) + random.uniform(0, 0.5))
        if last_exc:
            raise last_exc
        raise httpx.HTTPError(f"giving up on {url} after {self._retries} retries")


def _to_pairs(
    params: dict[str, Any] | list[tuple[str, Any]] | None,
) -> list[tuple[str, Any]] | None:
    if params is None:
        return None
    if isinstance(params, list):
        return list(params)
    return list(params.items())
