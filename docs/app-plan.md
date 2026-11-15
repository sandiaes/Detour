# App plan

> **Direction change, 2026-11-14 ([ADR 026](decisions/026-trip-manager-first.md), proposed):** the
> app is a trip manager and history first; generated plans are sights only with a midday gap;
> restaurants and cafés leave the imported data and are added through Photon or by hand; the Phase 8
> slot engine is retired; past trips keep their days. Destinations outside the imported regions
> (ADR 027, built) are the first manager feature, trip export and import (ADR 028, built) the second. This section and the phases below
> describe what was built; ADR 026's "Build order" is the work from here.

Status: **Phase 0, 1 and 2 are done; Phases 3, 4, 5, 6, 7 and 8 are built and await the owner's acceptance** (the owner reported on 2026-11-13 that the app works on the phone); Phase 8 onward is proposed. Budgets, currencies and prices are removed for now (ADR 017). Each phase is small enough to review on its own
and ends with tests that prove it. A phase starts only when its dependencies are complete.

## 1. Decisions

Recorded on 2026-11-12 from the owner's answers.

| ID | Decision | Outcome | Status |
|---|---|---|---|
| D1 | Licence and commercial posture | **Open source and non-commercial.** Free non-commercial services (Open-Meteo, Transitous) become permissible, subject to their other conditions. | Decided |
| D2 | MVP coverage | **Pilot regions: Japan, Italy, and Central Europe (Austria, Czechia and Hungary at least).** | Decided |
| D3 | Backend hosting: where the API server, the database and the routing engine run when not on a local machine | Open. S2 measured about 145 MB of imported data for five countries (before ADR 003), so Supabase Free could hold the `geo` data. ADR 005 (accepted): Supabase Free for the database, a Render free web service for the API, a GitHub Actions import job. | **Decided** |
| D4 | Public transport after the MVP (Phase 10) | Approved. **Japan is planned as single-city trips** until then (owner, Phase 6 prompt; ADR 016). | Approved |
| D5 | Anonymous installation token, no accounts | Approved. | Approved |
| D6 | Weather excluded from the MVP | Approved. | Approved |
| D7 | OR-Tools only if the Phase 0 spike justifies it | **Not justified: the heuristic only.** Spike S5 found OR-Tools 6–8% better on two fixtures but 7–300 times slower, and unable to find any plan for the 14-day fixture with its usual strategies. See `docs/spikes/s5-sequencing-findings.md`. | Decided by the approved rule; the owner may override |
| D8 | OpenFreeMap tiles now, self-hosted PMTiles as rehearsed fallback | Approved. | Approved |
| D9 | Photos on-device first; cloud backup decided in the photo phase | Approved. | Approved |
| D10 | Restaurant prices from users only; default band limits set in Phase 8 | **Superseded by ADR 017** (2026-11-13): no prices, price bands, budgets or currencies for now. | Superseded |
| D11 | Which open-source licence, and when the repository becomes public | **Apache-2.0** (ADR 007). The repository stays private until the owner decides to publish it. | Decided |
| D12 | Opening hours | **Out of scope.** No closed-place warning. See ADR 003. | Decided |
| D13 | Attraction selection | Wayside shrines and crosses, boundary stones, bomb craters and most memorials are not imported. See ADR 003. | Decided |
| D15 | Past trips archive | Past trips are kept as a map and list of visited cities and attractions, without routing. See ADR 006. Built 2026-11-13, awaits acceptance. | Decided |
| D17 | Region readiness thresholds | ADR 009: six gates; Austria, Czechia and Hungary first, then Italy, then Japan. | Decided |
| D16 | Distribution | No app stores. Android by sideloaded APK; iPhone built on the owner's Mac. See ADR 008. | Decided |
| D14 | Hosting constraint | Owner has no server and wants free, managed services. Travel times come from the FOSSGIS Valhalla server through a cached adapter (ADR 004, approved); S3 stays the reference for self-hosting. | Constraint |

### Notes on the decided items

