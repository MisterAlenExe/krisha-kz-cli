# krisha-kz CLI — Implementation Plan

A Python 3 CLI for extracting listings from **krisha.kz** (KZ real-estate).
Two commands in v1: `search` and `show`. JSONL output. Aggressive concurrency.

---

## 1. Findings from exploration

### Site shape
- Fully **server-rendered HTML**. Plain `curl` with a normal `User-Agent` returns the full page (no JS, no cookies, no Cloudflare challenge).
- nginx origin; rapid sequential fetches return 200/0.3 s with no throttling observed.
- `robots.txt` does **not** disallow `/prodazha/*`, `/arenda/*`, `/a/show/*`. Only auxiliary endpoints (`/ms/*`, `/ajax/*`, comments, claims, etc.) are blocked.
- `https://krisha.kz/sitemap.xml` → index → `search.xml`, `catalog.xml`, `complexes.xml`, etc. (useful for bulk ID discovery later, not v1).

### URL patterns

**Listings (search results pages):**
```
https://krisha.kz/{section}/{category}/{city}/?das[KEY]=VALUE&page=N
```
- `section`: `prodazha` (sale) | `arenda` (rent)
- `category`: `kvartiry`, `doma-dachi`, `uchastkov`, `kommercheskaya-nedvizhimost`, `garazhi`, `prombazy`, `biznes`, `zarubezhnoj-nedvizhimosti`, `komnaty` (rent), `vozmu-v-arendu` (rent)
- `city`: `almaty`, `astana`, `shymkent`, `karaganda`, … (lowercase Latin slugs)
- Pagination: `?page=2` … up to `1000` for unfiltered Almaty apartments (~20 ads/page).

**Single ad:**
```
https://krisha.kz/a/show/{id}
```

### Filter parameters (`das[…]`)
Confirmed by inspecting the search-form `<input name="das[…]">` fields:

| Param | Type | Notes |
|---|---|---|
| `das[live.rooms]` | int (1–5+, multi) | room count |
| `das[price][from]` / `[to]` | int (KZT) | |
| `das[live.square][from]` / `[to]` | int (m²) | |
| `das[live.square_k][from]` / `[to]` | int (m², kitchen) | |
| `das[house.year][from]` / `[to]` | int | year built |
| `das[flat.building]` | int multi | 1 brick, 2 panel, 3 monolith, 0 other |
| `das[flat.floor][from]` / `[to]` | int | flat floor |
| `das[house.floor_num][from]` / `[to]` | int | building floor count |
| `das[flat.toilet]` | int multi | 1 sep, 2 combined, 3 ≥2 |
| `das[flat.phone]` | int multi | |
| `das[mortgage]` | 1 / 0 | |
| `das[novostroiki]` | bool | new-builds only |
| `das[who]` / `das[_sys.fromAgent]` | bool | owner vs agent |
| `das[_sys.hasphoto]` | bool | photos required |
| `das[floor_not_first]` / `das[floor_not_last]` | bool | |
| `das[has_change]` | bool | exchange possible |
| `das[map.complex]` | hidden | new-build complex id |

(Full list: 30 inputs on the apartments form. CLI exposes a curated subset and a `--das key=value` escape hatch for the rest.)

### Data sources on each page

**Listing pages** carry one `.a-card` per advert with `data-id="{id}"` and these selectors:
- `.a-card__title` — e.g. `"2-комнатная квартира · 50 м² · 5/5 этаж"`
- `.a-card__price` — e.g. `"35 500 000 〒"`
- `.a-card__subtitle` — district + street/microdistrict
- `.a-card__text-preview` — short description (renovation, building, etc.)
- `.a-card__stats` — city, date posted, view count
- `<img data-src>` — thumbnail
- Also a sibling `<script>` block sets `window.adverts` array.

Total result count is in `.a-search-subtitle` (`"Найдено 2 762 объявления"`), used to bound `--pages all`.

**Ad detail pages** are the rich source. Two embedded JSON blobs:
- `window.data.advert` — `{id, price, photos[], title, addressTitle, square, rooms, ownerName, map: {lat, lon}, address: {country, city, district, microdistrict, street}, complexId, …}`
- `window.digitalData.product` — `{seller: {id, name, type, status}, latLng, region, categoryId, offerType, objectType, appliedPaidServices[]}`

