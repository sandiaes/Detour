# Detour — Claude Code build prompts (adjusted to the recorded decisions)

Adjusted on 2026-11-12 from the owner's original file "Dtour — Claude Code Build Prompts" (13
prompts). The project name is **Detour** (the original file said "Dtour"). Every change from the
original is listed in section 3, with its reason. Items that the original asked for but that the
recorded decisions removed are listed in section 4; the owner reviewed them on 2026-11-12 and
wants none of them for now. Each needs an ADR before it comes back. The prompt order was also
confirmed.

**Changed on 2026-11-13 (owner):** no budgets, currencies or prices in the app for now
([ADR 017](decisions/017-no-budgets-currencies-or-prices.md)); the Android end-to-end workflow runs
by hand only; every prompt below was rewritten to match, and each now starts with its status.
Prompts 1 to 9 are done or built; the next one is Prompt 10.

## 1. How to use this file

1. Give Claude one prompt at a time, in order.
2. Review the output, run the checks, and commit before the next prompt.
3. Do not let Claude continue to the next prompt on its own.
4. Each prompt is one phase of `docs/app-plan.md`. If a prompt and an ADR disagree, the ADR wins;
   tell Claude to stop and ask.
5. Prompts 1 to 11 reach the MVP. Prompts 12 to 15 come after it.
6. The model and effort lines are suggestions carried over from the original file.

### The owner's working environment (assumed in every prompt)

- A work PC (Windows) where nothing can be installed; browser access to github.com works, but
  GitHub Codespaces does not (its connection is blocked).
- A Mac, available for iPhone builds later.
- An Android phone on which the app is installed as a sideloaded APK.
- No server of the owner's own. Development and tests therefore run in **GitHub Actions** and in
  Claude Code's cloud sessions. Local Docker Compose is kept for any machine that can run it, but
  nothing may require a local Windows toolchain. Confirmed by the owner on 2026-11-12.

## 2. Fixed decisions (the prompts depend on these)

| Topic | Decision | Where recorded |
|---|---|---|
| Stack | React Native with Expo (development builds, never Expo Go), TypeScript, MapLibre React Native; Python with FastAPI; PostgreSQL with PostGIS | ADR 001 |
| No LLM | No LLM or generative-AI dependency anywhere; explanations are reason codes through fixed templates | CLAUDE.md |
| Out of scope, always | Booking, payments, hotel availability, flight-price comparison | CLAUDE.md |
| Opening hours | **Out of scope.** No closed-place warning | ADR 003 |
| Attractions | Wayside shrines and crosses, boundary stones, bomb craters and most memorials are not imported | ADR 003 |
| Data | OpenStreetMap extracts from Geofabrik imported per region; `geo` and `app` schemas kept separate | ADR 002, data model |
| Routing | FOSSGIS Valhalla server through a cached adapter: matrices of at most 100 cells and 150 km, one route request per long leg, labelled estimates as fallback; no self-hosted routing | ADR 004 |
| Hosting | Supabase Free (database), Render free web service (API, about one minute cold start), GitHub Actions import job; no automatic backups of `app` data | ADR 005 |
| Past trips | Archive of visited cities and attractions on a map, no routing | ADR 006 |
| Licence | Apache-2.0; repository private until the owner publishes it | ADR 007 |
| Distribution | No app stores; Android by APK; iPhone built on the owner's Mac | ADR 008 |
| Regions | Pilot regions Austria, Czechia, Hungary, Italy, Japan; enablement order and thresholds proposed in ADR 009 (not yet approved) | ADR 009 |
| Accounts | None. Anonymous installation token | app plan D5 |
| Weather, public transport, photos, iOS | After the MVP | app plan D4, D6, D9 |
| Money | **No budgets, currencies, prices, price bands or currency conversion** (owner, 2026-11-13) | ADR 017 |
| Meals and areas | Meals in fixed windows at imported places to eat; areas planned from base cities; Japan single-city only | ADR 016, app plan D4 |
| End-to-end test | The Android emulator workflow runs by hand only, never on every push | ADR 015 addendum |

Planned phases and their dependencies are in `docs/app-plan.md`.

## 3. What changed from the original prompts