**D1.** "Non-commercial" describes how the app is operated: no subscriptions, advertising or
sales. An open-source licence cannot itself forbid others' commercial use. Usage limits of the
community servers (Nominatim, Overpass, FOSSGIS routing) are about load, not commerce, so they
remain development-only.

**D2.** Five countries is a large first footprint. The Phase 0 spikes measure it before
anything is committed:

- S2 runs for all five countries, because the data quality report is cheap and decides which
  regions are enabled.
- S3 sizes routing for one country first, then the rest.
- Place names in Japan need a display rule (local name, English name, romanised name) in
  Phase 2.

**D4 and Japan.** Travel between Japanese cities is mostly by rail. With walking and driving
only, multi-city itineraries in Japan will be weaker than in Italy or Central Europe. Options:
keep the MVP order and limit Japan to single-city trips at first, or bring Phase 10 forward for
Japan. **Settled (2026-11-13):** single-city trips in Japan for now; an area in Japan is refused
with `area_single_city_only` (ADR 016).

**D3 and Supabase.** Three things need a host: the API server, the PostgreSQL/PostGIS database,
and the Valhalla routing engine.

| Component | Supabase |
|---|---|
| Database | Viable in principle: it is PostgreSQL and PostGIS can be enabled as an extension. |
| API server (FastAPI) | Not hosted by Supabase; needs a separate server. |
| Routing engine (Valhalla) | Not hosted by Supabase; needs a separate server with enough memory and disk. |

Limits of the Supabase Free plan read on 2026-11-12: 500 MB database, shared CPU with 500 MB
RAM, 5 GB egress, at most 2 active projects, and projects paused after one week of inactivity.
The user data (`app` schema) fits easily. The imported data for five countries (`geo` schema)
is likely to exceed 500 MB; S2 measures it. Because a server is needed for the API and Valhalla
anyway, running PostgreSQL on that same server is the simpler default, with Supabase as an
option if the measured size fits or a paid plan is acceptable.

## 2. Phase overview

```
0 Spikes ─► 1 Scaffold ─► 2 Geo data ─► 3 Travel time ─► 4 Planner v1 ─┬─► 6 Restaurants ─► 7 Add place ─► 8 Add restaurant ─► 9 MVP release
                                   └──────────────────────────────────► 5 Mobile shell ────────────┘
After MVP: 10 Public transport · 11 iOS · 12 Photos · 13 More coverage · 14 Weather (if approved)
```

Phase 5 can proceed in parallel with Phases 3 and 4 once the API contract exists, using
recorded responses.

## 3. Phases to the MVP

### Phase 0 — Decisions and technical spikes

**Goal:** remove the largest unknowns before any structure is committed. Spike code is
throwaway and is not merged into the product.

| Spike | Question | Evidence to produce |
|---|---|---|
| S1 Map | Does MapLibre React Native render OpenFreeMap in an Expo development build on Android? Can the APK be built in GitHub Actions (ADR 008)? | **Done.** APK built in GitHub Actions in about 14 min; map confirmed on the owner's Galaxy S22 (Android 16); release-variant APK instead of a development build (ADR 008 addendum). `docs/spikes/s1-map-findings.md` |
| S2 Data | Is OSM data in the candidate pilot regions good enough? | Data quality report: attractions, restaurants, cuisine, Wikidata link |
| S3 Routing | What does a regional Valhalla instance need? | Tile build time, memory, matrix latency for 50 points |
| S4 | Removed: opening hours are out of scope (ADR 003) | none |
| S5 Sequencing | Heuristic versus OR-Tools on three fixture trips | **Done.** Heuristic only (D7). `docs/spikes/s5-sequencing-findings.md` |

- **Dependencies:** none; D2 is decided.
- **Exit:** a short findings note per spike; D2, D3 and D7 can be decided; verification gaps in
  `docs/api-evaluation.md` section 15 marked for this phase are closed.
- **Risks:** a pilot region with poor data; mitigation is to pick another region.

### Phase 1 — Project scaffolding and continuous integration

