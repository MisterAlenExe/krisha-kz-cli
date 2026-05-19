# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Dev environment uses `uv` and a local `.venv/`:

```bash
uv venv && uv pip install -e .          # install (editable) + deps
.venv/bin/krisha --help                 # CLI entrypoint
.venv/bin/python -m krisha.cli ...      # equivalent
```

There is no test runner, linter, or formatter configured — `pyproject.toml` declares only runtime deps. `tests/fixtures/` exists (empty) and is `!`-excluded from `.gitignore` so recorded HTML fixtures can be committed if/when tests are added.

Smoke-test against the live site (mind the IP-ban risk — see "Rate limiting" below):

```bash
.venv/bin/krisha show 1009233693
.venv/bin/krisha search prodazha/kvartiry --city almaty --pages 1
```

## Architecture

Single Python package `src/krisha/` exposing one Typer app (`cli.py:app`, registered as `krisha`). Data flows in a fixed pipeline:

```
cli.py  →  urls.SearchFilters.page_url()  →  client.KrishaClient.get_text()
                                              ↓
                              parse_list.parse_listing_page()    (search)
                              parse_show.parse_show()            (show / --enrich)
                                              ↓
                              models.{ListingCard, AdDetail}  →  output.write_jsonl
```

Things worth knowing before changing code:

- **Rate limiting is global, not per-task.** `KrishaClient` holds a shared `_next_slot` monotonic timestamp guarded by `_slot_lock`. Every `get_text` call — including the `asyncio.gather` fan-outs in `cli.search` for paging and `--enrich` — passes through `_wait_for_slot`, so concurrency=2 + min_interval=1.0 means at most ~1 req/s overall, not 1 req/s per task. Don't bypass this by adding a second client or calling `_client.get` directly.
- **Polite-by-default is deliberate.** Defaults (`concurrency=2`, `min_interval=1.0`, HTTP/1.1, `Accept-Encoding: gzip, deflate`, Chrome-on-macOS UA, `403` short-circuits without retry) exist because the dev's IP was banned during stress testing. Don't "modernize" to HTTP/2, add brotli, or retry 403s without thinking about it. Proxy support reads `--proxy`, `KRISHA_PROXY`, then `HTTPS_PROXY`.
- **`parse_show` extracts two inline JSON blobs** — `window.data` (canonical advert payload) and `window.digitalData` (analytics, used for seller/category fallback). Regex won't work on nested braces; `_extract_json_blob` walks forward from the first `{` counting depth while tracking string literals and `\` escapes. If you touch it, mind both states.
- **`parse_list` quirks.** Stats (city, posted_at, views) come from `.a-card__stats-item` *children* — reading the parent `.a-card__stats` collapses the inter-item newlines and corrupts fields. `views` is always `None` because the count is loaded client-side via the robots-disallowed `/ms/views/...` endpoint. The `_TOTAL_RE` is class-anchored on `a-search-subtitle` to avoid matching unrelated "Найдено" text and tolerates `\xa0` non-breaking spaces inside the number.
- **URL building.** `urls.SearchFilters.page_url` uses `urlencode(..., safe="[]")` so the `das[key][from]` brackets stay literal (krisha rejects percent-encoded brackets). Page 1 is implicit (no `&page=` param). For filters not in the curated typed set, use the `--das KEY=VALUE` escape hatch rather than adding a one-off field.
- **`--pages all` flow.** `cli.search` fetches page `start_page` first, parses cards, then calls `parse_total_count` on the *same* HTML and divides by `ADS_PER_PAGE = 20` to compute the end page. Remaining pages are gathered concurrently but still rate-limited by the shared client.
- **Output.** `output.open_output` treats `-` (and `None`) as stdout; anything else is a file path. `write_jsonl` accepts a pydantic model or a `dict` and uses `orjson.dumps` with `model_dump(mode="json")`.

## Conventions

- Conventional Commits for every commit (`type(scope): subject`, imperative, ≤72 chars). Common scopes here: `client`, `cli`, `parse_show`, `parse_list`, `urls`.
- Python 3.11+, `from __future__ import annotations` at the top of every module, pydantic v2 syntax (`model_dump(mode="json")`, not `.dict()`).
