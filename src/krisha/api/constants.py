"""Static credentials and hosts for the krisha.kz mobile API.

`APP_ID` / `APP_KEY` are the iOS app's static credential pair, validated
together server-side. They aren't device- or IP-bound; we send them on
every request.
"""

from __future__ import annotations

APP_ID = "827741382230"
APP_KEY = "0f886a79655ffbfff79f247d3add8ac3"

HOST_APP = "https://app.krisha.kz"
HOST_API = "https://api.krisha.kz"
HOST_CHAT = "https://chat.krisha.kz"

# Headers the real iOS app sends. All optional (probe-verified) but kept
# for parity so our traffic looks like the genuine client.
DEFAULT_HEADERS = {
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate",
    "Accept-Language": "en-KZ;q=1.0, ru-KZ;q=0.9, kk-KZ;q=0.8",
    "User-Agent": (
        "KrishaKz/26.5.19 (kz.krisha.advapp; build:1; iOS 26.4.2) "
        "Alamofire/5.9.1"
    ),
    "app-version": "26.5.19",
    "app-platform": "ios",
    "app-platform-version": "26.4.2",
    "x-app-lang": "ru",
    "x-phone-model": "iPhone17,1",
    "APP-PHOTO-FORMAT": "webp",
}

# Top-level category IDs returned by /category/getSearchList.
CATEGORY_IDS = {
    "sell.flat": 1,
    "sell.flat_layout": 52,  # new-build off-plan layouts (isLayout:true adverts)
    "rent.flat": 2,
    "rent.room": 9,
    "sell.land": 14,
    "sell.industrial": 15,
    "rent.industrial": 16,
    "rent.take": 43,
    "rent.flat_daily": 57,
    "rent.flat_hourly": 58,
    "sell.commercial": 59,
    "rent.commercial": 60,
    "sell.business": 61,
    "sell.house_dacha": 62,
    "sell.garage": 63,
    "rent.garage": 64,
    "rent.house_dacha": 65,
    "rent.house_dacha_daily": 66,
}

# Common region IDs. The mobile API doesn't expose a name→id endpoint;
# these were verified empirically by probing the listing endpoint and
# inspecting `geo_location.city` on returned adverts.
#
# Caveat: unknown geo_ids appear to fall back to Almaty server-side, so
# unmapped names should not silently use a "safe default". Add new
# entries only after confirming with a probe.
REGION_IDS = {
    "almaty": 2,
    "astana": 105,
    "karaganda": 239,
    "balkhash": 237,
}

# /v1/a/listing/search returns 20 items per page; this is hardcoded
# server-side and not configurable via `limit`.
PAGE_SIZE = 20

# Bulk view-count endpoint accepts up to ~20 ids per call.
VIEWS_BATCH = 20