**Status: built and accepted on 2026-11-12.** The owner followed `docs/deployment.md`, deployed to
Render and Supabase, installed the APK, and reported that the app opens, Settings shows
"connected", and the map is visible. PostGIS was enabled on Supabase Free (step 3, reported 2026-11-12). Still
unconfirmed: the idle cold-start check (deployment step 9), which the owner is running. Choices and pinned versions: ADR 010. Not done and
carried forward: the project's own APK signing key (before any build is kept for real use), the
`app.installation` table (Phase 4), the navigation ADR (Phase 5), Supabase PostGIS availability on
the Free plan (confirm in `deployment.md` step 3).

**Goal:** an empty but complete skeleton that builds, tests and runs.

- **Deliverables:** repository layout (mobile app, backend, shared API contract,
  infrastructure); Docker Compose with database and API; health endpoint; installation
  registration and token check; OpenAPI contract and generated TypeScript types; linting,
  formatting, type checks and test runners in CI; an Android development build that calls the
  health endpoint.
- **Tests:** CI green; API health test; app smoke test.
- **Dependencies:** Phase 0, D5.
- **Risks:** toolchain version drift; mitigation is pinned versions recorded in an ADR.

### Phase 2 — Geo data foundation

**Status: built on 2026-11-12; accepted by the owner (reported 2026-11-12).** Everything below is implemented and tested
against a synthetic extract (ADR 011, ADR 012, `docs/data-model.md`). **No real extract has been
imported yet**: that is the owner's first acceptance step (`docs/deployment.md`, "Importing a
region"). Not done and carried forward: Wikidata sitelink counts, the category visit-duration
table (Phase 4), and a display rule for non-Latin names (gate 5, Japan). The automatic archive of
past trips was built later (ADR 006, amendment of 2026-11-13).

**Goal:** a pilot region's data is in the database and destinations can be searched.

- **Deliverables:** `geo` schema; region import command (places, restaurants, Wikidata
  signals, attraction selection rule from ADR 003); gazetteer import; country and currency seed; import-run record and
  data quality report; destination search endpoint; place search endpoint (local only).
- **Tests:** import runs twice with identical results; counts match the report; search returns
  expected results for a fixture list; spatial queries use indexes.
- **Dependencies:** Phase 1.
- **Risks:** tag normalisation takes longer than expected; mitigation is a narrow first
  category list.

### Phase 3 — Travel-time service

**Status: built on 2026-11-12, not yet accepted** (ADR 013, proposed). Implemented and tested
against a stub server: the adapter, the cache, chunking, the rate limiter and circuit breaker, the
daily budget, the estimate fallback, null-cell handling and route geometry. The build
environment cannot reach the server, so the owner ran a check by hand
(`docs/spikes/fossgis-request-shape-check.md`): the 523 s / 653 s difference is deterministic and
not caused by the algorithm, its cause is unknown, and the adapter's 1 x N shape agrees with the
plain route; `directions_type: none` shrinks route responses by 60% and is on. **Not done:**
latency was not measured; the null-cell format and `POST` are unconfirmed against the real
server; the estimate's detour factor looks low against the first real data (ADR 013). Matrix
symmetry is not asserted: walking times were 523 s one way and 622 s back.

**Goal:** routed walking and driving times, with a safe fallback.

- **Deliverables:** FOSSGIS routing adapter (ADR 004) with cache, chunked matrices (at most 100
  cells and 150 km each), single-route requests for legs between cities; estimated fallback with
  confidence label; route geometry. Self-hosted Valhalla only if the owner chooses it later (S3).
- **Tests:** matrix symmetry and sanity checks; fallback used when the container is stopped;
  cache hit on repeat; latency measured.
- **Dependencies:** Phase 2 (same extract), S3.
- **Risks:** FOSSGIS throttles or blocks the app; mitigation is the cache, labelled estimates and
  the self-hosting fallback measured in S3.

### Phase 4 — Planner v1: attractions and days

