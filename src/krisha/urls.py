"""Filter → krisha URL mapping.

Listings live at:
    /{section}/{category}/{city}/?das[KEY]=VALUE&page=N

`das[...]` parameter names come from the search form on the live site
(see PLAN.md for the full inventory). We expose a curated, typed subset
and a `--das KEY=VALUE` escape hatch for the rest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlencode

BUILDING_TYPES = {
    "brick": "1",
    "panel": "2",
    "monolith": "3",
    "other": "0",
}


@dataclass
class SearchFilters:
    section: str  # "prodazha" | "arenda"
    category: str  # "kvartiry" | "doma-dachi" | …
    city: str = "almaty"
    rooms: list[int] = field(default_factory=list)
    price_from: int | None = None
    price_to: int | None = None
    square_from: float | None = None
    square_to: float | None = None
    year_from: int | None = None
    year_to: int | None = None
    floor_from: int | None = None
    floor_to: int | None = None
    building: list[str] = field(default_factory=list)
    has_photo: bool = False
    new_build: bool = False
    from_owner: bool = False
    from_agent: bool = False
    mortgage: bool | None = None
    floor_not_first: bool = False
    floor_not_last: bool = False
    extra_das: dict[str, str] = field(default_factory=dict)

    def base_path(self) -> str:
        return f"/{self.section}/{self.category}/{self.city}/"

    def das_params(self) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for r in self.rooms:
            out.append(("das[live.rooms]", str(r)))
        if self.price_from is not None:
            out.append(("das[price][from]", str(self.price_from)))
        if self.price_to is not None:
            out.append(("das[price][to]", str(self.price_to)))
        if self.square_from is not None:
            out.append(("das[live.square][from]", _fmt_num(self.square_from)))
        if self.square_to is not None:
            out.append(("das[live.square][to]", _fmt_num(self.square_to)))
        if self.year_from is not None:
            out.append(("das[house.year][from]", str(self.year_from)))
        if self.year_to is not None:
            out.append(("das[house.year][to]", str(self.year_to)))
        if self.floor_from is not None:
            out.append(("das[flat.floor][from]", str(self.floor_from)))
        if self.floor_to is not None:
            out.append(("das[flat.floor][to]", str(self.floor_to)))
        for b in self.building:
            code = BUILDING_TYPES.get(b)
            if code is not None:
                out.append(("das[flat.building]", code))
        if self.has_photo:
            out.append(("das[_sys.hasphoto]", "1"))
        if self.new_build:
            out.append(("das[novostroiki]", "1"))
        if self.from_owner:
            out.append(("das[who]", "1"))
        if self.from_agent:
            out.append(("das[_sys.fromAgent]", "1"))
        if self.mortgage is True:
            out.append(("das[mortgage]", "1"))
        elif self.mortgage is False:
            out.append(("das[mortgage]", "0"))
        if self.floor_not_first:
            out.append(("das[floor_not_first]", "1"))
        if self.floor_not_last:
            out.append(("das[floor_not_last]", "1"))
        for k, v in self.extra_das.items():
            key = k if k.startswith("das[") else f"das[{k}]"
            out.append((key, v))
        return out

    def page_url(self, page: int) -> str:
        params = list(self.das_params())
        if page > 1:
            params.append(("page", str(page)))
        qs = urlencode(params, safe="[]")
        return f"{self.base_path()}?{qs}" if qs else self.base_path()


def _fmt_num(n: float) -> str:
    return str(int(n)) if n == int(n) else str(n)