| Original | Adjusted | Reason |
|---|---|---|
| "Dtour" | "Detour" | Project name. |
| 13 prompts in a different order | 15 prompts that follow the 14 app-plan phases | The original put add-city before the mobile app and restaurants, and the plan's dependencies differ. Mapping in the table below. |
| Prompt 1 (feasibility) | Marked done; replaced by Prompt 1 "Finish Phase 0" | The documents exist. Spikes S1 and S5 remain. |
| Prompt 2 asked for Windows PowerShell setup and local Docker Compose as the main path | CI-first; local Docker optional; Render and Supabase deployment guide | The owner cannot install software on the work PC (decision on environment, section 1). |
| Prompt 3 data model (User, Trip, TripPreference, ... PhotoAsset) | Folded into Prompt 4 and aligned with `docs/data-model.md` (anonymous installation, no user accounts, no photo asset yet) | D5 and the existing data model. |
| Prompt 4 provider abstraction (geocoding, place, restaurant, routing, transit, weather, currency providers called live) | Prompt 4 imports OSM data; Prompt 5 builds one routing adapter | Plan generation reads the database and cache (ADR 002, 004). Weather and transit providers are post-MVP. |
| Weather in the MVP | Removed | D6. |
| Opening hours in planning, restaurants, UI, tests and the beta journeys | Removed | ADR 003. |
| Variants "highlights, relaxed, culture, food, nature" | Two strategy profiles of one engine plus a diversity check | Plan Phase 4; product brief section 5. |
| User inputs: interests, pace, budget, transport preferences, hotel or city changes | Destination or area, duration, optional start date (currency and meal budget removed by ADR 017) | Product brief; the others are beyond the stated goals (CLAUDE.md rule 3). Listed in section 4. |
| Item states locked, preferred, flexible | `locked` boolean plus a stability cost for changes | Data model and plan Phase 7. |
| Offline queued edits, conflict resolution, sync | On-device read cache with honest staleness labels | Plan Phase 5. Queued sync is listed in section 4. |
| Public transport with GTFS, OpenTripPlanner or MOTIS self-hosted | Reassess in Prompt 13: Transitous or nothing; no self-hosting | No server (D14); ADR 005. |
| Authentication and multi-device sync (Prompt 12) | Parked | D5: no accounts. Needs an ADR and a fresh hosting review. |
| Android "private beta", Google Play assumptions | Private APK, no store | ADR 008. |
| "Validate the first release against Japan" | Austria, Czechia and Hungary first; Italy next; Japan last | Spike S2: Japan's names are mostly non-Latin and rail is its main inter-city transport (D4). |
| Test journeys for missing opening hours and missing transit coverage | Replaced by journeys for FOSSGIS unavailable or throttled, the cold start, and a paused Supabase project | The real failure modes (ADR 004, 005). |

### Mapping of the original prompts to the new ones

| Original | New |
|---|---|
| 1 Product and technical feasibility | Done (Phase 0 documents); Prompt 1 finishes Phase 0 |
| 2 Project foundation | 2 (Phase 1) |
| 3 Data model | 3 (Phase 2, first half) |
| 4 Provider abstraction | 3 (Phase 2, import and search) and 4 (Phase 3, routing adapter) |
| 5 Itinerary generation | 5 (Phase 4) |
| 9 Mobile experience | 6 (Phase 5) and parts of 8, 9 |
| 7 Restaurants | 7 (Phase 6) and 9 (Phase 8) |
| 6 Add a city | 8 (Phase 7) |
| 10 Offline, privacy, security | 10 (Phase 9) |
| 13 Quality gate and beta | 10 (Phase 9) |
| 8 Public transport | 12 (Phase 10) |
| 11 Photo design | 14 (Phase 12) |
| 12 Authentication and sync | Parked |
| New | 11 Past trips archive (ADR 006), 13 iOS (Phase 11) |

## 4. Asked for in the original, now needing the owner's approval and an ADR

These are not in any prompt below. Ask for them explicitly if wanted.

- Interests, travel pace, transport preferences and a free-form "approximate budget" as trip
  inputs.
- Currencies, meal budgets, restaurant prices (expected or actual), price bands and currency
  conversion (removed by ADR 017 on 2026-11-13).
- A choice of five itinerary themes (culture, food, nature, relaxed, highlights).
- Hotel or accommodation modelling, nights per city and "maximum hotel changes" (hotel
  availability is out of scope; the plan uses base cities and day allocation).