**Status: built on 2026-11-12, not yet accepted** (ADR 014, proposed). The engine
(`detour_api/planner/`), the generation endpoint `POST /v1/trips/{id}/itineraries/generate`, the
extended itinerary reads, and tests: golden files for five fixture trips, the validator against
each kind of broken plan, 3-, 7- and 14-day trips, incomplete data, impossible requests, routed
transfers, and latency. **Tried on synthetic fixtures only:** no real region is imported yet, so
the weights are untuned (the risk below). Known gaps: notability rests on OSM tags (Wikidata
sitelinks are not imported); first plans of a city have mostly estimated transfers until the
cache warms; 14 days in one city run out of distinct sights.

**Goal:** two different, valid itineraries of attractions for a city destination.

- **Deliverables:** candidate selection and scoring; visit-duration rule table; day
  construction with the baseline sequencer; transfers; two strategy profiles; diversity gate;
  independent validator; reason codes; plan-generation and read endpoints; `app` schema for
  trips and itineraries.
- **Tests:** golden fixtures reproduce identical output; validator passes on generated plans
  for a fixture set of destinations and durations; diversity threshold met or the single-plan
  response returned; latency within budget.
- **Dependencies:** Phases 2 and 3.
- **Risks:** itineraries feel arbitrary without popularity data; mitigation is tuning the
  scoring with the owner on real destinations.

### Phase 5 — Mobile shell

**Status: built on 2026-11-12, not yet accepted** (ADR 015, proposed). All deliverables below are implemented with component tests and an Android emulator workflow. The owner reported on 2026-11-13 that the app works on the phone, and asked for the emulator workflow to run **by hand only** (`e2e-android.yml`, `workflow_dispatch`). Map lines are straight connectors (no route geometry exists). Area destinations are enabled since Phase 6; the currency and meal budget fields were removed from the new-trip form (ADR 017).

**Goal:** create a trip, compare two proposals, view days and the map on Android.

- **Deliverables:** trip creation; proposals comparison; day list; map with visits and transfer
  lines; itinerary selection; attribution display; on-device read cache; error and empty
  states.
- **Tests:** component tests; one end-to-end flow on an Android emulator against a seeded
  backend (run by hand).
- **Dependencies:** Phase 1 contract; Phase 4 for live data; S1.
- **Risks:** map performance on low-end devices; mitigation is marker clustering and simplified
  geometry.

### Phase 6 — Restaurants in itineraries

**Status: built on 2026-11-13, not yet accepted** (ADR 016, proposed). Meal windows by meal type
(breakfast 07:30–10:00, lunch 13:00–15:00, afternoon snack 15:00–17:30, dinner 20:00–22:00) with
lengths by meal type and venue type; Essentials plans lunch and dinner, Wider also a snack;
breakfast is supported but not placed (the day starts after it). Places to eat come from the
imported data only, chosen by proximity (600 m, 1.5 km, 3 km rings), cuisine variety and venue
type; unknown cuisine shows as "Cuisine not specified"; no price, rating or opening hours. Areas
get base cities by sights and population (Essentials one per 4 days, Wider one per 3), days in
proportion, and inter-city legs from the travel-time service (route requests beyond 150 km). Japan
is single-city only. Reason codes for every meal, notes for bases and drives. The validator checks
meal windows and day length. Golden tests for three area trips added and the five city ones
updated. **Tried on synthetic fixtures only.**

**Goal:** plans include meals.

- **Deliverables:** meal windows in the heuristic sequencer (no OR-Tools, D7); area
  destinations with base cities and day allocation; meal slots with restaurant selection by
  proximity, cuisine variety and venue type; restaurant attributes in the API and app.
- **Tests:** meals inside meal windows; area fixtures produce sensible day allocation; golden
  tests updated.
- **Dependencies:** Phases 4 and 5, S5.
- **Risks:** restaurant data is uneven between countries; mitigation is the data quality
  report and cuisine-unknown handling.

### Phase 7 — Add a city or location, with recalculation

