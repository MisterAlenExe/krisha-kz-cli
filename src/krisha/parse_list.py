from __future__ import annotations

import re

from selectolax.parser import HTMLParser, Node

from .models import ListingCard

_TITLE_RE = re.compile(
    r"(?P<rooms>\d+)\s*-?комнатн\w*\s*квартир\w*"
    r"(?:.*?(?P<square>\d+(?:[.,]\d+)?)\s*м²)?"
    r"(?:.*?(?P<floor>\d+)\s*/\s*(?P<floors>\d+)\s*этаж)?",
    re.IGNORECASE,
)
_PRICE_RE = re.compile(r"\d+")
_COUNT_RE = re.compile(r"[\d\s]+")
_TOTAL_RE = re.compile(r"a-search-subtitle[\s\S]{0,200}?Найдено[^<]*<[^>]+>\s*([\d\s\xa0]+)\s*<", re.IGNORECASE)


def _text(node: Node | None) -> str | None:
    if not node:
        return None
    t = node.text(separator=" ", strip=True)
    return t or None


def _to_int(s: str | None) -> int | None:
    if not s:
        return None
    digits = "".join(ch for ch in s if ch.isdigit())
    return int(digits) if digits else None


def parse_total_count(html: str) -> int | None:
    """How many ads match the current search (for `--pages all`)."""
    m = _TOTAL_RE.search(html)
    if not m:
        return None
    return _to_int(m.group(1))


def parse_listing_page(html: str, page: int) -> list[ListingCard]:
    tree = HTMLParser(html)
    out: list[ListingCard] = []
    for card in tree.css("div.a-card"):
        raw_id = card.attributes.get("data-id")
        if not raw_id or not raw_id.isdigit():
            continue
        ad_id = int(raw_id)

        title = _text(card.css_first(".a-card__title"))
        price = _text(card.css_first(".a-card__price"))
        subtitle = _text(card.css_first(".a-card__subtitle"))
        preview = _text(card.css_first(".a-card__text-preview"))
        stat_items = [
            (s.text(strip=True) or "") for s in card.css(".a-card__stats-item")
        ]
        stat_items = [s for s in stat_items if s]
        img = card.css_first("img")
        photo = None
        if img:
            attrs = img.attributes
            photo = attrs.get("data-src") or attrs.get("src")

        rooms, square, floor, floors_total = None, None, None, None
        if title and (m := _TITLE_RE.search(title)):
            rooms = int(m.group("rooms")) if m.group("rooms") else None
            sq = m.group("square")
            if sq:
                square = float(sq.replace(",", "."))
            if m.group("floor"):
                floor = int(m.group("floor"))
            if m.group("floors"):
                floors_total = int(m.group("floors"))

        # The third stats-item (view counter) is populated client-side via
        # /ms/views/..., so it's empty in the server-rendered HTML. We only
        # record what's present.
        city = stat_items[0] if len(stat_items) > 0 else None
        posted_at = stat_items[1] if len(stat_items) > 1 else None
        views = _to_int(stat_items[2]) if len(stat_items) > 2 else None

        district, address = None, None
        if subtitle:
            chunks = [c.strip() for c in subtitle.split(",", 1)]
            district = chunks[0] if chunks else None
            address = chunks[1].strip() if len(chunks) > 1 else None

        out.append(
            ListingCard(
                id=ad_id,
                url=f"https://krisha.kz/a/show/{ad_id}",
                title=title,
                price_kzt=_to_int(price),
                rooms=rooms,
                square_m2=square,
                floor=floor,
                floors_total=floors_total,
                city=city,
                district=district,
                address=address,
                description_preview=preview,
                photo=photo,
                posted_at=posted_at,
                views=views,
                page=page,
            )
        )
    return out