- Reservation dates and times, reservation requirements and "insert a restaurant with a fixed
  reservation time".
- Offline queued edits, sync conflict detection, and data export.
- Accounts, sign-in, password recovery and multi-device sync.
- Cached public-transport instructions.
- Weather (D6) and "more coverage" regions (Phase 13) are post-MVP and have no prompt yet.

---

# Prompt 1 — Finish Phase 0: spikes S1 and S5

**Status:** done (S1 and S5 findings in `docs/spikes/`; D7 decided). Kept for the record.  
**Recommended model:** Claude Opus  
**Effort:** High  
**App-plan phase:** 0 (S2, S3 and S4 are done or removed)

```text
Read CLAUDE.md and every document in docs/, including docs/decisions/001 to 009 and
docs/spikes/.

Task: finish the two remaining Phase 0 spikes. Spike code is throwaway, lives in spikes/ and is
not merged into the product.

S1 — Map. Prove that MapLibre React Native renders an OpenFreeMap style in an Expo development
build on Android, and that the Android APK can be built in GitHub Actions without Android Studio
on any local machine (ADR 008). Produce the workflow, the APK as a downloadable artifact, and
step-by-step instructions for the owner to install it on a phone. Record how the style URL is
read from backend configuration instead of a constant in the app. Record what attribution is
shown. If the build cannot run in GitHub Actions, say exactly why and propose the alternative
(Expo's cloud build, whose free-plan limits you must read from its official page first).

S5 — Sequencing. Compare the simple heuristic and OR-Tools on three fixture trips: a 3-day
single-city trip, a 7-day regional trip and a 14-day multi-city trip, using the imported spike
data or hand-made fixtures. Measure plan quality, latency and repeatability across repeated runs
and machines (fixed seeds, solution-count limits, no wall-clock dependence). Time windows are
meal windows and day length only; there are no opening hours (ADR 003). Recommend one default
sequencer or recommend the heuristic only.

Write a findings note for each spike in docs/spikes/ and update docs/app-plan.md (D7) and
docs/architecture.md section 5.5 with the outcome.

Scope guards:
- Spikes only. Do not scaffold the product.
- No production code.
- Read official pages for any provider or tool limit you rely on; mark each figure with its
  source and the date read.
- No LLM dependency.
```

---

# Prompt 2 — Project foundation (Phase 1)

**Status:** done and accepted (ADR 010). Kept for the record.  
**Recommended model:** Claude Sonnet  
**Effort:** High  
**App-plan phase:** 1

```text
Read CLAUDE.md, README.md, docs/product-brief.md, docs/architecture.md, docs/data-model.md,
docs/app-plan.md, docs/kpis.md and docs/decisions/001 to 009.

Task: create the project foundation for Detour. The owner has given the go-ahead for Phase 1.

Create a monorepo with:
- apps/mobile: React Native with Expo and TypeScript, using development builds and the MapLibre
  config plugin (never Expo Go; do not hand-edit native projects);
- services/api: Python with FastAPI;
- packages/shared: generated TypeScript types from the OpenAPI contract;
- infrastructure: Docker Compose with PostgreSQL and PostGIS for any machine that can run it;
- docs: keep and update the existing documents.

Implement:
1. A mobile app with placeholder screens: Trips, Create Trip, Itinerary, Map, Saved Places,
   Settings. The Map screen shows the OpenFreeMap style URL read from the backend config.
2. A FastAPI service: versioned API, health endpoint, anonymous installation registration and
   token check (app-plan D5), environment-based configuration, structured logging with
   redaction, OpenAPI.
3. Database migrations for the `geo` and `app` schemas as empty, separate schemas.
4. A generated, typed API client for the app.
5. Linting, formatting, type checks and tests, all running in GitHub Actions. Nothing may
   require a local Windows toolchain.
6. A workflow that builds an Android release-variant APK as an artifact (ADR 008 addendum).
7. Deployment configuration for a Render free web service and a Supabase Free database
   (ADR 005), plus docs/deployment.md with step-by-step instructions. The owner creates the
   Supabase and Render accounts; guide them one step at a time. Deploy the health endpoint and
   confirm the phone build can call it, accepting the cold start.
8. .env.example without secrets; secrets only in the hosting providers' settings.
9. docs/development.md: CI-first setup; local Docker Compose as an option for a capable machine.

Tests: health endpoint, configuration loading, installation token check, one mobile component,
database connectivity in CI.

Update README.md, CLAUDE.md (Commands section), docs/architecture.md and docs/app-plan.md.
Before implementing, inspect the repository and preserve existing work. After implementing, run
the formatters, linters and tests in CI and report anything that could not run, and why.

Scope guards:
- Foundation only.
- No external API calls in the backend, no itinerary generation, no accounts, no photos, no
  public transport, no weather.
- No LLM dependency.
- Do not add features beyond this list.
```

