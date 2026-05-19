"""Pydantic models for krisha.kz mobile API responses.

Field coverage matches what we observed in real captures; extras are
tolerated (``model_config["extra"] = "allow"``) because the API ships
new fields without versioning.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class Photo(_Base):
    id: int | None = None
    path: str | None = None
    is_moderated: bool | None = Field(default=None, alias="isModerated")
    width: int | None = None
    height: int | None = None


class Photos(_Base):
    count: int = 0
    items: list[Photo] = Field(default_factory=list)


class Category(_Base):
    id: int | None = None
    name: str | None = None
    label: str | None = None
    url: str | None = None


class GeoLocation(_Base):
    region_id: int | None = Field(default=None, alias="regionId")
    region_alias: str | None = Field(default=None, alias="regionAlias")
    city: str | None = None
    district: str | None = None
    microdistrict: str | None = None
    street: str | None = None
    house_num: str | None = Field(default=None, alias="houseNum")
    address_title: str | None = Field(default=None, alias="addressTitle")
    map_lat: float | None = Field(default=None, alias="mapLat")
    map_lon: float | None = Field(default=None, alias="mapLon")
    map_zoom: int | None = Field(default=None, alias="mapZoom")


class Owner(_Base):
    id: int | None = None
    global_id: int | None = Field(default=None, alias="globalId")
    type: int | None = None
    name: str | None = None


class ComplexWorkTime(_Base):
    from_: str | None = Field(default=None, alias="from")
    to: str | None = None
    is_now_works: bool | None = Field(default=None, alias="isNowWorks")


class Complex(_Base):
    id: int | None = None
    name: str | None = None
    alias: str | None = None
    photo: str | None = None
    url: str | None = None
    builder: str | None = None
    work_time: ComplexWorkTime | None = Field(default=None, alias="workTime")


class AdvertSettings(_Base):
    show_text_translation: bool | None = Field(
        default=None, alias="showTextTranslation"
    )
    paywall_path: str | None = Field(default=None, alias="paywallPath")
    show_recommended_group_adverts: bool | None = Field(
        default=None, alias="showRecommendedGroupAdverts"
    )
    show_infrastructure: bool | None = Field(default=None, alias="showInfrastructure")
    show_price_analytics: bool | None = Field(
        default=None, alias="showPriceAnalytics"
    )
    favorites_enabled: bool | None = Field(default=None, alias="favoritesEnabled")


class Advert(_Base):
    id: int
    storage_id: str | None = Field(default=None, alias="storageId")
    is_layout: bool | None = Field(default=None, alias="isLayout")
    title: str | None = None
    text: str | None = None
    # `price` may come back as an int (in /v1/a/show) or a localised string
    # like "230 000" (in /a/getRelatedAdverts) — accept both.
    price: int | str | None = None
    price_title: str | None = Field(default=None, alias="priceTitle")
    price_m2: int | None = Field(default=None, alias="priceM2")
    date: str | None = None
    changed_storage_at: str | None = Field(default=None, alias="changedStorageAt")
    category: Category | None = None
    geo_location: GeoLocation | None = Field(default=None, alias="geoLocation")
    photos: Photos | None = None
    owner: Owner | None = None
    complex: Complex | None = None
    settings: AdvertSettings | None = None
    params: dict[str, Any] | None = None
    build_params: dict[str, Any] | None = Field(default=None, alias="buildParams")


class ListingItem(_Base):
    """Heterogeneous listing item.

    `kind` discriminates: `advert`, `hot` (wrapper containing nested items),
    `header` (city banner), `agent_advantages` (promo block when
    who=1+_sys.fromAgent=1).
    """

    kind: str
    model: dict[str, Any] | None = None


class ListingEnvelope(_Base):
    search_id: str | None = Field(default=None, alias="searchId")
    offset: int = 0
    limit: int = 20
    nb_total: int = Field(default=0, alias="nbTotal")
    items: list[ListingItem] = Field(default_factory=list)

    def adverts(self) -> list[Advert]:
        """Flatten items[] into a list of Advert objects.

        Skips banner items (`kind in {header, agent_advantages, ...}`)
        and descends into `kind == "hot"` wrappers.
        """
        out: list[Advert] = []
        for item in self.items:
            if item.kind == "advert" and item.model:
                out.append(Advert.model_validate(item.model))
            elif item.kind == "hot" and item.model:
                for inner in item.model.get("items") or []:
                    if inner.get("kind") == "advert" and inner.get("model"):
                        out.append(Advert.model_validate(inner["model"]))
        return out


class AveragePrices(_Base):
    """Price-per-m² benchmark for an advert vs. its city/district.

    `price_measure` is documented as `"m2"` but observed empty (`""`) in
    real responses — don't rely on it for unit display.
    """

    status: str | None = None
    city: int | None = None
    district: int | None = None
    current: int | None = None
    price_measure: str | None = Field(default=None, alias="priceMeasure")
    relative: float | None = None
    city_name: str | None = Field(default=None, alias="cityName")


class PriceHistoryPoint(_Base):
    """Shape unknown for populated responses; we keep it permissive."""

    pass


class PriceHistory(_Base):
    last_change: str | None = Field(default=None, alias="lastChange")
    is_up: bool | None = Field(default=None, alias="isUp")
    is_visible: bool = Field(default=False, alias="isVisible")
    graph_data: list[dict[str, Any]] = Field(default_factory=list, alias="graphData")
    list_data: list[dict[str, Any]] = Field(default_factory=list, alias="listData")


class ViewCount(_Base):
    """Per-advert view counts from /ms/views/krisha/live/{ids}/.

    `nb_phone_views` consistently returns 0 across all tested IDs (even
    high-traffic ones). The field is probably deprecated server-side or
    needs an auth context we don't have. Don't rely on it.
    """

    nb_views: int | None = None
    nb_phone_views: int | None = None


class Phones(_Base):
    phones: list[str] = Field(default_factory=list)
