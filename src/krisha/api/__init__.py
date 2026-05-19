"""Thin client for the krisha.kz mobile JSON API.

This is the supported path for new code. The HTML-scraping modules
(`krisha.client`, `krisha.parse_list`, `krisha.parse_show`, `krisha.urls`)
are kept on disk for reference but no longer wired into the CLI.

The endpoint catalogue is documented in `krisha-kz-openapi.yaml`
(local reference only; gitignored).
"""

from __future__ import annotations

from .client import ApiClient
from .endpoints import KrishaApi
from .models import (
    Advert,
    AveragePrices,
    Category,
    Complex,
    GeoLocation,
    ListingEnvelope,
    Owner,
    Photo,
    PriceHistory,
)
from .search import SearchFilters

__all__ = [
    "Advert",
    "ApiClient",
    "AveragePrices",
    "Category",
    "Complex",
    "GeoLocation",
    "KrishaApi",
    "ListingEnvelope",
    "Owner",
    "Photo",
    "PriceHistory",
    "SearchFilters",
]