---

# Prompt 3 — Data model and geo data foundation (Phase 2)

**Status:** done and accepted (ADR 011, ADR 012). Kept for the record.  
**Recommended model:** Claude Sonnet  
**Effort:** High  
**App-plan phase:** 2

```text
Read CLAUDE.md, docs/architecture.md, docs/api-evaluation.md, docs/data-model.md,
docs/app-plan.md, docs/kpis.md, docs/spikes/s2-data-findings.md and ADRs 002, 003, 005, 006, 009.

Task: implement the persistence layer and the region data import.

1. Implement the `geo` and `app` schemas exactly as docs/data-model.md describes, with
   migrations: regions, import runs, countries, cities, places, place sources and licences,
   restaurant profiles, Wikidata signals, travel times; installation, trip, itinerary, day, item,
   transfer, user place, and the past-trip archive (`app.trip_visit`, ADR 006). No prices,
   currencies or FX rates (ADR 017). There is no opening-hours table. Installation tokens replace user
   accounts. No photo table yet.
2. A region import command, run as a manually started GitHub Actions workflow (as in spike S2): it
   downloads a Geofabrik extract with an identifying User-Agent, filters it, imports it into a
   temporary PostGIS, applies the attraction selection rule (ADR 003, including the stricter
   memorial test and a reviewed decision on `historic=yes`, `building`, `railway`, `stone` and
   `tomb`), and loads the `geo` tables into Supabase through the session-mode pooler
   (ADR 005). The import must be repeatable with identical results.
3. The data quality report and the region readiness gates of ADR 009, computed automatically,
   with counts of excluded objects per class.
4. A gazetteer import (GeoNames) and a destination search endpoint over cities and areas, and a
   local place search endpoint. Search outside the local data uses Photon through the backend
   only, cached, per docs/api-evaluation.md; read its current terms first.
5. Seed data for one small illustrative trip, clearly marked as seed data.
6. Pydantic models, repository layer, validation, CRUD endpoints for trips, user places and
   itinerary items.

Tests: import twice gives identical results; counts match the report; search returns expected
results for a fixture list; spatial queries use indexes; validation rules.

Update docs/data-model.md with entity definitions, lifecycle and deletion rules, provider-data
ownership and licence handling (OSM as ODbL source records).

Scope guards:
- Data and search only. No itinerary optimization, no routing, no map screens.
- Never invent data. Unknown values stay unknown.
- Do not call Nominatim, Overpass or tile.openstreetmap.org from code or tests.
- No weather, no transit, no photos, no accounts, no budgets or prices, no LLM dependency.
```

---

# Prompt 4 — Travel-time service (Phase 3)

**Status:** built, awaiting acceptance (ADR 013). Kept for the record.  
**Recommended model:** Claude Sonnet  
**Effort:** High  
**App-plan phase:** 3