Plus an HTML characteristics list under `.offer__info-item` (e.g. `Тип дома: монолитный`, `Год постройки: 2025`, `Этаж: 6 из 9`, `Состояние квартиры: свежий ремонт`) and the free-text description under `.text` / `.a-text-white-spaces`.

Together: enough to produce a fully-typed record per ad without phoning the JS runtime.

### What we deliberately skip in v1
- **Phone numbers**: `/a/ajaxPhones?id=…` returns `403 "необходимо авторизоваться"` without login. Out of scope.
- **`/ms/*`** view-counter and analytics endpoints (robots-disallowed).
- **Maps tiles / 2GIS / photo CDN** beyond capturing URLs.

---

## 2. CLI surface

```
krisha search <section>/<category> [filters] [--pages N|N-M|all] [-o out.jsonl]
krisha show <id> [-o out.jsonl]
```

### `krisha search`
Emits **one JSON object per listing card** to stdout (or `-o file.jsonl`).

```
krisha search prodazha/kvartiry \
  --city almaty \
  --rooms 2 \
  --price-from 20000000 --price-to 40000000 \
  --year-from 2015 \
  --square-from 50 \
  --pages 1-5 \
  --concurrency 16 \
  -o almaty-2k.jsonl
```

Flags (typed):
- `--city` (default `almaty`)
- `--rooms` (repeatable)
- `--price-from` / `--price-to`
- `--square-from` / `--square-to`
- `--year-from` / `--year-to`
- `--floor-from` / `--floor-to`
- `--building` (`brick|panel|monolith|other`, repeatable)
- `--has-photo`, `--new-build`, `--from-owner`, `--from-agent`, `--mortgage`
- `--pages` — `5` | `2-7` | `all` (default `1`)
- `--das KEY=VALUE` — escape hatch for any other `das[…]` param
- `--enrich` — for each card, also fetch `/a/show/{id}` and merge full details (slower; effectively `crawl`)
- `-o, --output PATH` — file path or `-` for stdout (default)
- `--format jsonl` (only format in v1)

Each emitted JSON record:
```json
{
  "id": 1012332593,
  "url": "https://krisha.kz/a/show/1012332593",
  "title": "2-комнатная квартира · 50 м² · 5/5 этаж",
  "price_kzt": 35500000,
  "rooms": 2,
  "square_m2": 50.0,
  "floor": 5, "floors_total": 5,
  "city": "Алматы",
  "district": "Ауэзовский р-н",
  "address": "мкр Таугуль-1, Мкр Таугуль-3 8",
  "description_preview": "…",
  "photo": "https://astps-photos-kr.kcdn.kz/…/1-400x300.jpg",
  "posted_at": "2026-05-19",
  "views": 3551,
  "seller_type": "company",     // from digitalData when --enrich
  "page": 2,
  "scraped_at": "2026-05-19T00:25:11Z"
}
```

### `krisha show <id>`
Fetches `/a/show/{id}`, parses, emits one full JSON object:

```json
{
  "id": 1009233693,
  "url": "https://krisha.kz/a/show/1009233693",
  "title": "...",
  "price_kzt": 21500000,
  "rooms": 1, "square_m2": 35, "floor": 6, "floors_total": 9,
  "address": {"country": "...", "city": "Алматы", "district": "Наурызбайский р-н",
              "microdistrict": "мкр Шугыла", "street": "Мкрн Шугыла"},
  "coords": {"lat": 43.1943, "lon": 76.7833},
  "complex_id": 12345, "complex_name": "Ulytau",
  "building_type": "монолитный",
  "year_built": 2025,
  "condition": "свежий ремонт",
  "characteristics": {"Санузел": "совмещенный", "Балкон": "балкон", "Пол": "ламинат", "...": "..."},
  "description": "Пластиковые окна, неугловая, …",
  "photos": ["https://astps-photos-kr.../full.jpg", "..."],
  "seller": {"id": 21920863, "name": "Туран Капитал", "type": "company", "is_verified": false},
  "category": {"section": "prodazha", "object": "kvartiry", "category_id": 1},
  "scraped_at": "2026-05-19T00:25:11Z"
}
```

---

## 3. Project layout

