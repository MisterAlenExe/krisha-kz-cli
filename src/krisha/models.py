from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ListingCard(BaseModel):
    id: int
    url: str
    title: str | None = None
    price_kzt: int | None = None
    rooms: int | None = None
    square_m2: float | None = None
    floor: int | None = None
    floors_total: int | None = None
    city: str | None = None
    district: str | None = None
    address: str | None = None
    description_preview: str | None = None
    photo: str | None = None
    posted_at: str | None = None
    views: int | None = None
    page: int | None = None
    scraped_at: str = Field(default_factory=_utc_now)


class AdAddress(BaseModel):
    country: str | None = None
    city: str | None = None
    district: str | None = None
    microdistrict: str | None = None
    street: str | None = None


class AdCoords(BaseModel):
    lat: float
    lon: float


class AdSeller(BaseModel):
    id: int | None = None
    name: str | None = None
    type: str | None = None
    is_verified: bool | None = None


class AdCategory(BaseModel):
    section: str | None = None
    object: str | None = None
    category_id: int | None = None


class AdDetail(BaseModel):
    id: int
    url: str
    title: str | None = None
    price_kzt: int | None = None
    rooms: int | None = None
    square_m2: float | None = None
    floor: int | None = None
    floors_total: int | None = None
    address: AdAddress = Field(default_factory=AdAddress)
    coords: AdCoords | None = None
    complex_id: int | None = None
    complex_name: str | None = None
    building_type: str | None = None
    year_built: int | None = None
    condition: str | None = None
    characteristics: dict[str, str] = Field(default_factory=dict)
    description: str | None = None
    photos: list[str] = Field(default_factory=list)
    seller: AdSeller = Field(default_factory=AdSeller)
    category: AdCategory = Field(default_factory=AdCategory)
    scraped_at: str = Field(default_factory=_utc_now)