```text
Read CLAUDE.md, docs/architecture.md, docs/data-model.md, docs/app-plan.md,
docs/spikes/fossgis-matrix-check.md, docs/spikes/s3-routing-findings.md and ADRs 004 and 005.

Task: implement the travel-time service behind a routing adapter.

Requirements from ADR 004:
- The adapter calls the FOSSGIS Valhalla server for walking and driving. It sends an identifying
  User-Agent and an X-Client-Id header naming the project.
- Matrices are chunked to at most 100 cells and 150 km. Legs between distant cities use the
  single-route request, one per leg. Check whether a request option can reduce the response size
  and record it.
- Rate: 1 request per second sustained, bursts of at most 10, a circuit breaker after any 429 or
  error, a timeout, and a daily budget counter.
- Cache every cell in `geo.travel_time` with the provider, the response date and the request
  shape. Plan generation reads the cache; only misses call the adapter.
- Fallback: straight-line distance times a mode factor, stored and shown as `estimated`. A null
  matrix cell (some cells were unreachable in the benchmark) falls back the same way.
- Route geometry is fetched only for the selected itinerary and is never archived (ADR 006).
- Use one fixed request shape. Investigate why the same pair returned 523 s in two requests and
  653 s in a third, and report whether the difference persists before the cache is trusted.

Tests: contract tests against recorded responses (never the live server, never in CI); matrix
chunking; rate limiter and circuit breaker; cache hit on repeat; fallback when the adapter is
disabled; null-cell handling.

Scope guards:
- Travel time only. No itinerary generation, no public transport, no weather.
- No second routing provider, and no hidden fallback to a paid service.
- No LLM dependency.
```

---

# Prompt 5 — Planner v1: attractions and days (Phase 4)

**Status:** built, awaiting acceptance (ADR 014; amended by ADR 016). Kept for the record.  
**Recommended model:** Claude Opus  
**Effort:** High  
**App-plan phase:** 4

```text
Read CLAUDE.md, docs/product-brief.md, docs/architecture.md, docs/data-model.md, docs/app-plan.md,
docs/kpis.md and ADRs 003, 004, 006.

Task: implement version 1 of the deterministic planning engine for attractions and days.

Inputs: a city destination (area destinations come in Prompt 7), a duration in days and an
optional start date. Nothing else is a user input in the MVP (see section 4 of
docs/build-prompts.md); there is no currency or budget (ADR 017).

Produce two meaningfully different itineraries from two strategy profiles of one engine, with a
diversity check (Jaccard overlap of visits at most 0.6, or a different allocation of days). If
the destination cannot support two distinct plans, say so and return one.

Pipeline: candidate selection and scoring (notability signals from Wikidata, category,
distance); day construction with the baseline sequencer behind the Sequencer interface (use
OR-Tools only if spike S5 justified it); visit durations from a category rule table the user can
change; transfers from the travel-time service with their `routed` or `estimated` label; an
independent validator that every generated itinerary must pass; reason codes rendered through
fixed templates.

The engine is deterministic: stable ordering, ties broken by identifier, fixed seeds, and the
engine, configuration and data versions stored on every itinerary.

Tests: golden fixtures that reproduce identical output; validator tests; a 3-day city trip; a
7-day trip; a 14-day trip; a destination with incomplete place data; impossible constraints
(explain exactly which); latency within the budget in docs/kpis.md.

Scope guards:
- Attractions and days only. No restaurants, no recalculation after edits, no areas, no public
  transport, no weather.
- No opening hours, no closed-place logic.
- Never manufacture attractions, prices, ratings or travel times.
- No LLM dependency, and no synthetic descriptions.
```

---

# Prompt 6 — Mobile shell (Phase 5)

**Status:** built, awaiting acceptance (ADR 015); the owner reported on 2026-11-13 that the app
works on the phone. Kept for the record.  
**Recommended model:** Claude Sonnet  
**Effort:** High  
**App-plan phase:** 5

```text
Read CLAUDE.md, docs/product-brief.md, docs/architecture.md, docs/data-model.md, docs/app-plan.md
and ADRs 001, 004, 006, 008.

Task: build the mobile screens for creating a trip, comparing two proposals, and viewing days
and the map, on Android, as release-variant APKs built in GitHub Actions (ADR 008). The design should feel calm and minimal, like
a travel-planning product, not a booking marketplace. Do not copy another product's design.

Implement: trip list; create-trip form (destination search, days, optional start date; no currency
or budget, ADR 017); proposals comparison (side by side or swipeable, with a short
structured summary of how they differ); day list with items, durations, transfers and their
routed or estimated labels; map with markers for the day and transfer lines, loading markers
progressively; itinerary selection; attribution for OpenStreetMap and the tile provider visible
on the map; an on-device read cache of trips and itineraries; empty, loading, offline-read and
error states. Show a clear "waking the server" state during the Render cold start (ADR 005).

Accessibility: touch targets, screen-reader labels, contrast, text scaling, nothing conveyed by
colour alone. Performance: virtualised lists; no unnecessary requests.

Tests: component tests for the critical flows; one end-to-end flow on an Android emulator against
a seeded backend, in a GitHub Actions workflow the owner starts by hand (not on every push).

Scope guards:
- Screens and integration only; do not change planning calculations except to fix an
  integration defect.
- No accounts, no photos, no weather, no sharing or social features, no booking.
- No offline editing or sync. No budgets, currencies or prices.
- No LLM dependency.
```

