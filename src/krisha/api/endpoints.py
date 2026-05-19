"""Typed wrappers over the krisha.kz mobile JSON endpoints.

One method per endpoint we care about. Filter assembly lives in
``search.SearchFilters``; response parsing in ``models``.
"""

from __future__ import annotations

from typing import Any

from .client import ApiClient
from .constants import HOST_API, HOST_APP, VIEWS_BATCH
from .models import (
    Advert,
    AveragePrices,
    ListingEnvelope,
    Phones,
    PriceHistory,
    ViewCount,
)
from .search import SearchFilters


class KrishaApi:
    """High-level facade over `ApiClient`. Holds no state of its own."""

    def __init__(self, client: ApiClient) -> None:
        self._c = client

    # ---------- listings ----------

    async def listing_search(
        self,
        filters: SearchFilters,
        *,
        offset: int = 0,
        limit: int = 20,
        order_by: str = "add_date",
        sort: str = "desc",
        screen: str = "filter",
    ) -> ListingEnvelope:
        params = filters.listing_params(
            offset=offset,
            limit=limit,
            order_by=order_by,
            sort=sort,
            screen=screen,
        )
        data = await self._c.get_json(
            f"{HOST_APP}/v1/a/listing/search", params=params
        )
        return ListingEnvelope.model_validate(data)

    async def search_meta(self, filters: SearchFilters) -> dict[str, Any]:
        """Lightweight count oracle. Returns `{nbTotal, savedSearch}`."""
        return await self._c.get_json(
            f"{HOST_APP}/v1/a/search/meta", params=filters.meta_params()
        )

    # ---------- advert ----------

    async def show(self, advert_id: int) -> Advert:
        data = await self._c.get_json(
            f"{HOST_APP}/v1/a/show", params=[("id", advert_id)]
        )
        return Advert.model_validate(data.get("advert") or data)

    async def phones(self, advert_id: int) -> Phones:
        data = await self._c.get_json(
            f"{HOST_APP}/a/getPhones", params=[("id", advert_id)]
        )
        return Phones.model_validate(data.get("data") or data)

    async def average_prices(self, advert_id: int) -> AveragePrices:
        data = await self._c.get_json(
            f"{HOST_API}/v1/analytics/getAveragePrices.json",
            params=[("id", advert_id)],
        )
        return AveragePrices.model_validate(data)

    async def price_history(self, advert_id: int) -> PriceHistory:
        data = await self._c.get_json(
            f"{HOST_APP}/a/getPriceHistory", params=[("id", advert_id)]
        )
        return PriceHistory.model_validate(data)

    async def infrastructure(self, advert_id: int) -> dict[str, Any]:
        return await self._c.get_json(
            f"{HOST_APP}/infrastructure/getForAdvert",
            params=[("advertId", advert_id)],
        )

    async def related(self, advert_id: int) -> list[dict[str, Any]]:
        data = await self._c.get_json(
            f"{HOST_APP}/a/getRelatedAdverts", params=[("id", advert_id)]
        )
        return data if isinstance(data, list) else []

    async def recommended_groups(self, advert_id: int) -> dict[str, Any]:
        return await self._c.get_json(
            f"{HOST_APP}/a/getRecommendedGroupAdverts",
            params=[("id", advert_id)],
        )

    async def payment_services(
        self, advert_id: int, *, source: str = "search_advert"
    ) -> dict[str, Any]:
        """Promotion products available for the advert owner (TOP / Hot / etc.).

        Read-only from a scraping perspective; we never call the write side.
        """
        return await self._c.get_json(
            f"{HOST_APP}/a/getPaymentServices",
            params=[("id", advert_id), ("source", source)],
        )

    async def useful_articles(self, advert_id: int) -> dict[str, Any]:
        """Editorial articles linked to an advert. Low-value scraping target."""
        return await self._c.get_json(
            f"{HOST_APP}/content/usefulArticlesByAdvert",
            params=[("advertId", advert_id)],
        )

    # ---------- view counts (api.krisha.kz) ----------

    async def views(self, advert_ids: list[int]) -> dict[int, ViewCount]:
        """Bulk view counts. Splits into batches of `VIEWS_BATCH`."""
        out: dict[int, ViewCount] = {}
        for i in range(0, len(advert_ids), VIEWS_BATCH):
            chunk = advert_ids[i : i + VIEWS_BATCH]
            ids_str = ",".join(str(x) for x in chunk)
            data = await self._c.get_json(
                f"{HOST_API}/ms/views/krisha/live/{ids_str}/"
            )
            payload = (data or {}).get("data") or {}
            for k, v in payload.items():
                try:
                    out[int(k)] = ViewCount.model_validate(v)
                except (ValueError, TypeError):
                    continue
        return out

    # ---------- handbooks ----------

    async def categories(self) -> dict[str, Any]:
        """All browseable categories, grouped by section.

        Returns the raw API shape: ``{"sell": {"title", "items": [...]},
        "rent": {"title", "items": [...]}}``. To iterate over all leaf
        categories regardless of section, flatten yourself:

            cats = await api.categories()
            leaves = [c for section in cats.values() for c in section["items"]]
        """
        return await self._c.get_json(f"{HOST_APP}/category/getSearchList")

    async def search_form(self, cat_id: int) -> list[dict[str, Any]]:
        """Canonical filter schema for a category."""
        return await self._c.get_json(
            f"{HOST_APP}/category/getSearchForm", params=[("id", cat_id)]
        )

    async def complexes_for_region(self, region_id: int) -> Any:
        return await self._c.get_json(
            f"{HOST_APP}/complex/getMapComplexes",
            params=[("regionId", region_id)],
        )