**Status: built on 2026-11-13, not yet accepted** (ADR 018, proposed). The user searches sights near
the trip, towns, or (when nothing matches) Photon through the backend, or drops a pin; the place
becomes a mandatory visit. The plan is repaired, not planned again: the day with the lowest
stability cost takes it, locked items keep their day and times, items the user added are never left
out, meals are laid out again in their windows at imported places to eat; a place over 20 km from
every base gets one day at a new base city (nearest town within 25 km) with ADR 016's inter-city
legs, taken from a base with at least two days; Japan stays single-city. The preview is a stored
change set with a diff (added, left out, moved, new times, base changes, travel change, estimated
legs); accept or discard; nothing changes before. Every replaced version is kept (30 per
itinerary); removing the place the latest change added restores the previous version exactly.
Infeasible changes return each conflicting constraint. Lock, unlock and remove are on every visit
in the app. Migration `0007`. Tests: locked items never move, diff equals the applied result, add
then remove restores the plan, a distant addition re-allocates a day, infeasible additions are
explained. **Tried on synthetic fixtures only:** every addition changed one day and moved no visit
to another day; 12 to 690 ms in the engine.

**Goal:** the plan absorbs an addition with minimal disruption.

- **Deliverables:** add-place flow (search, pin); user places; mandatory-visit handling;
  stability cost; locking; preview diff with accept and discard; itinerary versioning.
- **Tests:** locked items never move; diff matches the applied result; adding then removing
  restores the previous plan; adding a distant city re-allocates days.
- **Dependencies:** Phase 6.
- **Risks:** recalculation reshuffles too much; mitigation is tuning the stability cost with
  fixtures.

### Phase 8 — Add a restaurant *(slot engine to be retired, ADR 026)*

**Goal:** a manually added restaurant lands in the best slot. (Prices, budgets, price bands and
currency conversion were removed by ADR 017 on 2026-11-13.)

**Status: built on 2026-11-13, not yet accepted** (ADR 019, proposed). The user searches
restaurants (the map data, then their saved ones, then, when nothing matches, Photon through the
backend with its budget counter, then entry by hand with a name, a map pin or typed coordinates,
optional cuisines and optional meals, otherwise "Cuisine not specified"). Every day with visits and
every meal slot the place serves is scored (location, neighbouring stops, meal type and venue type,
the ADR 016 meal window, travel impact, cuisine variety); up to three suggestions come back with
reasons, the estimated detour and which items move. The meal always stays inside its window and
the day inside its hours (the layout refuses otherwise and the revision validator checks it); no
visit is left out or moved to another day for it. Placing it is a Phase 7 change set (preview with
a diff, accept or discard, versions). Removing an added restaurant is not built (open item in
ADR 019).

- **Deliverables:** restaurant search (local, then Photon through the backend, then manual
  entry); slot scoring and alternatives with reasons.
- **Tests:** scoring fixtures; suggestions respect meal windows and day length; manual entry
  without cuisine stays "Cuisine not specified"; provider budget counter stops calls at the limit.
- **Dependencies:** Phase 7.
- **Risks:** external search unavailable; mitigation is manual entry always being possible.

### Phase 9 — MVP hardening and release

**Goal:** a build fit for the owner's own real trips, installed as a sideloaded APK (ADR 008).
*Revised 2026-11-15:* the Play Console closed test is removed (ADR 008: no app stores), and the
scope follows the manager-first direction (ADR 026). Meals, restaurant slots and Japan single-city
checks no longer belong here.

- **Deliverables:**
  - an audit of what is built against what is accepted, with the list of items still "awaiting
    acceptance" turned into accepted, changed or rejected;
  - failure-mode handling and a clear state for each dependency being slow or down (Render cold
    start, Supabase paused or limited, FOSSGIS throttled, Photon unavailable, Wikimedia
    unavailable, tiles down);
  - tile-provider switch rehearsed with a PMTiles extract;
  - attribution and licence screen (OpenStreetMap, GeoNames, Wikimedia credits, tile provider);
  - `docs/privacy.md` and `docs/security.md`, covering the anonymous installation, documents
    kept on the phone only, `.detour` export files (which may contain documents), the location
    permission if used, and logs;
  - backup of the `app` schema (scheduled export, or the owner's recorded acceptance of the
    risk; Supabase Free has no backups, ADR 005);
  - a performance pass on the trip list, the plan map, Optimize and the multi-city planner;
  - the device checks the design system still owes (the "E2E Android" screenshot tour run once,
    `e2e/trip-flow.yaml` brought up to date with the screens);
  - deployment to the chosen host; a release-mode APK; `docs/android-release.md`,
    `docs/known-limitations.md`, `docs/ios-readiness.md`.