---

# Prompt 7 — Restaurants in itineraries and area destinations (Phase 6)

**Status:** built on 2026-11-13, awaiting acceptance (ADR 016). Kept for the record.  
**Recommended model:** Claude Opus  
**Effort:** High  
**App-plan phase:** 6

```text
Read CLAUDE.md, docs/architecture.md, docs/data-model.md, docs/app-plan.md and ADRs 003, 004, 017.

Task: add meals to itineraries, and area destinations (a region instead of a single city).

Meals: fixed meal windows by meal type (breakfast, lunch, dinner, snack) and venue type;
restaurant selection by proximity, cuisine variety and venue type, from the imported data only.
Cuisine, venue type and meal type come from the open data; unknown cuisine is shown as "Cuisine
not specified". Restaurants carry no price, rating or opening hours.

Area destinations: base cities and allocation of days to them, using inter-city legs from the
travel-time service (route requests for legs beyond 150 km). Japan is limited to single-city
trips for now (app-plan D4).

Reason codes for each placement. The validator checks meals fall inside meal windows and day
length is respected. Update the golden tests.

Tests: meals inside meal windows; area fixtures give a sensible day allocation; golden tests
updated.

Scope guards:
- Meals and areas only. No manual restaurant adding, no recalculation after edits.
- No prices, budgets or currencies (ADR 017).
- No opening hours, reservations, ratings or reviews.
- No hotels or accommodation modelling.
- No LLM dependency.
```

---

# Prompt 8 — Add a city or place, with recalculation (Phase 7)

**Status:** built on 2026-11-13 (ADR 018, proposed); awaits the owner's acceptance.  
**Recommended model:** Claude Opus  
**Effort:** High  
**App-plan phase:** 7

```text
Read CLAUDE.md, docs/architecture.md, docs/data-model.md, docs/app-plan.md, ADRs 014, 016 and 017
and the planning engine.

Task: let the user add a city or place that was not in the proposal, and recalculate around it.

1. The user searches for a place or drops a pin; it becomes a mandatory visit.
2. The engine recalculates with minimal disruption: a stability cost for moving existing items,
   `locked` items never moved or removed, the day length and the meal windows respected (meals
   move with the day and stay at imported places to eat, ADR 016). If the addition is far away,
   days are re-allocated to a new base city with the inter-city legs of ADR 016.
3. The app previews the change as a diff (what moves, what is dropped, added travel time, any
   estimated times). The user accepts or discards. Nothing changes until acceptance.
4. Itinerary versioning: accepting creates a new version; the previous one stays; adding then
   removing the place restores the previous plan.
5. If no feasible plan exists, say exactly which constraints conflict. Never silently delete a
   city or an item.

Implement the backend service, preview and apply endpoints, undo through versioning, persisted
change sets, and the app screens for search, pin, preview, accept and discard.

Tests: locked items never move; the diff matches the applied result; add then remove restores the
plan; a distant addition re-allocates days; infeasible additions are explained.

Scope guards:
- Adding and removing places only. No restaurant adding in this prompt.
- No minimum or preferred nights, "trip may grow" options or per-city protections (section 4 of
  docs/build-prompts.md).
- No budgets, currencies or prices (ADR 017).
- No LLM dependency, no booking.
```

---

# Prompt 9 — Add a restaurant (Phase 8)

**Status:** built on 2026-11-13 (ADR 019, proposed); awaits the owner's acceptance. Prices, budgets
and currency conversion were removed from this prompt by ADR 017 (2026-11-13).  
**Recommended model:** Claude Sonnet  
**Effort:** High  
**App-plan phase:** 8

