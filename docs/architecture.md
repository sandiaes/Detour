# Architecture

Status: **accepted** on 2026-11-12 through
[`decisions/001-technology-stack.md`](decisions/001-technology-stack.md) and
[`decisions/002-api-strategy.md`](decisions/002-api-strategy.md). Hosting (D3) is decided in ADR 005.
No code exists yet.

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
6. **Honest data.** Estimated travel times and absent prices are shown as
   unknown or estimated, never guessed silently.

## 2. Stack verdict

| Provisional choice | Verdict | Notes |
|---|---|---|
| React Native + Expo + TypeScript | **Confirmed** | Expo SDK 58 (React Native 0.88). The New Architecture is mandatory since SDK 55. A development build is required because MapLibre is not in Expo Go. |
| MapLibre + OSM-compatible data | **Confirmed** | `@maplibre/maplibre-react-native` v11 (MIT), Android and iOS. `expo-maps` is rejected: alpha, Google Maps on Android, Apple Maps on iOS. |
| Python + FastAPI | **Confirmed** | MIT. Pin the Python version in Phase 1 to one supported by both FastAPI and the OR-Tools wheels. |
| PostgreSQL + PostGIS | **Confirmed** | Image `postgis/postgis:18-3.7`. The `-3.5` and `-3.6` tags are no longer updated. PostgreSQL 18 changed the data volume path to `/var/lib/postgresql`. |
| Docker Compose | **Confirmed** for local development | Production hosting: ADR 005. |
| Deterministic planning engine | **Confirmed** | Section 5. |
| OR-Tools | **Conditionally justified** | Useful for the multi-day, time-windowed, optional-visit problem. Introduced behind an interface after a Phase 0 spike; a simple heuristic remains as baseline and fallback. Section 5.5. |

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
│  API layer        trips · itineraries · places · prices · config  │   (fallback: self-hosted PMTiles)
│  Planning engine  candidates → scoring → days → sequence → meals  │
│  Services         travel time · FX · search                       │
│  Provider adapters (one interface per capability)                 │
└────┬───────────────────┬──────────────────────┬───────────────────┘
     │                   │                      │
     ▼                   ▼                      ▼
PostgreSQL + PostGIS   Valhalla (regional    External, backend-only, cached:
 geo schema: open data  tiles, self-hosted)   Photon (search), Frankfurter (daily FX)
 app schema: user data

Offline pipeline (CLI, not request path):
 Geofabrik .osm.pbf ─┬─► POI/restaurant import ─► geo schema
                     └─► Valhalla tile build
 GeoNames dump ─► gazetteer      Wikidata ─► notability      Country/currency seed
