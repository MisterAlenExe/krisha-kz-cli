from __future__ import annotations

import asyncio
import math
import sys
from typing import Annotated

import typer

from .client import KrishaClient
from .output import open_output, write_jsonl
from .parse_list import parse_listing_page, parse_total_count
from .parse_show import parse_show
from .urls import BUILDING_TYPES, SearchFilters

app = typer.Typer(
    add_completion=False,
    help="Extract real-estate listings from krisha.kz.",
    no_args_is_help=True,
)

ADS_PER_PAGE = 20  # observed: ~20 organic .a-card per page


def _parse_pages(spec: str) -> tuple[int, int | None]:
    """`"5"` → (1, 5); `"2-7"` → (2, 7); `"all"` → (1, None)."""
    spec = spec.strip().lower()
    if spec == "all":
        return 1, None
    if "-" in spec:
        a, b = spec.split("-", 1)
        return int(a), int(b)
    n = int(spec)
    return 1, n


def _parse_das_overrides(raw: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in raw:
        if "=" not in item:
            raise typer.BadParameter(f"--das expects KEY=VALUE, got {item!r}")
        k, v = item.split("=", 1)
        out[k.strip()] = v.strip()
    return out


async def _show_one(client: KrishaClient, ad_id: int):
    html = await client.get_text(f"/a/show/{ad_id}")
    return parse_show(html, ad_id)


@app.command()
def show(
    ad_id: Annotated[int, typer.Argument(help="Krisha advert ID (e.g. 1009233693)")],
    output: Annotated[
        str, typer.Option("--output", "-o", help="Output file (default: stdout)")
    ] = "-",
    timeout: Annotated[float, typer.Option(help="HTTP timeout (s)")] = 20.0,
) -> None:
    """Fetch one advert by ID and emit its full structured JSON record."""

    async def run() -> int:
        async with KrishaClient(concurrency=1, timeout=timeout) as client:
            ad = await _show_one(client, ad_id)
            with open_output(output) as out:
                write_jsonl(out, ad)
        return 0

    raise typer.Exit(asyncio.run(run()))


@app.command()
def search(
    target: Annotated[
        str,
        typer.Argument(
            help="<section>/<category>, e.g. prodazha/kvartiry or arenda/kvartiry"
        ),
    ],
    city: Annotated[str, typer.Option(help="City slug (almaty, astana, …)")] = "almaty",
    rooms: Annotated[
        list[int] | None,
        typer.Option("--rooms", help="Room count (repeatable)"),
    ] = None,
    price_from: Annotated[int | None, typer.Option("--price-from")] = None,
    price_to: Annotated[int | None, typer.Option("--price-to")] = None,
    square_from: Annotated[float | None, typer.Option("--square-from")] = None,
    square_to: Annotated[float | None, typer.Option("--square-to")] = None,
    year_from: Annotated[int | None, typer.Option("--year-from")] = None,
    year_to: Annotated[int | None, typer.Option("--year-to")] = None,
    floor_from: Annotated[int | None, typer.Option("--floor-from")] = None,
    floor_to: Annotated[int | None, typer.Option("--floor-to")] = None,
    building: Annotated[
        list[str] | None,
        typer.Option(
            "--building",
            help=f"Building type (repeatable). One of: {', '.join(BUILDING_TYPES)}",
        ),
    ] = None,
    has_photo: Annotated[bool, typer.Option("--has-photo")] = False,
    new_build: Annotated[bool, typer.Option("--new-build")] = False,
    from_owner: Annotated[bool, typer.Option("--from-owner")] = False,
    from_agent: Annotated[bool, typer.Option("--from-agent")] = False,
    mortgage: Annotated[
        bool | None,
        typer.Option("--mortgage/--no-mortgage", help="Filter by mortgage availability"),
    ] = None,
    floor_not_first: Annotated[bool, typer.Option("--floor-not-first")] = False,
    floor_not_last: Annotated[bool, typer.Option("--floor-not-last")] = False,
    das: Annotated[
        list[str] | None,
        typer.Option(
            "--das",
            help="Raw das override, e.g. --das flat.toilet=2 (repeatable).",
        ),
    ] = None,
    pages: Annotated[
        str, typer.Option("--pages", help="Page range: '5', '2-7', or 'all'.")
    ] = "1",
    concurrency: Annotated[int, typer.Option("--concurrency", "-c")] = 16,
    enrich: Annotated[
        bool,
        typer.Option(
            "--enrich",
            help="Fetch /a/show/{id} for each hit and merge full ad details.",
        ),
    ] = False,
    output: Annotated[str, typer.Option("--output", "-o")] = "-",
    retries: Annotated[int, typer.Option(help="HTTP retries per request")] = 3,
    timeout: Annotated[float, typer.Option(help="HTTP timeout (s)")] = 20.0,
) -> None:
    """Run a paginated krisha search and emit one JSONL record per listing.

    Examples:

        krisha search prodazha/kvartiry --city almaty --rooms 2 \\
            --price-from 20000000 --price-to 40000000 --pages 1-5

        krisha search arenda/kvartiry --city astana --has-photo --pages all
    """
    if "/" not in target:
        raise typer.BadParameter("TARGET must be '<section>/<category>'")
    section, category = target.split("/", 1)
    if section not in {"prodazha", "arenda"}:
        raise typer.BadParameter("section must be 'prodazha' or 'arenda'")

    for b in building or []:
        if b not in BUILDING_TYPES:
            raise typer.BadParameter(
                f"--building must be one of {sorted(BUILDING_TYPES)}; got {b!r}"
            )

    filters = SearchFilters(
        section=section,
        category=category,
        city=city,
        rooms=rooms or [],
        price_from=price_from,
        price_to=price_to,
        square_from=square_from,
        square_to=square_to,
        year_from=year_from,
        year_to=year_to,
        floor_from=floor_from,
        floor_to=floor_to,
        building=building or [],
        has_photo=has_photo,
        new_build=new_build,
        from_owner=from_owner,
        from_agent=from_agent,
        mortgage=mortgage,
        floor_not_first=floor_not_first,
        floor_not_last=floor_not_last,
        extra_das=_parse_das_overrides(das or []),
    )

    start_page, end_page = _parse_pages(pages)

    async def run() -> int:
        emitted = 0
        async with KrishaClient(concurrency=concurrency, retries=retries, timeout=timeout) as client:
            # First page tells us how many to fetch under --pages all
            first_url = filters.page_url(start_page)
            html = await client.get_text(first_url)
            cards = parse_listing_page(html, start_page)

            resolved_end = end_page
            if resolved_end is None:
                total = parse_total_count(html)
                resolved_end = (
                    math.ceil(total / ADS_PER_PAGE) if total else start_page
                )
                print(
                    f"[search] {total or '?'} matches; fetching pages {start_page}-{resolved_end}",
                    file=sys.stderr,
                )

            with open_output(output) as out:

                async def emit(card_records: list) -> int:
                    if enrich and card_records:
                        details = await asyncio.gather(
                            *(_show_one(client, c.id) for c in card_records),
                            return_exceptions=True,
                        )
                        n = 0
                        for card, detail in zip(card_records, details):
                            if isinstance(detail, Exception):
                                print(
                                    f"[enrich] id={card.id} error={detail!r}",
                                    file=sys.stderr,
                                )
                                write_jsonl(out, card)
                            else:
                                merged = {**detail.model_dump(mode="json"), "page": card.page}
                                write_jsonl(out, merged)
                            n += 1
                        return n
                    for c in card_records:
                        write_jsonl(out, c)
                    return len(card_records)

                emitted += await emit(cards)

                # Remaining pages concurrently
                remaining = list(range(start_page + 1, resolved_end + 1))
                if remaining:
                    htmls = await asyncio.gather(
                        *(client.get_text(filters.page_url(p)) for p in remaining),
                        return_exceptions=True,
                    )
                    for p, page_html in zip(remaining, htmls):
                        if isinstance(page_html, Exception):
                            print(
                                f"[search] page={p} error={page_html!r}",
                                file=sys.stderr,
                            )
                            continue
                        page_cards = parse_listing_page(page_html, p)
                        if not page_cards:
                            continue
                        emitted += await emit(page_cards)

        print(f"[search] emitted {emitted} records", file=sys.stderr)
        return 0 if emitted else 1

    raise typer.Exit(asyncio.run(run()))


if __name__ == "__main__":
    app()