```text
Read CLAUDE.md, docs/product-brief.md, docs/architecture.md, docs/api-evaluation.md,
docs/data-model.md, docs/app-plan.md and ADRs 002, 003, 016, 017.

Task: let the user add a restaurant and place it in the best slot.

Adding: search the local data first, then Photon through the backend (read its current terms),
then manual entry with a name and a map pin (the user may also type coordinates). The user may
give cuisines and the meals the place serves; otherwise they are unknown and shown as such
("Cuisine not specified").

Best slot: score every day and meal slot of the itinerary by location, neighbouring activities,
meal type and venue type, meal window (ADR 016) and travel impact; return up to three suggestions
with reasons, the estimated detour and which items move. The meal must stay inside its window and
the day inside its hours (the validator checks both). No opening hours and no reservations.

Tests: scoring fixtures; suggestions respect meal windows and day length; manual entry without
cuisine stays "Cuisine not specified"; the provider budget counter stops calls at the limit.

Scope guards:
- Restaurants only. No prices, budgets, price bands or currencies (ADR 017).
- No reviews or ratings, no reservations or booking.
- No weather, no accounts.
- No LLM dependency.
```

---

# Prompt 10 — MVP hardening and private Android APK (Phase 9)

**Status:** after Prompt 9.  
**Recommended model:** Claude Opus  
**Effort:** High  
**App-plan phase:** 9

```text
Read CLAUDE.md, README.md and every document in docs/, including the ADRs and spike notes.

Task: stabilise Detour for the owner's own use as a sideloaded Android APK. No new product
features.

1. Audit: requirements implemented, incomplete items, architecture consistency, provider-term
   compliance and attribution, quotas, error handling, data correctness, itinerary feasibility
   (meal windows and day length included), accessibility, performance, privacy, security, test
   coverage. Confirm that no budget, currency or price remains anywhere (ADR 017).
2. Resilience (only what the plan has): an on-device read cache with honest "cached, last
   updated" labels, retry with backoff, network-status handling, a clear state for each external
   dependency being slow or down (Render cold start, Supabase paused or limited, FOSSGIS
   throttled, Photon unavailable).
3. Privacy and security: docs/privacy.md and docs/security.md with a threat model covering keys
   in the app binary (there must be none), unauthorised use of the public API without accounts
   (installation token plus rate limits), location history, provider terms and cached data, and
   log leakage. Trip and local data deletion. No export unless approved.
4. Backups: Supabase Free has none (ADR 005). Implement or document the scheduled export of the
   `app` schema that the owner chose, or record that the owner accepted the risk.
5. Test plan and execution for these journeys: a 3-day city trip; a 14-day area trip with several
   base cities; an area in Japan (refused, single-city only); comparing two proposals; adding a
   place and previewing the impact; an impossible addition; adding a provider restaurant; a
   custom restaurant by map pin; using the app with no network (read cache); restarting and
   recovering a saved trip; FOSSGIS unavailable or throttled (estimated times labelled); the
   Render cold start; a paused database; undoing an adjustment. The Android end-to-end workflow
   is started by hand; run it once and record the result.
6. docs/android-release.md: exact steps to build the APK in GitHub Actions and install it on a
   phone (step by step). docs/known-limitations.md. docs/ios-readiness.md (the Mac route,
   ADR 008).

Fix defects within existing scope. Report: tests run, passed, failed, unresolved blockers,
manual checks required, and whether the MVP is ready for the owner's own use. Do not claim
readiness while critical journeys are untested.

Scope guards:
- Stabilisation only. No new features, no paid services, no LLM.
- No app-store submission.
```

---

# After the MVP

# Prompt 11 — Past trips archive (ADR 006)

**Status:** built on 2026-11-13 and awaiting the owner's acceptance (ADR 006, amendment): the
manual and automatic archive, the size report and the app's past-trip screen.  
**Recommended model:** Claude Sonnet  
**Effort:** Medium  
**App-plan phase:** release timing to be set by the owner

```text
Read CLAUDE.md, docs/data-model.md and ADR 006.

Task: implement the past-trips archive. A trip becomes past when the user marks it, or
automatically after its last day. When it does, keep the title, destination, dates and duration,
and one `app.trip_visit` row per city and attraction of the selected itinerary with a snapshot of
name, point, kind and day; delete transfers, route geometry, unselected and superseded
itineraries, and versions. The app shows a past trip as a map with markers for visited cities and
attractions and a list grouped by city, with no routes or travel times. The user can clear the
visits that were skipped (the `confirmed` flag). Meals and restaurants are not archived. For an
area trip, the archive lists each base city once.

Tests: archiving deletes exactly the listed data; a past trip renders without any routing data;
re-importing `geo` data does not break an archived trip; the size of an archived trip is
reported.

Scope guards: archive and display only; no re-planning of past trips; no photos; no LLM.
```

