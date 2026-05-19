from __future__ import annotations

import asyncio
import math
import sys
from typing import Annotated

import httpx
import typer

from .api import ApiClient, KrishaApi, SearchFilters
from .api.constants import CATEGORY_IDS, PAGE_SIZE, REGION_IDS
from .api.search import BUILDING_TYPES
from .output import open_output, write_jsonl


def _run(coro) -> int:
    """Run an async CLI handler with clean error reporting.

    Turns common HTTP/network errors into one-line stderr messages
    instead of dumping a full Python traceback.
    """
    try:
        return asyncio.run(coro)
    except httpx.HTTPStatusError as e:
        print(
            f"error: {e.response.status_code} {e.response.reason_phrase} "
            f"for {e.request.url}",
            file=sys.stderr,
        )
        return 1
    except httpx.HTTPError as e:
        print(f"error: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

app = typer.Typer(
    add_completion=False,
    help="Extract real-estate listings from krisha.kz via the mobile JSON API.",
    no_args_is_help=True,
)


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


def _parse_extras(raw: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in raw:
        if "=" not in item:
            raise typer.BadParameter(f"--extra expects KEY=VALUE, got {item!r}")
        k, v = item.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _resolve_cat_id(target: str) -> int:
    """Accept either a numeric id ("1") or a name ("sell.flat")."""
    target = target.strip()
    if target.isdigit():
        return int(target)
    if target not in CATEGORY_IDS:
        known = ", ".join(sorted(CATEGORY_IDS))
        raise typer.BadParameter(f"unknown category {target!r}. Known: {known}")
    return CATEGORY_IDS[target]


def _resolve_region_id(region: str) -> int:
    region = region.strip().lower()
    if region.isdigit():
        return int(region)
    if region not in REGION_IDS:
        known = ", ".join(sorted(REGION_IDS))
        raise typer.BadParameter(f"unknown region {region!r}. Known: {known}")
    return REGION_IDS[region]


# ----- shared rate-limit/networking flags ---------------------------------

ConcurrencyOpt = Annotated[
    int,
    typer.Option(
        "--concurrency",
        "-c",
        min=1,
        max=16,
        help="Max in-flight requests (default 2; raise carefully).",
    ),
]
MinIntervalOpt = Annotated[
    float,
    typer.Option(
        "--min-interval",
        min=0.0,
        help="Minimum gap between request starts, in seconds (±30%% jitter).",
    ),
]
RetriesOpt = Annotated[int, typer.Option("--retries", help="HTTP retries per request")]
TimeoutOpt = Annotated[float, typer.Option("--timeout", help="HTTP timeout (s)")]
ProxyOpt = Annotated[
    str | None,
    typer.Option(
        "--proxy",
        help="HTTP/SOCKS proxy URL (also reads KRISHA_PROXY / HTTPS_PROXY).",
    ),
]


@app.command()
def show(
    ad_id: Annotated[int, typer.Argument(help="Krisha advert ID (e.g. 1009233693)")],
    output: Annotated[
        str, typer.Option("--output", "-o", help="Output file (default: stdout)")
    ] = "-",
    min_interval: MinIntervalOpt = 1.0,
    retries: RetriesOpt = 4,
    timeout: TimeoutOpt = 30.0,
    proxy: ProxyOpt = None,
) -> None:
    """Fetch one advert by ID and emit its full JSON record."""

    async def run() -> int:
        async with ApiClient(
            concurrency=1,
            min_interval=min_interval,
            retries=retries,
            timeout=timeout,
            proxy=proxy,
        ) as client:
            api = KrishaApi(client)
            ad = await api.show(ad_id)
            with open_output(output) as out:
                write_jsonl(out, ad)
        return 0

    raise typer.Exit(_run(run()))


@app.command()
def search(
    category: Annotated[
        str,
        typer.Argument(
            help="Category id or name (sell.flat, rent.flat, sell.house_dacha, ...).",
        ),
    ],
    region: Annotated[
        str,
        typer.Option("--region", help="Region id or name (almaty, astana, ...)."),
    ] = "almaty",
    geo_id: Annotated[
        list[int] | None,
        typer.Option("--geo-id", help="District / microdistrict id (repeatable)."),
    ] = None,
    rooms: Annotated[
        list[int] | None,
        typer.Option("--rooms", help="Room count (repeatable)."),
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
    renovation: Annotated[
        list[int] | None,
        typer.Option("--renovation", help="flat.renovation value (repeatable)."),
    ] = None,
    has_photo: Annotated[bool, typer.Option("--has-photo")] = False,
    new_build: Annotated[bool, typer.Option("--new-build")] = False,
    from_owner: Annotated[
        bool,
        typer.Option(
            "--from-owner",
            help=(
                "Exclude type-2 agents. Note: 'builder' accounts (e.g. БИ "
                "Group sellers) are kept — this is NOT a private-individual-"
                "only filter."
            ),
        ),
    ] = False,
    from_agent: Annotated[bool, typer.Option("--from-agent")] = False,
    mortgage: Annotated[
        bool | None,
        typer.Option("--mortgage/--no-mortgage", help="Filter by mortgage availability"),
    ] = None,
    floor_not_first: Annotated[bool, typer.Option("--floor-not-first")] = False,
    floor_not_last: Annotated[bool, typer.Option("--floor-not-last")] = False,
    text: Annotated[
        str | None, typer.Option("--text", help="Free-text query.")
    ] = None,
    extra: Annotated[
        list[str] | None,
        typer.Option(
            "--extra",
            help="Raw filter override, e.g. --extra flat.toilet=2 (repeatable).",
        ),
    ] = None,
    order_by: Annotated[
        str,
        typer.Option("--order-by", help="add_date | _sys.price-2 | hot"),
    ] = "add_date",
    sort: Annotated[str, typer.Option("--sort", help="asc | desc")] = "desc",
    pages: Annotated[
        str, typer.Option("--pages", help="Page range: '5', '2-7', or 'all'.")
    ] = "1",
    enrich: Annotated[
        bool,
        typer.Option(
            "--enrich",
            help=(
                "Fetch full /v1/a/show for each hit. Adds analytics, "
                "params.groups, build_params.groups; drops list-only fields "
                "(activePaidPackages, cardType, identification, specialOffers)."
            ),
        ),
    ] = False,
    output: Annotated[str, typer.Option("--output", "-o")] = "-",
    concurrency: ConcurrencyOpt = 2,
    min_interval: MinIntervalOpt = 1.0,
    retries: RetriesOpt = 4,
    timeout: TimeoutOpt = 30.0,
    proxy: ProxyOpt = None,
) -> None:
    """Run a paginated search and emit one JSONL record per listing.

    Examples:

        krisha search sell.flat --region almaty --rooms 2 \\
            --price-from 20000000 --price-to 40000000 --pages 1-5

        krisha search rent.flat --region astana --has-photo --pages all
    """
    floor_custom: list[int] = []
    if floor_not_first:
        floor_custom.append(1)
    if floor_not_last:
        floor_custom.append(2)

    for b in building or []:
        if b not in BUILDING_TYPES:
            raise typer.BadParameter(
                f"--building must be one of {sorted(BUILDING_TYPES)}; got {b!r}"
            )

    filters = SearchFilters(
        cat_id=_resolve_cat_id(category),
        common_region_id=_resolve_region_id(region),
        geo_ids=geo_id or [],
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
        renovation=renovation or [],
        floor_custom=floor_custom,
        has_photo=has_photo,
        new_build=new_build,
        from_owner=from_owner,
        from_agent=from_agent,
        mortgage=mortgage,
        text=text,
        extra=_parse_extras(extra or []),
    )

    start_page, end_page = _parse_pages(pages)

    async def run() -> int:
        emitted = 0
        async with ApiClient(
            concurrency=concurrency,
            retries=retries,
            timeout=timeout,
            min_interval=min_interval,
            proxy=proxy,
        ) as client:
            api = KrishaApi(client)

            first = await api.listing_search(
                filters,
                offset=(start_page - 1) * PAGE_SIZE,
                limit=PAGE_SIZE,
                order_by=order_by,
                sort=sort,
            )
            resolved_end = end_page
            if resolved_end is None:
                resolved_end = (
                    math.ceil(first.nb_total / PAGE_SIZE) if first.nb_total else start_page
                )
                print(
                    f"[search] {first.nb_total} matches; fetching pages "
                    f"{start_page}-{resolved_end} (concurrency={concurrency}, "
                    f"min-interval={min_interval}s)",
                    file=sys.stderr,
                )

            with open_output(output) as out:

                async def emit(envelope) -> int:
                    ads = envelope.adverts()
                    if enrich and ads:
                        details = await asyncio.gather(
                            *(api.show(a.id) for a in ads),
                            return_exceptions=True,
                        )
                        n = 0
                        for ad, detail in zip(ads, details):
                            if isinstance(detail, Exception):
                                print(
                                    f"[enrich] id={ad.id} error={detail!r}",
                                    file=sys.stderr,
                                )
                                write_jsonl(out, ad)
                            else:
                                write_jsonl(out, detail)
                            n += 1
                        return n
                    for a in ads:
                        write_jsonl(out, a)
                    return len(ads)

                emitted += await emit(first)

                remaining = list(range(start_page + 1, resolved_end + 1))
                if remaining:
                    envelopes = await asyncio.gather(
                        *(
                            api.listing_search(
                                filters,
                                offset=(p - 1) * PAGE_SIZE,
                                limit=PAGE_SIZE,
                                order_by=order_by,
                                sort=sort,
                            )
                            for p in remaining
                        ),
                        return_exceptions=True,
                    )
                    for p, env in zip(remaining, envelopes):
                        if isinstance(env, Exception):
                            print(f"[search] page={p} error={env!r}", file=sys.stderr)
                            continue
                        emitted += await emit(env)

        print(f"[search] emitted {emitted} records", file=sys.stderr)
        return 0 if emitted else 1

    raise typer.Exit(_run(run()))


@app.command()
def phone(
    ad_id: Annotated[int, typer.Argument(help="Krisha advert ID")],
    output: Annotated[str, typer.Option("--output", "-o")] = "-",
    min_interval: MinIntervalOpt = 1.0,
    proxy: ProxyOpt = None,
) -> None:
    """Reveal the seller's phone number(s) for one advert."""

    async def run() -> int:
        async with ApiClient(
            concurrency=1, min_interval=min_interval, proxy=proxy
        ) as client:
            api = KrishaApi(client)
            phones = await api.phones(ad_id)
            with open_output(output) as out:
                write_jsonl(out, {"id": ad_id, "phones": phones.phones})
        return 0

    raise typer.Exit(_run(run()))


@app.command()
def views(
    ad_ids: Annotated[
        list[int],
        typer.Argument(help="One or more advert IDs (batched 20 per call)."),
    ],
    output: Annotated[str, typer.Option("--output", "-o")] = "-",
    min_interval: MinIntervalOpt = 1.0,
    proxy: ProxyOpt = None,
) -> None:
    """Bulk view counts: emits {id, nb_views, nb_phone_views} per advert."""

    async def run() -> int:
        async with ApiClient(
            concurrency=1, min_interval=min_interval, proxy=proxy
        ) as client:
            api = KrishaApi(client)
            counts = await api.views(list(ad_ids))
            with open_output(output) as out:
                for ad_id in ad_ids:
                    c = counts.get(ad_id)
                    write_jsonl(
                        out,
                        {
                            "id": ad_id,
                            "nb_views": c.nb_views if c else None,
                            "nb_phone_views": c.nb_phone_views if c else None,
                        },
                    )
        return 0

    raise typer.Exit(_run(run()))


@app.command()
def categories() -> None:
    """List the category IDs accepted by `krisha search`."""
    for name, cat_id in sorted(CATEGORY_IDS.items(), key=lambda x: x[1]):
        typer.echo(f"  {cat_id:>3}  {name}")


@app.command()
def regions() -> None:
    """List the region names accepted by `krisha search --region`.

    The mobile API doesn't expose a name → id endpoint, so this list is a
    hand-verified subset. To narrow by an ID not in the list, pass
    `--geo-id N` directly.
    """
    for name, region_id in sorted(REGION_IDS.items(), key=lambda x: x[1]):
        typer.echo(f"  {region_id:>3}  {name}")


if __name__ == "__main__":
    app()
