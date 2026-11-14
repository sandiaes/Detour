# Architecture

Status: **accepted** on 2026-11-12 through
[`decisions/001-technology-stack.md`](decisions/001-technology-stack.md) and
[`decisions/002-api-strategy.md`](decisions/002-api-strategy.md). Hosting (D3) is decided in ADR 005.
Phase 1 (the foundation: section 4.2.1) and Phase 2 (data and search: section 4.2.2, the import
pipeline in 4.4, the search service in 4.6) are implemented. Phase 3 (the travel-time service,
section 4.5, [ADR 013](decisions/013-phase-3-travel-time-service.md)), Phase 4 (planner v1 for
attractions and days, section 5, [ADR 014](decisions/014-phase-4-planner-v1.md)), Phase 5 (the
mobile shell, [ADR 015](decisions/015-phase-5-mobile-shell.md)) and Phase 6 (meals and area
destinations, section 5, [ADR 016](decisions/016-phase-6-meals-and-area-destinations.md)) are built
and await acceptance. Phase 7 (adding and removing places with recalculation, section 5.4,
[ADR 018](decisions/018-phase-7-add-place-and-recalculation.md)) and Phase 8 (adding a restaurant
and placing it in the best slot, sections 4.2.6 and 5.4,
[ADR 019](decisions/019-phase-8-add-a-restaurant.md)) are built and await acceptance. Budgets, currencies, prices and
the FX job are removed for now ([ADR 017](decisions/017-no-budgets-currencies-or-prices.md)).
Multilingual place names (section 4.7, [ADR 025](decisions/025-multilingual-place-names.md)) are
built and await acceptance.

## 1. Principles

1. **No LLM at runtime.** Planning is a deterministic algorithm. Explanations are structured
   reason codes rendered through fixed templates.
2. **Own the data path.** Open data is imported into our own database per region. The app does
   not depend on public community servers at request time.
3. **Backend-only integration.** The mobile app talks to one API: ours. Every external provider
   sits behind a backend adapter, so a provider can be swapped without an app release.
4. **One planning engine for both platforms.** All itinerary logic runs in the backend. The
   mobile app renders and edits.
5. **Deterministic and explainable.** The same inputs and data version produce the same
   itineraries, and every placement carries the reasons for it.
6. **Honest data.** Estimated travel times and unknown cuisines are shown as
   estimated or unknown, never guessed silently. The app has no prices (ADR 017). Place names are
   never translated; a name Detour romanized itself says so (ADR 025).

## 2. Stack verdict

| Provisional choice | Verdict | Notes |
|---|---|---|
| React Native + Expo + TypeScript | **Confirmed** | Expo SDK 58 (React Native 0.88). The New Architecture is mandatory since SDK 55. A development build is required because MapLibre is not in Expo Go. |
| MapLibre + OSM-compatible data | **Confirmed** | `@maplibre/maplibre-react-native` v11 (MIT), Android and iOS. `expo-maps` is rejected: alpha, Google Maps on Android, Apple Maps on iOS. |
| Python + FastAPI | **Confirmed** | MIT. Pin the Python version in Phase 1. |
| PostgreSQL + PostGIS | **Confirmed** | Image `postgis/postgis:18-3.7`. The `-3.5` and `-3.6` tags are no longer updated. PostgreSQL 18 changed the data volume path to `/var/lib/postgresql`. |
| Docker Compose | **Confirmed** for local development | Production hosting: ADR 005. |
| Deterministic planning engine | **Confirmed** | Section 5. |
| OR-Tools | **Not adopted** (spike S5, D7). Earlier verdict: conditionally justified | Useful for the multi-day, time-windowed, optional-visit problem. Introduced behind an interface after a Phase 0 spike; a simple heuristic remains as baseline and fallback. Section 5.5. |

Additions the provisional stack did not name: **Valhalla** (self-hosted routing and matrices), a
**region import pipeline**, and **expo-sqlite** for an on-device read cache.

## 3. System overview

```
┌───────────────────────────── Mobile app (Expo, TypeScript) ─────────────────────────────┐
│  Screens: trip setup · itinerary variants · day view · map · add place · restaurant     │
│  MapLibre React Native (vector tiles)          expo-sqlite (read cache of trips)        │
└───────────────┬──────────────────────────────────────────────┬──────────────────────────┘
                │ HTTPS/JSON (OpenAPI contract)                │ vector tiles (style URL from backend)
                ▼                                              ▼
┌──────────────────────── Backend (FastAPI) ────────────────────────┐   OpenFreeMap public instance
│  API layer        trips · itineraries · places · config           │   (fallback: self-hosted PMTiles)
│  Planning engine  scope → candidates → days → sequence → meals    │
│  Services         travel time · search                            │
│  Provider adapters (one interface per capability)                 │
└────┬───────────────────┬──────────────────────┬───────────────────┘
     │                   │                      │
     ▼                   ▼                      ▼
PostgreSQL + PostGIS   Valhalla (FOSSGIS     External, backend-only, cached:
 geo schema: open data  server, ADR 004)      Photon (search)
 app schema: user data

Offline pipeline (CLI, not request path):
 Geofabrik .osm.pbf ─┬─► attraction import ─► geo schema
                     └─► Valhalla tile build
 GeoNames dump ─► gazetteer      Wikidata ─► notability, English names (ADR 025, lazy)
```

