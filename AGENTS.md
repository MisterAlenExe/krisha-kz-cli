# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Commands

Dev environment uses `uv` and a local `.venv/`:

```bash
uv venv && uv pip install -e .          # install (editable) + deps
.venv/bin/krisha --help                 # CLI entrypoint
.venv/bin/python -m krisha.cli ...      # equivalent
```

There is no test runner, linter, or formatter configured.

Smoke-test against the live API:

```bash
.venv/bin/krisha show 1009233693
.venv/bin/krisha search sell.flat --region almaty --rooms 2 --pages 1
.venv/bin/krisha phone 1009233693
.venv/bin/krisha views 1009233693 687390482
```

## Architecture

Single Python package `src/krisha/`. Two layers:

- **`krisha.api`** (current, wired into the CLI) — thin async client over the krisha.kz iOS mobile JSON API. The endpoint catalogue lives in `krisha-kz-openapi.yaml` (gitignored — local reference only); that's the source of truth.
- **`krisha.client`, `krisha.parse_list`, `krisha.parse_show`, `krisha.urls`, `krisha.models`** — DEPRECATED HTML-scraper modules, kept on disk for reference. Not imported by `cli.py`.

Data flow for the API path:

```
cli.py  →  api.SearchFilters.listing_params()  →  api.ApiClient.get_json()  →  api.KrishaApi
                                                                                  ↓
                                          api.ListingEnvelope.adverts()  →  output.write_jsonl
```

Things worth knowing:

- **Auth is a static iOS-app credential pair.** `api.constants.APP_ID` / `APP_KEY` are sent in the query string on every request. No nonce, no signature, no device binding (probe-verified). If those ever stop working it means krisha rotated them — re-extract from a fresh iOS app build.
- **Rate limiting is global, not per-task.** `ApiClient` holds a shared `_next_slot` timestamp guarded by `_slot_lock`. Every `get_json` call — including `asyncio.gather` fan-outs in `cli.search` — passes through `_wait_for_slot`. Concurrency 2 + min-interval 1.0 means ~1 req/s overall, not 1 req/s per task. Don't bypass by instantiating a second client.
- **Polite-by-default is deliberate.** The dev's IP was banned during the HTML-scraping era. Defaults (concurrency 2, min-interval 1.0, HTTP/1.1, 403 short-circuits without retry) carried over. Proxy support reads `--proxy`, then `KRISHA_PROXY`, then `HTTPS_PROXY`.
- **Listing items are heterogeneous.** `items[]` mixes `kind:"advert"` with banners (`kind:"hot"`, `"header"`, `"agent_advantages"`). `ListingEnvelope.adverts()` flattens to real adverts only — descends into `kind:"hot"` wrappers, skips the others. Don't iterate `items[]` directly.
- **Sort namespace split.** Regular sorts use `orderBy[data][0][...]` lowercase. The hot-feed sort uses `orderBy[system_data][0][name]=hot&orderBy[system_data][0][sort]=DESC` — uppercase DESC, different namespace key. `SearchFilters.listing_params(order_by="hot")` handles this.
- **Filter encoding.** Mobile API uses repeated keys (`query[data][map.geo_id][]=106&...[]=2726`) which dicts can't represent — we emit `list[tuple[str, Any]]` and pass it straight to httpx. The canonical names come from `/category/getSearchForm?id={catId}`; see `SearchFilters` for the curated typed set and `--extra KEY=VALUE` for the escape hatch.
- **Region names are unresolved.** `/v1/booking/regions` and `/region/getAgentRegions` return ID arrays only. No name-lookup endpoint exists; names appear pre-cached in the iOS app binary. `api.constants.REGION_IDS` has a hand-filled subset, verified empirically: `almaty=2`, `astana=105`, `karaganda=239`, `balkhash=237`. Unknown geo_ids appear to fall back to Almaty server-side, so don't add entries without probing first.
- **`commonRegionId` alone doesn't filter.** It's metadata; the actual geographic constraint is `query[data][map.geo_id][]`. `SearchFilters` auto-injects `geo_ids=[common_region_id]` when no geo_ids are passed, so the CLI's `--region NAME` actually works. Don't remove that default.
- **`--pages all` flow.** First page is fetched at `offset=(start_page-1)*PAGE_SIZE`; `nb_total / PAGE_SIZE` (rounded up) gives the last page. Remaining pages are gathered concurrently but still rate-limited by the shared client.
- **Output.** `output.open_output` treats `-` (and `None`) as stdout. `write_jsonl` accepts a pydantic model or a `dict` and uses `orjson.dumps` with `model_dump(mode="json")`.

## Conventions

- Conventional Commits for every commit (`type(scope): subject`, imperative, ≤72 chars). Common scopes: `api`, `cli`, `client`, `models`, `search`.
- Python 3.11+, `from __future__ import annotations` at the top of every module, pydantic v2 syntax (`model_dump(mode="json")`, not `.dict()`).
- New endpoints: extend `api/endpoints.py` and document in `krisha-kz-openapi.yaml` (keep them in sync).
