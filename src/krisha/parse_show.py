from __future__ import annotations

import re

import orjson
from selectolax.parser import HTMLParser

from .models import AdAddress, AdCategory, AdCoords, AdDetail, AdSeller

_FLOOR_RE = re.compile(r"(\d+)\s*из\s*(\d+)")
_INT_RE = re.compile(r"\d+")


def _extract_json_blob(html: str, marker: str) -> dict | None:
    """Find `marker = {…};` and return the parsed object.

    The JSON contains nested braces, so we can't use a non-greedy regex;
    we locate the opening `{` after the marker and walk forward, counting
    braces while respecting string literals.
    """
    idx = html.find(marker)
    if idx == -1:
        return None
    start = html.find("{", idx)
    if start == -1:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(html)):
        ch = html[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return orjson.loads(html[start : i + 1])
                except orjson.JSONDecodeError:
                    return None
    return None


def _text(node) -> str:
    return node.text(separator=" ", strip=True) if node else ""


def parse_show(html: str, ad_id: int) -> AdDetail:
    tree = HTMLParser(html)
    window_data = _extract_json_blob(html, "window.data") or {}
    digital_data = _extract_json_blob(html, "window.digitalData") or {}

    advert = window_data.get("advert") or {}
    product = (digital_data.get("product") or {}) if isinstance(digital_data, dict) else {}

    address_obj = advert.get("address") or {}
    map_obj = advert.get("map") or {}
    coords = (
        AdCoords(lat=map_obj["lat"], lon=map_obj["lon"])
        if isinstance(map_obj, dict) and "lat" in map_obj and "lon" in map_obj
        else None
    )

    title = advert.get("title") or _text(tree.css_first("div.offer__advert-title h1")) or None

    characteristics: dict[str, str] = {}
    for item in tree.css(".offer__info-item"):
        label_node = item.css_first(".offer__info-title")
        value_node = item.css_first(".offer__advert-short-info")
        if not label_node or not value_node:
            continue
        label = label_node.text(strip=True)
        value = value_node.text(separator=" ", strip=True)
        if label and value:
            characteristics[label] = value

    floor_str = characteristics.get("Этаж", "")
    floor, floors_total = None, None
    if m := _FLOOR_RE.search(floor_str):
        floor, floors_total = int(m.group(1)), int(m.group(2))

    year_str = characteristics.get("Год постройки", "")
    year_built = int(m.group(0)) if (m := _INT_RE.search(year_str)) else None

    description_node = tree.css_first(".js-description, .text, .a-text-white-spaces")
    description = description_node.text(separator="\n", strip=True) if description_node else None

    photos = [p["src"] for p in (advert.get("photos") or []) if isinstance(p, dict) and p.get("src")]

    seller_obj = product.get("seller") if isinstance(product, dict) else None
    if isinstance(seller_obj, dict):
        seller = AdSeller(
            id=seller_obj.get("id"),
            name=seller_obj.get("name"),
            type=seller_obj.get("type"),
            is_verified=seller_obj.get("isChecked"),
        )
    else:
        seller = AdSeller()

    return AdDetail(
        id=advert.get("id") or ad_id,
        url=f"https://krisha.kz/a/show/{advert.get('id') or ad_id}",
        title=title,
        price_kzt=advert.get("price"),
        rooms=advert.get("rooms"),
        square_m2=advert.get("square"),
        floor=floor,
        floors_total=floors_total,
        address=AdAddress(
            country=address_obj.get("country"),
            city=address_obj.get("city"),
            district=address_obj.get("district"),
            microdistrict=address_obj.get("microdistrict"),
            street=address_obj.get("street"),
        ),
        coords=coords,
        complex_id=advert.get("complexId") or None,
        complex_name=characteristics.get("Жилой комплекс"),
        building_type=characteristics.get("Тип дома"),
        year_built=year_built,
        condition=characteristics.get("Состояние квартиры"),
        characteristics=characteristics,
        description=description,
        photos=photos,
        seller=seller,
        category=AdCategory(
            section=advert.get("sectionAlias") or product.get("offerType"),
            object=advert.get("categoryAlias") or product.get("objectType"),
            category_id=advert.get("categoryId"),
        ),
    )