All services except the tile host run from one Docker Compose file in development: `db`, `api`,
`valhalla`, plus one-shot `import` jobs.

## 4. Components

### 4.1 Mobile app

- **Trip export and import (ADR 028):** `src/exchange/`. The backend assembles the trip as JSON
  (`GET /v1/trips/{id}/export`) and writes an imported trip as a new place trip with a manual plan
  (`POST /v1/trips/import`); the phone adds the documents, zips them with `fflate` into a `.detour`
  file and hands it to the system share sheet (`expo-sharing`). Detour uploads nothing. Opening a
  `.detour` file with the app (an Android intent filter) goes to the Import screen.

- Expo SDK 58, TypeScript, Continuous Native Generation with config plugins; no hand-edited
  native projects. This keeps the iOS build a configuration task, not a port.
- **Redesign, steps 1 and 2 (ADR 021, proposed):** design tokens and reusable components
  (`src/theme.ts`, `src/components/ds/`, line icons and illustrated covers drawn with
  `react-native-svg`), a bottom bar (Trips, Explore, Add, Photos, More; Add is contextual), the
  trips list with Upcoming and Past tabs, and a Trip Overview built around the active itinerary
  (`selected_itinerary_id`) with Overview, Itinerary, Map, Photos and Documents tabs. The original
  proposals are in the trip's menu. Step 3: the itinerary a day at a time
  (`components/plan/DayPlan.tsx`), map and list sharing one selection, transport markers at new
  base cities (the API's `Day.base_city_lat`/`lon`, read from `geo.city` at read time), and a place
  detail screen. Step 4: adding a place by search, address or pin with up to three suggested
  days, each from the Phase 7 recalculation restricted to that day (`place-suggestions`), then
  the usual preview. Explore, Photos, Documents and notes are placeholders that say they are not
  built.
- **Built in Phase 5 (ADR 015):** a stack navigator in React state, a small server-state layer in front of an `expo-sqlite` read cache, and the screens: trips, new trip, the two proposals compared, day list, plan map, Settings with credits. Offline reads, "waking the server" and error states are in every list screen. The Phase 1 description that follows is the shell it replaced.
- **Built in Phase 1:** `apps/mobile` with six placeholder screens (Trips, Create Trip, Itinerary,
  Map, Saved Places, Settings), a tab bar held in React state (no navigation library until the
  Phase 5 ADR), a backend connection layer (health, then config, then anonymous registration;
  token kept in `expo-secure-store`) that shows a "waking the server" state during the Render cold
  start, and the attribution rule with a component test. The only build-time value is
  `EXPO_PUBLIC_DETOUR_API_URL`.
- Android builds run in GitHub Actions: `expo prebuild` then Gradle `assembleRelease` on a
  GitHub-hosted runner, about 14 minutes, APK downloaded from the run's artifacts (spike S1,
  `docs/spikes/s1-map-findings.md`). They are release-variant builds with the JavaScript bundled,
  not `expo-dev-client` builds, because the owner has no computer to run a development server
  (ADR 008 addendum). Expo's cloud build (free plan: 15 Android and 15 iOS builds per month,
  low-priority queue, read 2026-11-12) is the fallback. The project's own signing key is needed
  before a build is kept for real use.
- MapLibre React Native for all map rendering. The style URL and the attribution lines are read
  from the backend config endpoint (`GET /v1/config`, shape recorded in the S1 findings), so the
  tile provider can change without a release. The only build-time value is the backend's base
  URL. Attribution is visible in a map corner at start and may collapse to an "i" button after
  five seconds or on map interaction (OSMF attribution guidelines).
- `expo-sqlite` holds a read cache of the user's trips so that an accepted itinerary is viewable
  without a connection. Planning and recalculation always need the backend.
- **Trip documents stay on the device** (ADR 023): files copied into the app's private storage with
  `expo-file-system`, listed in a `trip_document` table of the same SQLite database (apart from the
  cache). They are never uploaded; the backend knows nothing of them.
- No direct calls to any third-party API other than the tile host.
- Platform-specific behaviour is limited to permissions and build configuration.
- Navigation, server-state and form libraries: none (ADR 015).

**iOS readiness.** Minimum iOS for SDK 58 is 16.4. MapLibre's config plugin is required on iOS.
The app is not distributed through app stores (ADR 008): iPhone builds are compiled on the
owner's Mac. Whether a free Apple ID suffices or the paid Apple Developer Program ($99 per year)
is needed is decided in Phase 11. No Android-only native module is allowed into the dependency
list without an ADR.

### 4.2 Backend API

- FastAPI application exposing a versioned JSON API described by OpenAPI. TypeScript types for
  the app are generated from that contract.
- Stateless request handling; all state in PostgreSQL.
- Identity in the MVP is an **anonymous installation**: the app registers once and receives a
  bearer token (D5, approved). This avoids building accounts, which are not a product goal.
- Indicative resource groups (final shapes are defined in Phase 1):
  - destinations: search cities and areas
  - trips: create, read, update
  - itineraries: generate variants, read, select
  - itinerary edits: add place, add restaurant, move, lock, remove; each returns a **preview
    diff** that the user accepts or discards
  - places: search within the trip's region
  - config: map style URL, attribution list, data versions

