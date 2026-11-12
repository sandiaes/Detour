# App plan

Status: **proposed**. Nothing is implemented. Each phase is small enough to review on its own
and ends with tests that prove it. A phase starts only when its dependencies are complete.

## 1. Decisions required first

These need the owner's approval. Phase 1 cannot start responsibly without D1, D2 and D5.

| ID | Decision | Recommendation | Blocks |
|---|---|---|---|
| D1 | Licence and commercial posture: is the project open source, and is it non-commercial for now? | State it explicitly. It decides whether Transitous and Open-Meteo's free API are permitted. | Phase 10, weather |
| D2 | MVP coverage: imported pilot regions, or any destination worldwide? | One to three pilot regions chosen by the owner. | Phase 0 spikes, Phase 2 |
| D3 | Backend hosting beyond a local machine | Decide after the Phase 0 sizing spike; hosting providers have not been evaluated. | Phase 9 |
| D4 | Public transport outside the MVP | Yes: deliver it as Phase 10 through self-hosted MOTIS, or Transitous if D1 allows. | MVP scope |
| D5 | Identity: anonymous installation token, no accounts | Yes for the MVP. | Phase 1 |
| D6 | Weather | Exclude: it is not a stated product goal. Revisit after the MVP. | Scope |
| D7 | OR-Tools | Adopt only if the Phase 0 spike shows better plans within the latency budget; keep the heuristic as fallback. | Phase 6 |
| D8 | Map tiles: OpenFreeMap public instance now, self-hosted PMTiles as rehearsed fallback | Yes. | Phase 5 |
| D9 | Photo storage: on-device first, cloud backup decided when the photo phase starts | Yes. | Phase 12 |
| D10 | Restaurant prices: user-entered only; no price inferred from venue type; default band limits set in Phase 8 | Yes. | Phase 8 |

## 2. Phase overview

```
0 Spikes ─► 1 Scaffold ─► 2 Geo data ─► 3 Travel time ─► 4 Planner v1 ─┬─► 6 Hours + restaurants ─► 7 Add place ─► 8 Add restaurant + prices ─► 9 MVP release
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
| S1 Map | Does MapLibre React Native render OpenFreeMap in an Expo development build on Android? | Running build; notes on configuration |
| S2 Data | Is OSM data in the candidate pilot regions good enough? | Data quality report: attractions, restaurants, share with opening hours, cuisine, Wikidata link |
| S3 Routing | What does a regional Valhalla instance need? | Tile build time, memory, matrix latency for 50 points |
| S4 Hours | Which opening-hours parser handles real values from S2? | Parse success rate by library on a sample |
| S5 Sequencing | Heuristic versus OR-Tools on three fixture trips | Plan quality, latency, repeatability across runs |

- **Dependencies:** D2 (which regions to test).
- **Exit:** a short findings note per spike; D2, D3 and D7 can be decided; verification gaps in
  `docs/api-evaluation.md` section 15 marked for this phase are closed.
- **Risks:** a pilot region with poor data; mitigation is to pick another region.

### Phase 1 — Project scaffolding and continuous integration

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

**Goal:** a pilot region's data is in the database and destinations can be searched.

- **Deliverables:** `geo` schema; region import command (places, restaurants, raw opening
  hours, Wikidata signals); gazetteer import; country and currency seed; import-run record and
  data quality report; destination search endpoint; place search endpoint (local only).
- **Tests:** import runs twice with identical results; counts match the report; search returns
  expected results for a fixture list; spatial queries use indexes.
- **Dependencies:** Phase 1.
- **Risks:** tag normalisation takes longer than expected; mitigation is a narrow first
  category list.

### Phase 3 — Travel-time service

**Goal:** routed walking and driving times, with a safe fallback.

- **Deliverables:** Valhalla container and tile build for the pilot region; travel-time
  interface with cache; estimated fallback with confidence label; route geometry.
- **Tests:** matrix symmetry and sanity checks; fallback used when the container is stopped;
  cache hit on repeat; latency measured.
- **Dependencies:** Phase 2 (same extract), S3.
- **Risks:** memory needs exceed the target host; mitigation is a smaller region or OSRM.

### Phase 4 — Planner v1: attractions and days

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

### Phase 6 — Opening hours and restaurants in itineraries

**Goal:** plans respect opening hours and include meals.

- **Deliverables:** opening-hours parsing and the three-state service; time windows in
  sequencing (OR-Tools here if D7 says so); area destinations with base cities and day
  allocation; meal slots with restaurant selection by proximity, hours, cuisine variety and
  venue type; restaurant attributes in the API and app.
- **Tests:** no visit scheduled while known-closed; unknown hours flagged; meals inside meal
  windows; area fixtures produce sensible day allocation; golden tests updated.
- **Dependencies:** Phases 4 and 5, S4, S5.
- **Risks:** sparse opening hours make time windows weak; mitigation is the unknown state and
  user override.

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
- **Tests:** closed slots never proposed; scoring fixtures; per-person derivation; band and
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
| 11 iOS | Build configuration, permissions, platform testing, App Store submission | Apple Developer Program ($99 per year) |
| 12 Photos | Pick photos, link to trip, day, city or item; on-device storage; later optional backup | D9; Play photo-permission policy respected |
| 13 More coverage | On-demand region import; supplementary places from Overture and Foursquare OS Places | Hosting capacity; matching rules |
| 14 Weather | Informational forecast overlay | D6 approved; D1 decides the provider |

GTFS-Realtime is considered only after Phase 10, and only for same-day use.

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

**Phase 0, spike S2 together with decision D2:** choose the candidate pilot regions and produce
the data quality report for each from an OSM extract. Its result decides whether the open-data
approach is good enough where the app will first be used, and it feeds every later phase.
