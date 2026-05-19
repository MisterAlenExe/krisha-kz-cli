"""Build mobile-API query strings.

The mobile API uses repeated-key URL encoding (e.g.
`query[data][map.geo_id][]=106&query[data][map.geo_id][]=2726`) so we
emit a list-of-tuples rather than a dict.

Filter vocabulary comes from `/category/getSearchForm?id={catId}`. The
fields here cover apartment search (catId 1 / 2). For categories with
their own namespace (e.g. commercial uses `com.*`), pass values via
`extra` until/unless we extend this dataclass.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Building-type enum values from getSearchForm (1=панель, 2=кирпич,
# 3=монолит — exact mapping not officially confirmed; matches the
# UI ordering observed in the iOS picker).
BUILDING_TYPES = {
    "panel": "1",
    "brick": "2",
    "monolith": "3",
    "other": "0",
}


@dataclass
class SearchFilters:
    """Typed filter set → mobile query-string params.

    Pass `extra` for any key not covered explicitly (the `--das` escape
    hatch). Use the canonical mobile name, e.g.
    ``extra={"query[data][flat.toilet][]": "2"}``.
    """

    cat_id: int
    common_region_id: int = 105  # 105 = Almaty
    # geographic narrowing via map.geo_id[] (district / microdistrict ids).
    geo_ids: list[int] = field(default_factory=list)
    # rooms: rendered as live.rooms[or][N] — pass a list.
    rooms: list[int] = field(default_factory=list)
    price_from: int | None = None
    price_to: int | None = None
    square_from: float | None = None
    square_to: float | None = None
    year_from: int | None = None
    year_to: int | None = None
    floor_from: int | None = None
    floor_to: int | None = None
    house_floors_from: int | None = None  # min storeys in building
    house_floors_to: int | None = None
    building: list[str] = field(default_factory=list)  # see BUILDING_TYPES
    renovation: list[int] = field(default_factory=list)  # flat.renovation[]
    toilet: list[int] = field(default_factory=list)  # flat.toilet[]
    floor_custom: list[int] = field(default_factory=list)  # 1=not first, 2=not last
    has_photo: bool = False
    new_build: bool = False
    from_owner: bool = False
    from_agent: bool = False
    mortgage: bool | None = None
    has_change: bool = False
    text: str | None = None
    extra: dict[str, str] = field(default_factory=dict)

    def listing_params(
        self,
        *,
        offset: int = 0,
        limit: int = 20,
        order_by: str = "add_date",
        sort: str = "desc",
        screen: str = "filter",
        is_pagination: int = 0,
    ) -> list[tuple[str, Any]]:
        """Params for /v1/a/listing/search.

        order_by `"hot"` automatically switches to the `orderBy[system_data]`
        namespace and uppercase `DESC` that the API requires.
        """
        p: list[tuple[str, Any]] = [
            ("catId", self.cat_id),
            ("commonRegionId", self.common_region_id),
            ("offset", offset),
            ("limit", limit),
            ("isPagination", is_pagination),
            ("withAdverts", 1),
            ("screen", screen),
        ]
        if order_by == "hot":
            p.append(("orderBy[system_data][0][name]", "hot"))
            p.append(("orderBy[system_data][0][sort]", sort.upper()))
        else:
            p.append(("orderBy[data][0][name]", order_by))
            p.append(("orderBy[data][0][sort]", sort.lower()))
        p.extend(self._query_data())
        return p

    def meta_params(self) -> list[tuple[str, Any]]:
        """Params for /v1/a/search/meta (count oracle)."""
        return [
            ("catId", self.cat_id),
            ("commonRegionId", self.common_region_id),
            *self._query_data(),
        ]

    def _query_data(self) -> list[tuple[str, Any]]:
        p: list[tuple[str, Any]] = []
        # `commonRegionId` is metadata-only — the server ignores it for geo
        # filtering. Without an explicit `map.geo_id[]`, results span all of
        # Kazakhstan. Default to the region itself so `--region almaty` actually
        # narrows to Almaty.
        geo_ids = self.geo_ids or [self.common_region_id]
        for gid in geo_ids:
            p.append(("query[data][map.geo_id][]", gid))
        for r in self.rooms:
            p.append(("query[data][live.rooms][or][]", r))
        if self.price_from is not None:
            p.append(("query[data][_sys.price-2][from]", self.price_from))
        if self.price_to is not None:
            p.append(("query[data][_sys.price-2][to]", self.price_to))
        if self.square_from is not None:
            p.append(("query[data][live.square][from]", _num(self.square_from)))
        if self.square_to is not None:
            p.append(("query[data][live.square][to]", _num(self.square_to)))
        if self.year_from is not None:
            p.append(("query[data][house.year][from]", self.year_from))
        if self.year_to is not None:
            p.append(("query[data][house.year][to]", self.year_to))
        if self.floor_from is not None:
            p.append(("query[data][flat.floor][from]", self.floor_from))
        if self.floor_to is not None:
            p.append(("query[data][flat.floor][to]", self.floor_to))
        if self.house_floors_from is not None:
            p.append(("query[data][house.floor_num][from]", self.house_floors_from))
        if self.house_floors_to is not None:
            p.append(("query[data][house.floor_num][to]", self.house_floors_to))
        for b in self.building:
            code = BUILDING_TYPES.get(b)
            if code is not None:
                p.append(("query[data][flat.building][]", code))
        for v in self.renovation:
            p.append(("query[data][flat.renovation][]", v))
        for v in self.toilet:
            p.append(("query[data][flat.toilet][]", v))
        for v in self.floor_custom:
            p.append(("query[data][floor_custom][]", v))
        if self.has_photo:
            p.append(("query[data][_sys.hasphoto]", 1))
        if self.new_build:
            p.append(("query[data][novostroiki]", 1))
        if self.from_owner:
            p.append(("query[data][who]", 1))
        if self.from_agent:
            p.append(("query[data][_sys.fromAgent]", 1))
        if self.mortgage is True:
            p.append(("query[data][mortgage]", 1))
        elif self.mortgage is False:
            p.append(("query[data][mortgage]", 0))
        if self.has_change:
            p.append(("query[data][has_change]", 1))
        if self.text:
            p.append(("text", self.text))
        for k, v in self.extra.items():
            p.append((_extra_key(k), v))
        return p


_EXTRA_KEY_RE = re.compile(r"^([^\[]+)(\[.*)?$")


def _extra_key(k: str) -> str:
    """Normalize a user-supplied --extra key into a full query-string key.

    Examples:
        flat.toilet          → query[data][flat.toilet]
        flat.toilet[]        → query[data][flat.toilet][]      (array form)
        house.year[from]     → query[data][house.year][from]   (range form)
        query[data][...]     → unchanged
    """
    if k.startswith("query["):
        return k
    m = _EXTRA_KEY_RE.match(k)
    if not m:
        return f"query[data][{k}]"
    base, suffix = m.group(1), m.group(2) or ""
    return f"query[data][{base}]{suffix}"


def _num(n: float) -> str:
    return str(int(n)) if n == int(n) else str(n)