```
krisha-kz-cli/
├── pyproject.toml           # uv / hatchling; installs `krisha` entrypoint
├── README.md
├── PLAN.md                  # this file
└── src/krisha/
    ├── __init__.py
    ├── cli.py               # Typer app, command wiring, option parsing
    ├── client.py            # httpx.AsyncClient wrapper, retries, jitter, concurrency
    ├── urls.py              # build search URL from filters; cities/categories enums
    ├── parse_list.py        # listing-page HTML → list[ListingCard]
    ├── parse_show.py        # ad-page HTML → AdDetail (extract window.data + offer__info-item)
    ├── models.py            # pydantic models: ListingCard, AdDetail, SearchFilters
    └── output.py            # JSONL writer (atomic, line-buffered, stdout/file)
```

### Dependencies (pyproject)
- `httpx[http2]` — async HTTP client with HTTP/2 and connection pooling.
- `selectolax` — fast Modest-engine HTML parser (~10× lxml on listing pages).
- `typer[all]` — CLI framework (Click-based; rich help).
- `pydantic` v2 — typed models and JSON serialisation.
- `orjson` — fast JSON encoder for JSONL output.
- (dev) `pytest`, `respx` for offline HTML fixtures.

---

## 4. Scraping mechanics

### Extracting `window.data` from ad pages
The blob is rendered inline as:
```html
<script>window.data = {"advert":{…}, …};</script>
```
Strategy:
1. Locate via regex: `r"window\.data\s*=\s*(\{.*?\});"` with DOTALL on the raw HTML.
2. `orjson.loads()` the match.
3. Same for `window.digitalData` to get `seller` and `latLng`.
4. Fall back to selectolax for the `.offer__info-item` characteristics rows (these are *not* in `window.data`).

### Listing parse
- Iterate `div.a-card[data-id]`.
- Use selectolax for `.a-card__title`, `.a-card__price`, `.a-card__subtitle`, `.a-card__text-preview`, `.a-card__stats`, `img[data-src]`.
- Normalise price: strip non-digits, parse "21 500 000 〒" → `21500000`.
- Normalise area, rooms, floor from the title regex `r"(\d+)-комнатная.*?(\d+(?:\.\d+)?)\s*м².*?(\d+)/(\d+)"` (gracefully skip when partial).
- Stop pagination early when the page returns zero `.a-card` rows, or when `<title>` lacks "Страница N" beyond requested range.

### Concurrency / politeness
User selected **aggressive**:
- Default `--concurrency 16` over a single shared `httpx.AsyncClient` with `http2=True` and keep-alive.
- No deliberate sleep between requests.
- Retry policy: 3 retries with exponential backoff (0.5 / 1 / 2 s) on `429`, `5xx`, and network errors. Honour `Retry-After` if set.
- Realistic browser `User-Agent`; `Accept-Language: ru-RU,ru;q=0.9,en;q=0.8`; `Accept-Encoding: gzip, br`.
- No cookies — site happily serves anonymous.
- `--concurrency` and `--retries` are tunable flags so the user can dial down if banned.

### Error handling
- Per-page failures don't kill the run: log a single-line warning to stderr (`{"event":"error", "page":3, "status":502}`) and continue.
- Exit code `0` if ≥1 record was emitted, else `1`.

---

## 5. Build / iteration order

1. **Scaffold** (`pyproject.toml`, `src/krisha/__init__.py`, `cli.py` skeleton, install via `uv pip install -e .`).
2. **`show` command first** — smallest unit, well-defined output. Build `parse_show.py` against the saved `/tmp/krisha_ad.html` fixture.
3. **`search` command** — wire `urls.py` filter mapping; reuse async client.
4. **`--enrich`** — fan-out from search cards to `show` for each ID.
5. **Tests** — record 1 listing + 1 ad page as fixtures under `tests/fixtures/`; parse-only tests run offline.
6. **README** with copy-paste examples, including a `jq | duckdb` recipe.

Estimated effort: ~half a day to MVP (`show` + `search` no-enrich), another half-day for `--enrich`, tests, README.

---

## 6. Out of scope (v1)

- Authentication / phone reveal.
- Map-bounded search (`/a/show-map/` is robots-disallowed).
- Sitemap-based full-corpus crawl.
- Saved-search diffing / `watch` mode.
- CSV / SQLite / Parquet outputs.
- Image downloads (URLs are emitted; user can `wget` if needed).
- Complex / new-build (`/complex/`) endpoints — different schema.

These are good follow-ups once v1 is in use.