# Prompt 12 — Public transport (Phase 10)

**Status:** after the MVP.  
**Recommended model:** Claude Opus  
**Effort:** High  
**App-plan phase:** 10

```text
Read CLAUDE.md, docs/architecture.md, docs/api-evaluation.md, docs/data-model.md, the routing
implementation, and ADRs 005, 007, 008, 016.

Task: first reassess the public-transport options with the current official documentation.
Self-hosting OpenTripPlanner or MOTIS is not possible (no server). The candidate is the hosted
Transitous service, which requires published source under an open-source licence (the repository
must be public under Apache-2.0, ADR 007) and has its own usage rules; read them first. If
Transitous or an equivalent does not fit, record that public transport stays out and stop.

If it fits, write an ADR, then implement a transit adapter behind the same rules as the routing
adapter (timeout, cache, budget, fallback, identifying headers, tests on recorded responses).
Legs show the mode (walk, rail, bus and so on), departure and arrival times, operator, and
whether the data is scheduled or real-time. Where no data exists, show nothing invented; fall
back to labelled driving or walking times. Document the supported regions, the unsupported
cases and feed attribution. Japan's rail coverage is the main reason for this phase (app-plan D4):
if transit fits, propose (in the ADR) lifting the single-city limit for areas in Japan and use
transit for the legs between base cities there.

Scope guards: transit only; no ticket purchase, fares or prices; no worldwide coverage claim; no
paid provider; no LLM.
```

# Prompt 13 — iOS on the owner's Mac (Phase 11)

**Status:** after the MVP.  
**Recommended model:** Claude Sonnet  
**Effort:** High  
**App-plan phase:** 11

```text
Read CLAUDE.md, docs/architecture.md, docs/app-plan.md, docs/ios-readiness.md and ADR 008.

Task: make the app build and run on the owner's iPhone, without the App Store. First read, from
the official Expo and Apple pages, what a free Apple ID allows (how long a build stays valid, how
many apps) and what the paid Apple Developer Program ($99 per year) adds, and report it so the
owner can choose. Then provide the build configuration, permissions, and step-by-step
instructions for compiling on the Mac with Xcode and installing over a cable. Test the platform
differences (permissions, safe areas, map rendering).

Scope guards: no App Store or TestFlight submission; no iOS-only native dependency without an
ADR; no LLM.
```

# Prompt 14 — Photos: design first (Phase 12)

**Status:** after the MVP.  
**Recommended model:** Claude Opus  
**Effort:** Medium  
**App-plan phase:** 12

```text
Read CLAUDE.md, docs/product-brief.md, docs/architecture.md, docs/data-model.md and the
photo-related notes in docs/api-evaluation.md (decision D9: on-device first).

Task: design the travel-photo capability without implementing it. Photos are linked to a trip,
a day, a city or an itinerary item; shown chronologically and on a map when location metadata
exists; originals kept; EXIF handled carefully; deletion removes derived files; no broad media
access (use the picker).

Compare storage options using their current official pages: device-only (the default),
Supabase Storage (Free plan storage and egress limits), Cloudflare R2 and Backblaze B2. Include
free allowance, bandwidth, mobile support, signed URLs, backup, privacy, deletion and what
happens if the free allowance is exceeded (the owner wants no paid services). Include Firebase Storage only if it is clearly better and its
free terms are verified.

Create docs/photo-architecture.md and update docs/data-model.md and docs/app-plan.md. Do not
implement uploads in this task.

Scope guards: design only; no facial recognition or image classification; no public gallery; no
LLM or computer-vision dependency.
```

---

# Parked

- **Authentication and multi-device synchronisation** (original Prompt 12). The app plan has
  anonymous installation tokens and no accounts (D5). If wanted later: an ADR, a fresh read of
  Supabase's free-plan terms (including its "internal business purposes" wording) and a hosting
  review first.
- **Weather** (D6) and **more coverage** (Phase 13): no prompt until approved.