```

All services except the tile host run from one Docker Compose file in development: `db`, `api`,
`valhalla`, plus one-shot `import` jobs.

## 4. Components

### 4.1 Mobile app

- Expo SDK 58, TypeScript, Continuous Native Generation with config plugins; no hand-edited
  native projects. This keeps the iOS build a configuration task, not a port.
- Development builds from the start. Android builds can run locally or on the EAS free plan
  (15 Android and 15 iOS builds per month, low-priority queue).
- MapLibre React Native for all map rendering. The style URL is read from a backend config
  endpoint, so the tile provider can change without a release.
- `expo-sqlite` holds a read cache of the user's trips so that an accepted itinerary is viewable
  without a connection. Planning and recalculation always need the backend.
- No direct calls to any third-party API other than the tile host.
- Platform-specific behaviour is limited to permissions and build configuration.
- Navigation, server-state and form libraries are chosen in Phase 5 and recorded in an ADR.

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
  - price records: add expected or actual price
  - config: map style URL, attribution list, data versions

### 4.3 Data stores

- **PostgreSQL + PostGIS**, two schemas kept deliberately separate:
  - `geo`: imported open data (OSM-derived places, GeoNames gazetteer, Wikidata signals,
    countries, currencies, FX rates, travel-time cache). Rebuildable from sources.
  - `app`: user data (installations, trips, itineraries, items, price records, later photos).
- The separation is also a licence boundary: `geo` contains ODbL-derived data; `app` is
  independent data that references it by identifier. See `docs/data-model.md`, section 5.

### 4.4 Region import pipeline

A command-line job, run by the operator, that makes a region usable:

1. Download the region's OSM extract.
2. Filter and load attractions, restaurants and other relevant features into `geo.place` with
   their source tags preserved.
3. Apply the attraction selection rule (ADR 003): wayside shrines and crosses, boundary stones,
   bomb craters and memorials without a `wikidata` tag are not imported. Count what was excluded.
4. Load the gazetteer rows (GeoNames) covering the region.
5. Fetch Wikidata signals for places that carry a `wikidata` tag.
6. Build Valhalla tiles from the same extract.
7. Record an `import_run` with source dates and counts, and publish a **data quality report**
   (how many places, share with cuisine, share with Wikidata link, objects excluded per class).

The MVP supports operator-imported **pilot regions**: Japan, Italy, Austria, Czechia and
Hungary (D2). A
request for a destination outside them returns a clear "region not available" response.
On-demand import is a post-MVP item.

### 4.5 Travel-time service

One internal interface: `matrix(points, mode)` and `route(from, to, mode)`.

| Order | Source | Confidence label |
|---|---|---|
| 1 | Cache (`geo.travel_time`) | as stored |
| 2 | Valhalla for the region | `routed` |
| 3 | Straight-line distance × detour factor ÷ mode speed | `estimated` |

The fallback keeps planning available when the routing container is down, and every transfer
shown to the user carries its confidence label. Modes in the MVP: walking and driving.

### 4.6 Other services

- **Search service:** local trigram search over the gazetteer and the region's places; if
  nothing suitable is found, a Photon query through the backend, cached; finally a manual
  entry (name plus map pin).
- **FX service:** a daily job stores reference rates; conversions read from the table and
  record the rate date used.

## 5. Planning engine

The engine is a pure function of `(request, data version, engine version)`.

### 5.1 Inputs

Destination (a city or an area), trip length in days, optional start date, and items the user
has added or locked. Defaults that the user does not see as features: day window (for example
09:00–21:00), meal windows, and walking threshold. These live in a versioned configuration file.

### 5.2 Pipeline

1. **Scope.** Resolve the destination to a geometry. For an area, select candidate base cities
   by population and attraction density, and allocate days to them.
2. **Candidates.** Select attractions inside the scope; score them deterministically from OSM
   category, heritage and tourism tags, and Wikidata notability. Remove duplicates.
3. **Durations.** Assign an estimated visit duration from a category rule table (for example
   museum, viewpoint, park, place of worship). No free source provides visit durations, so the
   table is ours, versioned, and each item's duration is editable by the user.
4. **Day construction.** Group candidates geographically, then solve the multi-day ordering
   with opening-hour time windows; visits that do not fit are dropped by priority.
5. **Meals.** Reserve lunch and dinner slots. For each, choose a restaurant near the route
   position at that time, open or unknown at that time, varying cuisine across the trip, and
   respecting the user's budget where a price record exists.
6. **Transfers.** Insert a transfer between consecutive items with mode, duration and
   confidence.
7. **Validation.** An independent checker verifies every produced itinerary: no overlaps, day length respected, locked items untouched. A failed check is a
   bug, not a user-visible itinerary.
8. **Explanation.** Each item carries reason codes such as `HIGH_NOTABILITY`,
   `NEAR_PREVIOUS_ITEM`, `FITS_BUDGET`.

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

### 5.4 Edits and recalculation

- **Add a city or location.** The new place becomes a mandatory visit. The engine re-solves with
  a **stability cost** that penalises moving existing items to another day or reordering them,
  and never moves locked items. If the place is another city, day allocation is recomputed. The
  response is a diff (added, moved, removed, time changes) that the user accepts or discards.
- **Add a restaurant.** For each day and each meal slot, the engine computes: whether the place
  is open, closed or unknown in the slot; the extra travel caused by inserting it between the
  neighbouring items; the shift imposed on later items; whether the slot already has a meal; and
  how well the venue type suits the meal. Closed slots are excluded. The lowest-cost slot wins,
  ties are broken by earlier day then earlier slot, and the next-best alternatives are returned
  with their reason codes.

### 5.5 Is OR-Tools justified?

The core problem is selecting and ordering optional visits across several days, each with
meal windows and a day-length limit. This maps onto OR-Tools' routing solver: days are
vehicles, meal windows are time windows, and optional visits are disjunctions with penalties,
all of which its documentation covers.

| Option | For | Against |
|---|---|---|
| Hand-written heuristic (greedy insertion + local search) | Small, transparent, no dependency, easy to make deterministic | Weak once time windows, optional visits and stability costs combine |
| OR-Tools routing solver (Apache 2.0) | Handles the combined constraints; mature | Native dependency; time-limited search can end at different points on different machines |

**Recommendation.** Define a `Sequencer` interface. Ship the heuristic first as the baseline.
Run a Phase 0 spike comparing both on fixture trips; adopt OR-Tools as the default sequencer in
Phase 6 if it gives better plans within the latency budget. For reproducibility, bound the
search by solution count or iteration limits with a fixed first-solution strategy, and use the
wall-clock limit only as a safety cap. This determinism approach must be validated in the spike.

### 5.6 Determinism rules

- Stable ordering everywhere, with ties broken by place identifier.
- No wall-clock or random input without a fixed seed stored in the itinerary record.
- Each itinerary stores the engine version, configuration version and import-run identifier.
- Golden tests: fixed fixtures must reproduce byte-identical itineraries.

## 6. External integration rules

1. Every provider is wrapped by an adapter implementing a capability interface (tiles config,
   search, routing, FX).
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
  GeoNames, Wikidata (optional) and Frankfurter-related notes on the About screen.
- **Failure behaviour.** Routing down → estimated times. Search provider down → local results
  and manual entry. FX missing → amounts shown unconverted. Tiles down → itinerary list still
  works; map shows an error with retry.
- **Testing.** Engine unit and golden tests; validator property tests; adapter contract tests
  against recorded responses; API tests; app component tests; one end-to-end path on Android.
- **Observability.** Structured backend logs with request identifiers and per-stage planning
  timings, which also feed the KPIs.

## 8. Environments and cost

| Environment | Composition | Recurring cost |
|---|---|---|
| Local development | Docker Compose: `db`, `api`, `valhalla` | none |
| Personal production | Supabase Free database, Render free web service, GitHub Actions import (ADR 005); OpenFreeMap; Photon and Frankfurter public instances | $0 per month at the limits read on 2026-11-12 |
| Public commercial | Self-hosted or contracted tiles, self-hosted Photon and Frankfurter, legal review of ODbL use | to be estimated |

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