- **Tests:** full regression; KPI measurement run; chaos checks (routing down, search down,
  tiles down, images down); the journeys in Prompt 10 (`build-prompts.md`).
- **Dependencies:** the owner's acceptance of the built work (section 7), D3.
- **Risks:** hardening unaccepted work turns into feature fixes, so accept or reject first.
  Documents live only on the phone, so an uninstall loses them; the export and "Back up all
  trips" actions must be explained in the privacy note.

## 4. After the MVP

| Phase | Content | Preconditions |
|---|---|---|
| 10 Public transport | Transit legs from schedule data through self-hosted MOTIS or Transitous; mode choice between walk, drive and transit; feed attribution | D1, D4; feed licences reviewed for each pilot region |
| 11 iOS | Build configuration, permissions, platform testing, build on the owner's Mac and install by cable (no App Store; ADR 008) | The owner's Mac; Apple Developer Program ($99 per year) only if the free route proves unusable |
| 12 Photos | Pick photos, link to trip, day, city or item; on-device storage; later optional backup | D9; Play photo-permission policy respected |
| 13 More coverage | On-demand region import; supplementary places from Overture and Foursquare OS Places | Hosting capacity; matching rules |
| 14 Weather | Informational forecast overlay | D6 approved; D1 decides the provider |

GTFS-Realtime is considered only after Phase 10, and only for same-day use.

**Multi-city trips (ADR 024, built 2026-11-14, awaiting acceptance).** A trip can be an ordered list
of 2 to 6 cities chosen by the user, with the days of each; the planner plans each city and the legs
between them, and the cities can be edited later through change sets. Legs into or out of Japan stay
without a time until Phase 10 fills them in. Japan itself is not imported yet (gate 5, ADR 009).

### Note: which regions are loaded (2026-11-12, owner)

The five pilot regions are loaded ahead of time by the operator (workflow "Import region"); the
app offers only regions that are `available`. The owner chose to **keep it like this for now** and
to reconsider later. Ideas discussed, none decided or built:

- **On-demand import** (Phase 13) does not fit the current hosting: an extract such as Italy's is a
  2 GB download and a long job, the import needs a temporary PostGIS and `osm2pgsql` (not possible
  on Render's free plan, 512 MB), and Supabase Free holds 500 MB. It would need a background import
  with a "preparing this region" state, and probably an ADR.
- **Load only the regions of upcoming trips** and remove the others to stay under the database
  limit. Past trips and itineraries keep their own name and point snapshots and no foreign key
  crosses `app` and `geo` (ADR 006, ADR 012), so removing a region's `geo` data does not break
  them. Missing: a "remove region" operation (delete a region's places and areas, mark it
  `disabled`), for example as a small workflow.

### Manager and history (ADR 026, proposed)

Not a numbered phase. In the owner's order: (1) sights-only plans with a midday gap; (2) restaurants
and cafés removed from the data, cuisine and meal types removed, slot engine retired, Add a
restaurant through Photon and by hand; (3) past trips keep their days (all of (1) to (3) are built); (4) **destinations outside
the imported regions** (ADR 027, built); (5) **export and import of a trip as a file**
([ADR 028](decisions/028-trip-export-and-import.md), accepted and built: a `.detour` zip, import as a new copy); (6) **Optimize a hand-made trip** ([ADR 029](decisions/029-optimize-a-hand-made-trip.md),
accepted and built): the engine reorders the stops for the least travel, within each day or across
all days, restaurants within 60 minutes of their chosen time and never after 21:00, with a preview
and an undo; then saved
ideas, manual reordering, notes, trip summary and photos.

## 5. MVP exclusions

- Public transport and real-time transit data
- iOS build
- Photos
- Weather
- Destinations outside imported pilot regions; on-demand region import
- Accounts, sign-in, sharing, multi-device sync
- Offline map downloads and offline planning
- Restaurant ratings, reviews, prices and price levels; budgets and currencies (ADR 017)
- Imported restaurant, café and cuisine data (ADR 026)
- Public-holiday opening rules
- Accommodation as day start and end point
- Booking, payments, hotel availability, flight prices (never in scope)
- Any LLM or generative-AI component (never in scope)

## 6. Cross-phase risks

| Risk | Likelihood | Impact | Response |
|---|---|---|---|
| Open data too thin in a region | Medium | High | S2 gate; supplementary sources in Phase 13 |
| Free public service withdrawn or restricted | Medium | Medium | Adapters, backend-delivered configuration, named fallbacks |
| Plans not convincingly different | Medium | High | Diversity gate, KPI, owner review in Phase 4 |
| Hosting cost of routing and database | Medium | Medium | S3 sizing; small regions; D3 |
| Scope creep beyond the brief | Medium | Medium | Exclusion list; new features need an ADR |
| Library churn (Expo, MapLibre) | Medium | Low | Pinned versions; upgrade as a planned task |
| Licence obligations misread | Low | High | Schema separation; legal review before commercial release |

## 7. Recommended next task

**ADR 026 (2026-11-14, proposed):** all six build steps are **built** (planner, slot-engine removal,
data change, history record, app); destinations (ADR 027), export and import (ADR 028) and Optimize (ADR 029)
are built; saved ideas, notes and photos wait for the owner. The text below is older and still stands for the phases it names,
except where ADR 026 retires them (Phase 8's slot costs, the imported restaurants).

**Accept the built work (Phases 3 to 8 and the ADR 021 to 029 changes), then Phase 9 (MVP
hardening, revised 2026-11-15), when the owner asks for it (CLAUDE.md).** For Phase 8: confirm or change the slot costs of ADR 019 on a real imported city,
add a restaurant from the map data, one from the wider search and one by hand on the phone, and
decide whether removing an added restaurant is wanted. For Phase 7: confirm or change the stability costs and the 20 km / 25 km distances
of ADR 018 on a real imported city, and try adding a sight, a pin and a distant town on the phone. For Phase 6: confirm or change the meal windows, the profiles' meals and the
base-city rules of ADR 016 on a real imported area.
Phase 2 is accepted. For Phase 3: confirm or change the numbers in ADR 013 (especially the walking
detour factor). For Phase 4: import Austria, generate plans for two or three Austrian cities, and
confirm or change the weights, the duration table and the open items of ADR 014.

Carried forward from Phase 2 (the owner accepted it; these items were not reported as resolved):
Acceptance meant: deploy the new migrations (Render runs them at start), add the repository
secret `DETOUR_IMPORT_DATABASE_URL`, run the "Import region" workflow for **Austria** first, and
read the report and `review-sample.json` (ADR 011). Open items that need the owner:

- confirm or change ADR 011 (the selection rule): Austria is read; three classes were removed, only
  named tourist classes are kept, and restaurants and cafes are kept only within 500 m of an
  attraction or near a town (rules version 2026-11-12.4, applied at the next import). Re-import
  Austria once to see the new counts and size. Open: the memorial-subtype question, the Czechia
  sample, and temples and churches mapped only as `amenity=place_of_worship` (not imported; a gap
  for Italy and Japan);
- confirm the two ADR 012 owner decisions (no foreign keys across the schemas; the manual
  itinerary endpoint and the trip snapshot fields);
- the Geofabrik terms were checked by the owner on 2026-11-12 (`docs/api-evaluation.md` section
  4.1); the first real run (Austria) confirmed the GeoNames layouts and the `.poly` download;
- the `geo` data is larger than estimated (71 MB for Austria against about 9 MB in spike S2):
  find where the space goes before importing Italy (gate 6);
- the signing key for the APK (Phase 1 carry-over) and the navigation ADR (Phase 5).

Background: all Phase 0 spikes are done or removed (S1, S2, S3, S5; S4 removed). D2, D3 and D7
are decided.
