# App plan

Status: **Phase 0, 1 and 2 are done; Phases 3 and 4 are built and await the owner's acceptance**; Phase 5 onward is proposed. Each phase is small enough to review on its own
and ends with tests that prove it. A phase starts only when its dependencies are complete.

## 1. Decisions

Recorded on 2026-11-12 from the owner's answers.

| ID | Decision | Outcome | Status |
|---|---|---|---|
| D1 | Licence and commercial posture | **Open source and non-commercial.** Free non-commercial services (Open-Meteo, Transitous) become permissible, subject to their other conditions. | Decided |
| D2 | MVP coverage | **Pilot regions: Japan, Italy, and Central Europe (Austria, Czechia and Hungary at least).** | Decided |
| D3 | Backend hosting: where the API server, the database and the routing engine run when not on a local machine | Open. S2 measured about 145 MB of imported data for five countries (before ADR 003), so Supabase Free could hold the `geo` data. ADR 005 (accepted): Supabase Free for the database, a Render free web service for the API, a GitHub Actions import job. | **Decided** |
| D4 | Public transport after the MVP (Phase 10) | Approved. See the note on Japan below. | Approved |
| D5 | Anonymous installation token, no accounts | Approved. | Approved |
| D6 | Weather excluded from the MVP | Approved. | Approved |
| D7 | OR-Tools only if the Phase 0 spike justifies it | **Not justified: the heuristic only.** Spike S5 found OR-Tools 6–8% better on two fixtures but 7–300 times slower, and unable to find any plan for the 14-day fixture with its usual strategies. See `docs/spikes/s5-sequencing-findings.md`. | Decided by the approved rule; the owner may override |
| D8 | OpenFreeMap tiles now, self-hosted PMTiles as rehearsed fallback | Approved. | Approved |
| D9 | Photos on-device first; cloud backup decided in the photo phase | Approved. | Approved |
| D10 | Restaurant prices from users only; default band limits set in Phase 8 | Approved. | Approved |
| D11 | Which open-source licence, and when the repository becomes public | **Apache-2.0** (ADR 007). The repository stays private until the owner decides to publish it. | Decided |
| D12 | Opening hours | **Out of scope.** No closed-place warning. See ADR 003. | Decided |
| D13 | Attraction selection | Wayside shrines and crosses, boundary stones, bomb craters and most memorials are not imported. See ADR 003. | Decided |
| D15 | Past trips archive | Past trips are kept as a map and list of visited cities and attractions, without routing. See ADR 006. Release timing open. | Decided |
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
Japan. To be settled when Phase 4 results are reviewed.

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
0 Spikes ─► 1 Scaffold ─► 2 Geo data ─► 3 Travel time ─► 4 Planner v1 ─┬─► 6 Restaurants ─► 7 Add place ─► 8 Add restaurant + prices ─► 9 MVP release
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
table (Phase 4), a display rule for non-Latin names (gate 5, Japan), and the automatic archive of
past trips.

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

**Goal:** create a trip, compare two proposals, view days and the map on Android.

- **Deliverables:** trip creation; proposals comparison; day list; map with visits and transfer
  lines; itinerary selection; attribution display; on-device read cache; error and empty
  states.
- **Tests:** component tests; one end-to-end flow on an Android emulator against a seeded
  backend.
- **Dependencies:** Phase 1 contract; Phase 4 for live data; S1.
- **Risks:** map performance on low-end devices; mitigation is marker clustering and simplified
  geometry.

### Phase 6 — Restaurants in itineraries

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

**Goal:** the plan absorbs an addition with minimal disruption.

- **Deliverables:** add-place flow (search, pin); user places; mandatory-visit handling;
  stability cost; locking; preview diff with accept and discard; itinerary versioning.
- **Tests:** locked items never move; diff matches the applied result; adding then removing
  restores the previous plan; adding a distant city re-allocates days.
- **Dependencies:** Phase 6.
- **Risks:** recalculation reshuffles too much; mitigation is tuning the stability cost with
  fixtures.

### Phase 8 — Add a restaurant, prices and budget

**Goal:** a manually added restaurant lands in the best slot, and prices are tracked honestly.

- **Deliverables:** restaurant search (local, then Photon through the backend, then manual
  entry); slot scoring and alternatives with reasons; price records (expected and actual, per
  person or total, any currency); trip meal budget and price bands; daily FX job and stored
  rates; conversions labelled approximate.
- **Tests:** scoring fixtures; per-person derivation; band and
  budget-fit calculations; FX fallback order; provider budget counter stops calls at the limit.
- **Dependencies:** Phase 7, D10.
- **Risks:** external search unavailable; mitigation is manual entry always being possible.

### Phase 9 — MVP hardening and release

**Goal:** a build fit for real trips.

- **Deliverables:** failure-mode handling; tile-provider switch rehearsed with a PMTiles
  extract; attribution and licence screen; privacy note; performance pass; backup of the `app`
  schema; deployment to the chosen host; release build; Play Console closed test.
- **Tests:** full regression; KPI measurement run; chaos checks (routing down, search down,
  tiles down).
- **Dependencies:** Phase 8, D3.
- **Risks:** a new personal Play account needs a closed test with at least 12 testers for 14
  days before production access; plan the calendar for it. Play registration costs $25 once.

## 4. After the MVP

| Phase | Content | Preconditions |
|---|---|---|
| 10 Public transport | Transit legs from schedule data through self-hosted MOTIS or Transitous; mode choice between walk, drive and transit; feed attribution | D1, D4; feed licences reviewed for each pilot region |
| 11 iOS | Build configuration, permissions, platform testing, build on the owner's Mac and install by cable (no App Store; ADR 008) | The owner's Mac; Apple Developer Program ($99 per year) only if the free route proves unusable |
| 12 Photos | Pick photos, link to trip, day, city or item; on-device storage; later optional backup | D9; Play photo-permission policy respected |
| 13 More coverage | On-demand region import; supplementary places from Overture and Foursquare OS Places | Hosting capacity; matching rules |
| 14 Weather | Informational forecast overlay | D6 approved; D1 decides the provider |

GTFS-Realtime is considered only after Phase 10, and only for same-day use.

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

## 5. MVP exclusions

- Public transport and real-time transit data
- iOS build
- Photos
- Weather
- Destinations outside imported pilot regions; on-demand region import
- Accounts, sign-in, sharing, multi-device sync
- Offline map downloads and offline planning
- Restaurant ratings, reviews and provider price levels
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

**Accept Phases 3 and 4, then Phase 5 (mobile shell), when the owner asks for it (CLAUDE.md).**
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
