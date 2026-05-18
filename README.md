# krisha-kz CLI

CLI for extracting real-estate listings from [krisha.kz](https://krisha.kz)
(Kazakhstan). Emits JSONL — one ad per line — pipeable into `jq`, DuckDB, etc.

## Install

```bash
uv venv && uv pip install -e .
# entrypoint:
krisha --help
```

Requires Python 3.11+.

## Rate-limiting & IP bans

Krisha will block your IP if you hammer the site. The CLI ships with
**polite defaults** that have worked reliably for me:

- `--concurrency 2` — at most two in-flight requests.
- `--min-interval 1.0` — ≥1 s between request *starts*, with ±30 % jitter,
  enforced globally across all concurrent tasks.
- Browser-like `User-Agent`, HTTP/1.1 with keep-alive.
- Retry with exponential backoff (max 60 s) on `429` and `5xx`.
- A `403` aborts immediately with a clear message (retrying a ban won't help).

**If you get blocked:**

1. Wait a few hours.
2. Re-run with a proxy: `--proxy http://user:pass@host:port` (also reads
   `KRISHA_PROXY` and `HTTPS_PROXY` env vars).
3. Lower throughput further: `--concurrency 1 --min-interval 2`.
4. Optionally override the UA: `--user-agent "Mozilla/5.0 …"`.

## Commands

### `krisha show <id>`

Fetch a single advert by its krisha ID and emit the full structured record.

```bash
krisha show 1009233693 | jq .
```

Returns: `id`, `url`, `title`, `price_kzt`, `rooms`, `square_m2`, `floor`,
`floors_total`, structured `address` & `coords`, `complex_name`, `complex_id`,
`building_type`, `year_built`, `condition`, full `characteristics` dict,
free-text `description`, `photos[]`, `seller`, `category`, `scraped_at`.

### `krisha search <section>/<category>`

Run a paginated search and emit one JSONL record per hit.

```bash
# Almaty 2-room apartments, 20-40M ₸, built 2015+, pages 1-5
krisha search prodazha/kvartiry \
  --city almaty \
  --rooms 2 \
  --price-from 20000000 --price-to 40000000 \
  --year-from 2015 \
  --pages 1-5 \
  -o almaty-2k.jsonl

# Astana rentals, all pages, behind a proxy, extra slow
krisha search arenda/kvartiry --city astana --rooms 2 --pages all \
  --min-interval 2 --proxy http://localhost:8888 -o rentals.jsonl

# With full ad details merged in (one /a/show fetch per result)
krisha search prodazha/kvartiry --city almaty --rooms 1 --pages 1 --enrich
```

Total request count for `search`: `pages` (with `--enrich`: `pages × (1 + cards_per_page)`).
Plan accordingly given the default 1 s spacing.

#### Filters

| Flag | Maps to | Notes |
|---|---|---|
| `--city` | URL slug | `almaty`, `astana`, `shymkent`, `karaganda`, … |
| `--rooms N` | `das[live.rooms]` | repeatable |
| `--price-from/--price-to` | `das[price][from/to]` | KZT |
| `--square-from/--square-to` | `das[live.square][from/to]` | m² |
| `--year-from/--year-to` | `das[house.year][from/to]` | |
| `--floor-from/--floor-to` | `das[flat.floor][from/to]` | |
| `--building` | `das[flat.building]` | `brick`, `panel`, `monolith`, `other` (repeatable) |
| `--has-photo` | `das[_sys.hasphoto]` | |
| `--new-build` | `das[novostroiki]` | |
| `--from-owner` / `--from-agent` | `das[who]` / `das[_sys.fromAgent]` | |
| `--mortgage/--no-mortgage` | `das[mortgage]` | |
| `--floor-not-first/--floor-not-last` | matching `das[...]` | |
| `--das KEY=VALUE` | escape hatch | e.g. `--das flat.toilet=2` |

#### Networking flags (both commands)

| Flag | Default | Notes |
|---|---|---|
| `--concurrency` / `-c` | `2` (search) / `1` (show) | max in-flight requests |
| `--min-interval` | `1.0` s | global gap between request starts, ±30 % jitter |
| `--retries` | `4` | retries on `429` / `5xx` / network errors |
| `--timeout` | `30.0` s | per-request HTTP timeout |
| `--proxy` | — | HTTP/SOCKS URL; also reads `KRISHA_PROXY`, `HTTPS_PROXY` |
| `--user-agent` | Chrome on macOS | override default UA |

Run `krisha search --help` for the full list.

#### Sections / categories

- `prodazha/{kvartiry,doma-dachi,uchastkov,kommercheskaya-nedvizhimost,garazhi,prombazy,biznes}`
- `arenda/{kvartiry,komnaty,doma-dachi,kommercheskaya-nedvizhimost,garazhi,vozmu-v-arendu}`

#### Output

`-o file.jsonl` writes to a file; default is stdout. One JSON object per line.

```bash
krisha search prodazha/kvartiry --city almaty --pages 1 | \
  jq -r 'select(.price_kzt < 25000000) | "\(.id)\t\(.price_kzt)\t\(.address)"'
```

## Notes & limitations

- All endpoints accessed (`/prodazha/*`, `/a/show/*`) are **not** in
  `robots.txt`. Phone numbers (`/a/ajaxPhones`) require a logged-in session
  and are not implemented.
- View counts on listing cards are populated client-side via a
  robots-disallowed endpoint, so `views` is `null` for `search` results.

## Project layout

```
src/krisha/
├── cli.py         # Typer commands
├── client.py      # httpx async wrapper, rate limiter, retries
├── urls.py        # SearchFilters → URL
├── parse_list.py  # listing-page HTML → ListingCard
├── parse_show.py  # ad-page HTML → AdDetail (extracts window.data)
├── models.py      # pydantic models
└── output.py      # JSONL writer
```