#### 4.2.1 Phase 1 API

Implemented in `services/api` (FastAPI, Python 3.13), all under `/v1`, described by
`packages/shared/openapi.json`:

| Endpoint | Purpose |
|---|---|
| `GET /v1/health` | Liveness: status, version, deployed commit. No database access |
| `GET /v1/health/ready` | Readiness: database reachable, `geo` and `app` present, PostGIS version if enabled; 503 otherwise |
| `GET /v1/config` | Map style URL and attribution lines (shape from spike S1) plus a config version |
| `POST /v1/installations` | Register an anonymous installation; returns the id and a bearer token |
| `GET /v1/installations/me` | Token check; 401 with `WWW-Authenticate: Bearer` if invalid |

Settings come from `DETOUR_*` environment variables; logs are JSON with redaction; the token is an
HMAC-signed string that needs no database row in Phase 1 (ADR 010). The interactive documentation
is at `/v1/docs`. The typed client for the app is generated from the contract, and CI fails on
drift.

#### 4.2.2 Phase 2 API

Also under `/v1`, in the contract `packages/shared/openapi.json`. Everything except the first two
rows needs the installation token. Errors are `{"detail", "code"}` with a stable `code`.

| Endpoint | Purpose |
|---|---|
| `GET /v1/regions` | Import regions, status (`available` only if every ADR 009 gate passed), data version |
| `GET /v1/attributions` | Credits to show: OpenStreetMap, GeoNames, map tiles |
| `GET /v1/trips/{id}/export`, `GET /v1/trips/export`, `POST /v1/trips/import` | The trip file (ADR 028): one trip or every trip as JSON of `format: "detour-trip"`, `format_version: 1`, and the import of such a file as new trips, all or nothing; no identifier of ours is in it |
| `GET /v1/destinations/search` | Cities (GeoNames) and areas (OSM boundaries) by name; accents, case and alternate names ignored; each result says whether its region can be planned. `include_external=true` asks Photon only if nothing matches locally, or always with `also_if_found=true` (ADR 027: the app's "Search more widely"); a Photon result becomes a `place` trip destination (snapshot, no `geo` row; suggestions are refused with `destination_not_plannable`) |
| `GET /v1/places/search`, `GET /v1/places/{id}` | Imported places by name and/or around a point; a place with its provenance and licence |
| `POST/GET/PATCH/DELETE /v1/trips`, `POST/GET /v1/trips/{id}/archive`, `GET/PATCH …/visits` | Trips (city or area destination, days, optional start date; no currency, budget or price bands since ADR 017) and the past-trip archive (ADR 006): marked by the user or made when reading the trips two days after the last day; `GET …/archive` reports its size |
| `POST/GET /v1/trips/{id}/itineraries`, `GET/DELETE /v1/itineraries/{id}` | Manual (empty) itineraries and their days; engine itineraries arrive in Phase 4 |
| `POST /v1/itineraries/{id}/days/{n}/items`, `GET/PATCH/DELETE /v1/items/{id}` | Visits, meals and free time with validation (place kind, duration, times, overlap, positions) |
| `POST/GET/PATCH/DELETE /v1/user-places` | Places the user pinned or saved from an external search result |

The layers are routers (`routers/`), Pydantic models (`models/`), repositories (`repo/`, SQL with
bound parameters, no ORM) and one adapter (`adapters/photon.py`). Each request commits its
transaction before the response is sent.

#### 4.2.3 Phase 4 API

| Endpoint | Purpose |
|---|---|
| `POST /v1/trips` with `destination_kind: route`, `PUT /v1/trips/{id}/stops`, `POST /v1/trips/{id}/stops/preview` | Multi-city trips (ADR 024): 2 to 6 stops whose days add up to the trip; `Trip.stops`, `stops_version`; the name follows the stops (fixed table, `naming.py`). With a chosen plan, a stop edit is a change set (`edit_stops`) repaired from the current plan (`planner/stop_edits.py`, `planner/stop_service.py`) and applied like any other; without one the stops are replaced. Refusals: `route_needs_two_stops`, `too_many_stops`, `stop_days_mismatch`, `stop_repeated`, `destination_not_found`, `409 region_not_available`, `LOCKED_ON_DROPPED_DAY`, `stops_changed` (choosing a plan made for earlier stops) |
| `POST /v1/trips/{id}/itineraries/generate` | Plan a city or area trip: one generation of two itineraries (Essentials, Wider), or one with the reason; replaces earlier unselected proposals. `422 area_single_city_only` (an area in Japan, D4), `422 planning_impossible` (with `issues`), `409` for a past trip, an unavailable region or the limit of 5 |
| `GET /v1/itineraries/{id}`, `GET /v1/trips/{id}/itineraries` | Now also the generation id, seed, diversity score, plan notes and statistics; per item the rendered reasons and the transfer to the next item (mode, seconds, metres, `routed` or `estimated`) |
| `GET /v1/images/{id}`, `Trip.cover_image`, `Item.image` | Photos (ADR 022): the backend streams the stored JPEG from Supabase Storage (public, immutable cache headers, no token) so the app never calls the storage host; trips and items carry a `Photo` (path, average colour, size, credit line) found in `geo.image_lookup`, never a hidden one. Cities and areas use a fallback chain (the item's image, its English Wikipedia lead image, its Commons category; ADR 022 amendment). The API resolves photos itself in the background after a trip is created, generated or the trips are read (`images/background.py`: one run at a time under a Postgres advisory lock, resumable, at most 100 lookups); the "Resolve images" workflow stays as an operator tool |
| `GET /v1/destinations/{kind}/{ref}/cover-candidates`, `GET /v1/cover-previews/{id}`, `PUT /v1/trips/{id}/cover` | "Change photo": up to 12 photos that pass the gate, with 500 px previews made and served by the backend, cached a week; choosing one stores it like an automatic photo and sets the trip's cover (null: the automatic photo again) |

The engine is `detour_api/planner/` (section 5); its reads and writes are `repo/planning.py`. Hand
edits of items delete transfers that no longer join neighbours (they are not recomputed; adding or
removing a place through a change set, section 4.2.5, recalculates the days it changes).

#### 4.2.4 Phase 6 API (ADR 016; meals removed by ADR 026)

- Generated itineraries contain **sights only**. A restaurant or café stop (`type = meal`) is one the
  user added; it carries `restaurant: {venue_type}` (restaurant or cafe, from the user's place) and no
  meal type or cuisine.
- Days carry `base_city_name` and, on the first day at a new base city of an area, `arrival`: the
  drive from the previous base (mode, seconds, metres, `routed` or `estimated`). For a multi-city
  trip (ADR 024) a leg into or out of a country travelled by rail is `mode` and `confidence`
  `unknown` with no seconds or metres: no time is invented, and the day is planned in full.
- Statistics add `meals`, `meal_minutes` and `intercity_legs`.
- Destination search adds `unavailable_reason` (`region_not_available`, `area_single_city_only`).

#### 4.2.5 Phase 7 API (ADR 018)

| Endpoint | Purpose |
|---|---|
| `POST /v1/itineraries/{id}/change-sets` | Preview `add_place` (an imported sight by `place_id`, or a user place of kind `city` or `location` by `user_place_id` with `duration_minutes`) or `remove_place` (`item_id`) on a planned itinerary. Stores the change set with its proposal and returns the diff (added, left out, moved, new times, base changes, travel change, estimated legs) and notes. Nothing in the itinerary changes. `422 recalculation_impossible` with `issues`; `409 not_recalculable` for a hand-made itinerary |
| `GET /v1/change-sets/{id}` | One change set: `pending`, `applied`, `discarded` or `expired` |
| `POST /v1/change-sets/{id}/apply` | Keeps the current version, writes the previewed proposal exactly, increments the version; returns the change set and the itinerary. `409 change_set_stale` if the itinerary changed since the preview |
| `POST /v1/change-sets/{id}/discard` | Closes the change set; the itinerary is untouched |
| `GET /v1/itineraries/{id}/versions` | Earlier versions, newest first, with what replaced each (a change set or a hand edit) |

Code: `planner/recalc.py` (the repair), `planner/diff.py`, `planner/revision_validator.py`,
`planner/change_service.py` (read, recalculate outside a transaction, write, with per-stage
timings), `repo/changes.py` and `repo/plan_state.py`. User places may now carry `search_provider`
`geonames` (a town from destination search, saved to add it to a plan).

### 4.3 Data stores

- **PostgreSQL + PostGIS**, two schemas kept deliberately separate (both exist and are empty
  after the first Alembic migration; PostGIS is enabled where first needed, ADR 010):
  - `geo`: imported open data (OSM-derived places, GeoNames gazetteer, Wikidata signals,
    countries, currencies (GeoNames reference rows, unused since ADR 017), travel-time cache).
    Rebuildable from sources.
  - `app`: user data (installations, trips, itineraries, items, user places, later photos).
- The separation is also a licence boundary: `geo` contains ODbL-derived data; `app` is
  independent data that references it by identifier. See `docs/data-model.md`, section 5.

### 4.4 Region import pipeline

**Implemented in Phase 2** as `python -m detour_api.importer` and the manually started workflow
`.github/workflows/import-region.yml` (ADR 005, ADR 012). Steps 1 to 4 and 7 are built; step 5
(Wikidata) and step 6 (Valhalla tiles) are not. The sequence as built:

1. download the Geofabrik extract with an identifying User-Agent;
2. `osmium tags-filter` keeps the candidate objects;
3. `osm2pgsql` (flex output, `importer/osm.lua`) loads them into a temporary PostGIS;
4. Python applies the selection rule (`importer/selection.py`, ADR 003 and ADR 011), derives
   places and signals, and counts every exclusion by class and reason (restaurants and cafes are
   not candidates, ADR 026);
5. the rows are loaded into Supabase through the session-mode pooler in one transaction, the
   report is checked against the database, gates 4 to 6 of ADR 009 are evaluated, and the region
   becomes `available` or `disabled`.

Run twice on the same extract, it leaves identical data (tested). The original design follows.

A command-line job, run by the operator, that makes a region usable:

1. Download the region's OSM extract.
2. Filter and load attractions and other relevant features into `geo.place` with
   their source tags preserved.
3. Apply the attraction selection rule (ADR 003): wayside shrines and crosses, boundary stones,
   bomb craters and memorials without a `wikidata` tag are not imported. Count what was excluded.
4. Load the gazetteer rows (GeoNames) covering the region.
5. Fetch Wikidata signals for places that carry a `wikidata` tag.
6. Build Valhalla tiles from the same extract.
7. Record an `import_run` with source dates and counts, and publish a **data quality report**
   (how many places, share with Wikidata link, objects excluded per class).

The MVP supports operator-imported **pilot regions**: Japan, Italy, Austria, Czechia and
Hungary (D2). A
request for a destination outside them returns a clear "region not available" response.
On-demand import is a post-MVP item.

### 4.5 Travel-time service

**Built in Phase 3** (`detour_api/travel/`, `adapters/valhalla.py`, ADR 004 and ADR 013). Internal
interface, on `app.state.travel_time`: `cells(pairs, mode)` (sparse, the one Phase 4 should use),
`matrix(points, mode)` (every ordered pair), `travel_time(a, b, mode)` and
`route_geometry(a, b, mode)`. Modes: walking and driving. Each result carries a confidence label
(`routed` or `estimated`), a source and, for an estimate, a reason.

| Order | Source | Confidence label |
|---|---|---|
| 1 | Cache (`geo.travel_time`): routed rows, and "no route" rows until they expire | as stored |
| 2 | FOSSGIS Valhalla through the adapter, for misses only | `routed` |
| 3 | Straight-line distance x a detour factor (walking 1.8, driving 1.3), converted at a mode speed | `estimated` |

- **Request shape (fixed, `matrix-v1`):** one source and up to 100 targets per matrix request;
  cells farther apart than about 150 km are one route request each. A pair always takes the same
  path, so cached times never mix shapes.
- **Safety:** token bucket (1 per second, burst 10), circuit breaker after any 429 or error, a
  10 s timeout, a daily budget of 1,500 calls, `User-Agent` and `X-Client-Id` headers. A
  `max_seconds` argument bounds the time one operation spends waiting on the provider; the cells
  not reached are estimated.
- **Estimates made because the provider was unavailable are not stored.** A cell the provider has
  no route for is stored as `estimated` with no number and asked again after 30 days.
- **Route geometry** is fetched for the selected itinerary only, returned and never stored.
- **Size:** the cache is capped at 100,000 rows, measured at 20.7 MB; it counts toward gate 6.
- Plan generation never calls the provider if asked not to (`use_provider=False`): it then reads
  the cache and estimates.

Any failure (adapter off, provider down, budget used, rate limit, time limit, unreadable answer)
gives the labelled estimate, so planning stays available. Details and unverified assumptions:
ADR 013.

#### 4.2.6 Phase 8 API (ADR 019; **reduced by ADR 026**)

`POST /v1/itineraries/{id}/restaurant-suggestions` and the change-set action `add_restaurant` are
**removed**, and so are `planner/restaurant_slots.py` and the imported restaurants. What remains:

| Endpoint | Purpose |
|---|---|
| `GET /v1/restaurants/search` | Restaurants and cafés: the user's saved ones first, then, with `include_external` and only when none matches, Photon through the backend (restaurants and cafés only, each with its `venue_type`; no cuisine, no meal types). Manual entry is `POST /v1/user-places` with kind `restaurant` or `cafe` |
| `POST /v1/itineraries/{id}/days/{n}/items` | Places the stop (`type = meal`, `user_place_id`) on the day and time the user chose, with a default length of 75 minutes (restaurant) or 45 (café); no preview |

### 4.6 Other services

- **Search service (built in Phase 2):** local trigram search over the gazetteer, the areas and
  the region's places; if nothing suitable is found and the caller asked for it, a Photon query
  through the backend (`adapters/photon.py`: User-Agent, timeout, cache, daily budget, pause on
  failure); finally a manual entry (name plus map pin) saved as a user place. Restaurant search
  (Phase 8) searches the user's saved places, then Photon, with its own endpoint and a tag filter that
  is checked again on the way back (ADR 019, ADR 026).
- **FX service:** removed (ADR 017): the app has no currencies or prices.

### 4.7 Place names (ADR 025)

Built 2026-11-14; full description in [`multilingual-place-names.md`](multilingual-place-names.md).
One resolver (`detour_api/names/`) chooses the English-facing name of a place, city or area and keeps
its original local name:

| Order | Source | Confidence |
|---|---|---|
| 1 | The user's approved name (`app.place_name_override`, per installation) | 1.00 |
| 2 | An English name the provider marks official (no source today) | 0.99 |
| 3, 4 | Wikidata English label, English Wikipedia title (`geo.place_name`, fetched lazily) | 0.98, 0.97 |
| 5 to 8 | OSM `name:en`, `official_name:en`, `brand:en`, `short_name:en`, Latin `int_name` | 0.93, 0.85 |
| 9 | The source's romanization (`name:ja-Latn`, `name:zh-Latn-pinyin`, `name:ko_rm` …) | 0.85 |
| 10, 11 | Detour's transliteration: language-specific, then generic, labelled "Automatically romanized" | 0.70, 0.35 |
| 12 | The original local name | |

Businesses keep their own name (only an official English, English brand or Latin international name
replaces it). Han characters, Arabic script, Hebrew and Thai are never transliterated; nothing is
machine-translated. Reads never call a provider: they combine the import's names, the stored Wikidata
names (expired ones too) and the caller's override. The Wikidata lookups (labels, aliases, sitelink;
a city through its GeoNames id; a place through its QID or Wikipedia sitelink; coordinates only as a
controlled operator fallback) run in the background after a trip is created, generated or read, and
from `python -m detour_api.importer names`, through the ADR 022 Wikimedia adapter; "no English name"
is cached for 90 days. Plan generation uses the stored names and never waits for or calls Wikidata.
Endpoints: `names` (`PlaceName`) on place search, place detail and items;
`PUT`/`DELETE /v1/places/{id}/display-name` (Edit display name). Search matches every name and alias
(`geo.place.alias_norm`, `geo.place_name`), normalised separately from display.

## 5. Planning engine

The engine is a pure function of `(request, data version, engine version)`, plus the travel times
the travel-time service returns (each transfer records whether its time was routed or estimated).

**Built in Phase 6 (v2, [ADR 016](decisions/016-phase-6-meals-and-area-destinations.md)):** step 1
for areas (base cities, days per base, inter-city legs) and step 5 (meals in fixed windows at
imported places to eat), with the validator checking meal windows and day length. Code:
`planner/areas.py`, `planner/meals.py`, and the engine, validator and configuration below.
Section 5.4: adding a city or location is built in Phase 7 (ADR 018); adding a restaurant in
Phase 8 (ADR 019).

**Built in Phase 4 (v1, [ADR 014](decisions/014-phase-4-planner-v1.md)):** city destinations;
steps 2, 3, 4, 6, 7 and 8 below, the two profiles and the diversity gate of section 5.3, and the
determinism rules of section 5.6. What v1 does differently from the outline below: the only time
windows are the day (09:00 to 18:00 for Essentials, 19:00 for Wider, inside the 09:00–22:00
window), because opening hours are out of scope (ADR 003) and meals come in Phase 6; planning uses
cached travel times and labelled estimates for a sparse cell set, and only the transfers of the
finished plans are asked of the provider, within 3 s; days whose routed transfers no longer fit
drop their lowest-value visit. Code: `planner/engine.py` (pipeline), `scoring.py`, `durations.py`,
`sequencer.py`, `travel.py`, `validator.py`, `reasons.py`, `config.py`.

### 5.1 Inputs

Destination (a city or an area), trip length in days, optional start date, and items the user
has added or locked. Defaults that the user does not see as features: day window (for example
09:00–22:00), meal windows, and walking threshold. These live in a versioned configuration file.

> **ADR 026 (proposed, 2026-11-14; planner step built):** the engine (`planner-3.0.0`) produces
> **sights only**: no meals, no restaurant lookup, one unplanned 90-minute midday gap per day
> (`planner/daylayout.py`, idle time, not an item), a 09:00–20:00 window, and recalculation that
> keeps that gap and treats a restaurant or café stop as fixed. The Phase 8 slot engine (section
> 4.2.6, section 5.4 "Add a restaurant") is **removed**: a restaurant is a stop the user adds with a
> chosen day and time. Restaurants, cafés and cuisines have left `geo` and the API (migration `0014`). Sections
> below that mention meals describe the engine before this change.

### 5.2 Pipeline

1. **Scope.** Resolve the destination to a geometry. For an area, select candidate base cities
   by population and attraction density, and allocate days to them. For a multi-city trip
   (ADR 024) the bases are the user's stops, in the user's order, with the user's days: nothing is
   chosen or reordered; each candidate belongs to its nearest stop, and a city that comes back later
   shares its candidates without repeating a visit. The diversity gate also looks at each stop.
2. **Candidates.** Select attractions inside the scope; score them deterministically from OSM
   category, heritage and tourism tags, and Wikidata notability. Remove duplicates.
3. **Durations.** Assign an estimated visit duration from a category rule table (for example
   museum, viewpoint, park, place of worship). No free source provides visit durations, so the
   table is ours, versioned, and each item's duration is editable by the user.
4. **Day construction.** Solve the multi-day selection and ordering within the day window;
   visits that do not fit are dropped by priority. (Opening hours are out of scope, ADR 003.)
5. **Meals.** Reserve time for each profile's meals (Essentials lunch and dinner, Wider also an
   afternoon snack) in fixed windows by meal type, with lengths by meal type and venue type. For
   each, choose an imported place to eat whose venue type serves that meal, near the visits before
   and after it, varying cuisine across the trip. No opening hours (ADR 003) and no prices
   (ADR 017).
6. **Transfers.** Insert a transfer between consecutive items with mode, duration and
   confidence.
7. **Validation.** An independent checker verifies every produced itinerary: no overlaps, day length respected, locked items untouched. A failed check is a
   bug, not a user-visible itinerary.
8. **Explanation.** Each item carries reason codes such as `WIKIDATA_LINKED`,
   `NEAR_PREVIOUS_ITEM`, `LUNCH_WINDOW`, `NEW_CUISINE`, `CUISINE_NOT_SPECIFIED`.

### 5.3 Two meaningfully different itineraries

Variants are produced by **strategy profiles**, each a different weighting of the same engine:

| Profile | Emphasis |
|---|---|
| Essentials | Highest-ranked sights, compact days, least travel |
| Wider | More areas or cities, more variety of categories, more travel accepted |

A **diversity gate** then compares the variants. The proposed test is that the Jaccard
similarity of their visit sets is at most 0.6, or that their city/day allocation differs. If the
gate fails, shared lower-priority visits are penalised in the second profile and it is solved
again. If the destination is too small to support two distinct plans, the response says so
rather than presenting near-duplicates. The threshold is tuned in Phase 4 against fixtures.

**As built (ADR 014):** threshold 0.6; Wider is solved again with the shared visits worth 50 %,
20 %, then 0 % of their value; a second plan with fewer than half the first plan's visits does not
count as an alternative; the single-plan response carries the note `SINGLE_PLAN`. For one city
the "different allocation" alternative cannot apply. **Areas (ADR 016):** Essentials uses a base
city per 4 days and Wider one per 3, so their base cities or days per base usually differ, which
makes them distinct even when their visits overlap more than 60 %.

### 5.4 Edits and recalculation

> **Planned, ADR 029:** **Optimize** is a change-set action (`optimize`, scope `within_days` or
> `across_days`) in a new `planner/optimize.py`. It reorders a hand-made or planned plan for the
> least travel, starting from the current order and accepting only strict improvements, so it is
> never longer. Every stop is kept; restaurants stay on their day within 60 minutes of their chosen
> time and not after 21:00; locked and document-bearing (app-supplied `fixed_item_ids`) stops stay;
> a stop stays in its own city's days. Travel uses cache and labelled estimates, then the provider
> for the final days' legs. An independent revision validator checks the proposal.

- **Add a city or location.** The new place becomes a mandatory visit. The engine re-solves with
  a **stability cost** that penalises moving existing items to another day or reordering them,
  and never moves locked items. If the place is another city, day allocation is recomputed. The
  response is a diff (added, moved, removed, time changes) that the user accepts or discards.

  **As built (Phase 7, [ADR 018](decisions/018-phase-7-add-place-and-recalculation.md)):** the plan
  is repaired, not planned again. A place within 20 km of a base city is inserted into the day at
  that base with the lowest stability cost (travel weight x added travel minutes, 300 per visit
  that changes day, value + 200 per visit left out, 5 per item retimed); visits it pushes out move
  to another day at the same base if they fit, else they are left out and shown. A place farther
  away takes one day from a base with at least two (first or last of its run) for a new base city,
  the nearest town within 25 km, with ADR 016's inter-city legs; Japan stays single-city (D4).
  Locked items keep their day and times; items the user added are never left out; meals are laid
  out again in their windows at imported places to eat. Unchanged days are copied exactly. An
  independent validator checks every proposal. Removing the place the latest accepted change added
  restores the stored previous version exactly (undo through versioning).
- **Add a restaurant.** *(Removed by ADR 026: the user chooses the day and time; the text below
  describes the removed slot engine.)* For each day and each meal slot, the engine computes: the extra travel
  caused by inserting it between the
  neighbouring items; the shift imposed on later items; whether the slot already has a meal; and
  how well the venue type suits the meal (opening hours are out of scope, ADR 003). The lowest-cost slot wins,
  ties are broken by earlier day then earlier slot, and the next-best alternatives are returned
  with their reason codes.

  **As built (Phase 8, [ADR 019](decisions/019-phase-8-add-a-restaurant.md)):** the restaurant is a
  meal the user adds. It is first a floating entry that the day's layout starts when its meal window
  (ADR 016) opens or when the traveller arrives, and refuses if it would end after the window or the
  profile's day end; the stored result is a fixed meal. Every day with visits and every meal type
  the place serves is a slot; each slot's best position is chosen among the four with the least added
  travel, and the slots are ranked by cost (added travel, straight-line detour, shifted items and
  minutes, waiting for the window, replacing a planned meal, a repeated cuisine, unknown meal
  types). The three cheapest come back with reason codes, the estimated detour and the items that
  move. No visit is left out or moved to another day. Placing is a change set (preview, apply,
  versions); the revision validator checks the window, the day and the place.

### 5.5 Is OR-Tools justified?

The core problem is selecting and ordering optional visits across several days, each with
meal windows and a day-length limit. This maps onto OR-Tools' routing solver: days are
vehicles, meal windows are time windows, and optional visits are disjunctions with penalties,
all of which its documentation covers.

| Option | For | Against |
|---|---|---|
| Hand-written heuristic (greedy insertion + local search) | Small, transparent, no dependency, easy to make deterministic | Expected to be weak once time windows, optional visits and stability costs combine; S5 measured a 6–8% gap on two of three fixtures |
| OR-Tools routing solver (Apache 2.0) | Handles the combined constraints; mature | Native dependency; time-limited search can end at different points on different machines |

**Outcome of spike S5 (2026-11-12): the heuristic only; OR-Tools is not adopted.** Details in
[`spikes/s5-sequencing-findings.md`](spikes/s5-sequencing-findings.md). Measured on three synthetic
fixture trips (3-day city, 7-day region, 14-day multi-city) with meal windows and the day length
as the only time windows:

- **Quality:** where OR-Tools found a plan, its best repeatable configuration was 6–8% better on
  the shared objective than the heuristic on the city and regional trips (2–6% more score). On
  the 14-day trip the heuristic was as good as the best OR-Tools result.
- **Latency:** the heuristic needs 7–43 ms per plan. OR-Tools needs 0.1–1.3 s for a plain
  descent and 1.7–4.2 s with guided local search for 100 solutions, per variant; on a GitHub
  x86-64 runner two such variants take about 8 s against the 5 s KPI for the whole request.
- **Robustness:** on the 14-day trip, a day that starts late (after an inter-city drive) made
  every insertion-based first-solution strategy return no plan within 60 s. Only "start with
  nothing planned" found one, in 18 s. A sequencer that can return nothing for a feasible trip
  would need the heuristic as a fallback anyway.
- **Determinism:** solution-count limits gave identical plans on Linux x86-64, Linux arm64 and
  Windows, but only while the 60 s wall-clock safety cap was not reached. Where it was reached
  (7-day trip, 1,000 solutions) the slower machines returned a different plan. What a
  "solution" counts also depends on the first-solution strategy (100 solutions lasted 70 ms with
  one and 2 s with another). The heuristic gave the same plan on every machine.

**Consequences.** The `Sequencer` interface stays, with the heuristic as its only
implementation (greedy best-gain insertion, then 2-opt, relocation, swap-in and re-insertion in
a fixed order, ties by identifier, no randomness, no clock). Every run is deterministic by
construction, so golden tests need no solver limits. OR-Tools may be reconsidered only through a
new spike on real imported data, if the Phase 4 or Phase 6 fixture KPIs show the heuristic
falling short, and then only behind the same interface with the heuristic as fallback.

### 5.6 Determinism rules

- Stable ordering everywhere, with ties broken by place identifier.
- No wall-clock or random input without a fixed seed stored in the itinerary record.
- Each itinerary stores the engine version, configuration version and import-run identifier.
- Golden tests: fixed fixtures must reproduce byte-identical itineraries.

## 6. External integration rules

1. Every provider is wrapped by an adapter implementing a capability interface (tiles config,
   search, routing).
2. Every outbound call sends an identifying User-Agent with a contact address, has a timeout,
   and is cached according to the provider's terms.
3. A per-provider daily budget counter stops calls before a published quota is reached and
   degrades to the next source.
4. Provider URLs and keys are configuration, never constants in the app.
5. An **attributions** endpoint lists the credits currently required; the app shows them on the
   map and on an About screen.
6. A provider may only be added through an ADR that records its verified terms.

## 7. Cross-cutting concerns

- **Privacy.** No analytics SDK in the MVP. Search text sent to Photon goes through the backend,
  so the provider never sees the user's device. Location permission is not required by any MVP
  feature.
- **Attribution.** "© OpenStreetMap contributors" and the tile provider's credit on the map;
  GeoNames and Wikidata (optional) on the About screen.
- **Failure behaviour.** Routing down → estimated times. Search provider down → local results
  and manual entry. Tiles down → itinerary list still
  works; map shows an error with retry.
- **Testing.** Engine unit and golden tests; validator property tests; adapter contract tests
  against recorded responses; API tests; app component tests; one end-to-end path on Android.
- **Observability.** Structured backend logs with request identifiers and per-stage planning
  timings, which also feed the KPIs.

## 8. Environments and cost

| Environment | Composition | Recurring cost |
|---|---|---|
| Development and tests | GitHub Actions (CI-first, `docs/development.md`); Docker Compose (`db`, `api`) optional | none |
| Personal production | Supabase Free database, Render free web service, GitHub Actions import (ADR 005); OpenFreeMap; Photon public instance; FOSSGIS Valhalla (ADR 004) | $0 per month at the limits read on 2026-11-12 |
| Public commercial | Self-hosted or contracted tiles, self-hosted Photon and routing, legal review of ODbL use | to be estimated |

Known platform costs: none while the app is not distributed through app stores (ADR 008). An
Apple Developer Program membership ($99 per year) is optional for the iOS phase. Google Play
registration ($25 once, plus a closed test with 12 testers for 14 days for new personal
accounts) would apply only if the owner later chose Google Play. Backend hosting is decided in
ADR 005.

## 9. Architecture risks

| Risk | Effect | Mitigation |
|---|---|---|
| OSM data is thin in a chosen region | Poor itineraries | Data quality report gates a region; Overture and Foursquare OS Places as supplements |
| Many mapped "attractions" are not sightseeing (shrines, stones) | Noisy candidates | Selection rule (ADR 003), Wikidata signal |
| Region-pack model limits "any destination" | Product feels narrow | Explicit pilot regions; on-demand import after MVP |
| Routing capacity: FOSSGIS limits (100 cells, 150 km per matrix, about 1 request per second) and no availability promise | Slow first plans, or blocking | Chunked matrices, route requests for long legs, cache, labelled estimates; self-hosting fallback sized in S3 |
| OpenFreeMap discontinued | No map | Style URL from backend; PMTiles fallback rehearsed in Phase 9 |
| Two variants look alike | Core goal missed | Diversity gate and KPI |
| MapLibre React Native breaking changes | App build breaks | Pin versions; upgrade only with the Expo SDK |
| ODbL share-alike exposure | Legal risk at commercial release | Schema separation; legal review before commercial release |
