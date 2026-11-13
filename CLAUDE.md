# CLAUDE.md

Guidance for AI-assisted work in this repository.

## Project

Detour is a cross-platform travel-itinerary planner: Android first, iPhone later. The user
gives a destination or area and a trip length; the app proposes at least two meaningfully
different itineraries and recalculates when the user adds places or restaurants.

## Current state

**Phases 1 to 6 are implemented.** Phase 1: a monorepo with a placeholder mobile app, a FastAPI
service, a generated API client, CI, an Android APK workflow and Render/Supabase deployment
configuration (ADR 010). Phase 2 (ADR 011, ADR 012; `docs/data-model.md`): the `geo` and `app`
schemas, the region import and GeoNames gazetteer commands and the "Import region" workflow, the
data quality report with the ADR 009 gates, destination and place search, the Photon adapter, a
seed trip, and CRUD for trips, user places and itinerary items. No region has been imported into
the real database yet. **Phase 3 is built and awaits acceptance** (ADR 013, proposed): the
travel-time service behind a FOSSGIS Valhalla adapter, with the `geo.travel_time` cache and the
labelled estimate fallback; it has no endpoint of its own and is used by the planner. The owner's
request-shape check is done (`docs/spikes/fossgis-request-shape-check.md`): the fixed 1 x N shape
agrees with the plain route. **Phase 4 is built and awaits acceptance** (ADR 014, proposed): the
planning engine v1 in `detour_api/planner/` (two strategy profiles, heuristic sequencer, category
duration table, diversity gate, independent validator, reason templates) and
`POST /v1/trips/{id}/itineraries/generate`; tried on synthetic fixtures only. **Phase 5 is built
and awaits acceptance** (ADR 015, proposed): the mobile screens in `apps/mobile/src` (trips, create
trip, comparison of two proposals, day list, plan map, selection, on-device read cache, offline and
"waking the server" states); the owner reported on 2026-11-13 that the app works on the phone. The
Android end-to-end workflow (`e2e-android.yml`) runs **by hand only**. **Phase 6 is built and
awaits acceptance** (ADR 016, proposed): meals in fixed windows at imported places to eat
(`planner/meals.py`), area destinations with base cities and inter-city legs (`planner/areas.py`),
Japan single-city only, migration `0006`; tried on synthetic fixtures only. **No budgets,
currencies or prices** (ADR 017, accepted 2026-11-13): none in the app, the API or the database;
bringing them back needs a new ADR. The decisions in `docs/app-plan.md`
section 1 are recorded; hosting (D3) is decided in ADR 005, the licence is Apache-2.0 (ADR 007),
and the app is not distributed through app stores (ADR 008). Do not start the next phase until the
owner asks for it.

## Read first

| Need | Document |
|---|---|
| What the product does and does not do | `docs/product-brief.md` |
| System design and planning engine | `docs/architecture.md` |
| Which providers may be used, and on what terms | `docs/api-evaluation.md` |
| Tables, the licence boundary, lifecycle | `docs/data-model.md` |
| Phases, dependencies, exclusions | `docs/app-plan.md` |
| Targets | `docs/kpis.md` |
| Recorded decisions | `docs/decisions/` |
| Working on the code, CI | `docs/development.md` |
| Deploying | `docs/deployment.md` |

## Hard constraints

1. **No LLM or generative-AI dependency** in the app, the backend, or any build step that
   produces user-facing content. Explanations are reason codes rendered through fixed templates.
2. **Out of scope, always:** booking, payments, hotel availability, flight-price comparison.
3. **No features beyond the stated product goals.** A new feature needs the owner's approval
   and an ADR.
4. **No new external provider without an ADR** that cites its official terms and the date they
   were read. A free trial is not a free tier.
5. **Never invent data.** No fabricated prices, ratings, opening hours or travel times. Missing
   values are stored and shown as unknown; estimates are labelled.

## Architecture rules

- The mobile app calls only the Detour backend and the map tile host. No other third-party
  call from the app.
- All planning logic lives in the backend, so Android and iOS share it.
- Plan generation makes no third-party network calls, with one exception (ADR 004): travel
  times not yet in the cache come from the FOSSGIS Valhalla server through the routing
  adapter. Otherwise it reads the database and the cache.
- Every external provider sits behind an adapter with a fallback, a timeout, caching, a daily
  budget counter and an identifying User-Agent.
- Do not call public community servers (Nominatim, Overpass, FOSSGIS routing,
  `tile.openstreetmap.org`) from code, tests or the app. Their policies do not allow it.
  Exception (ADR 004): backend code may call the FOSSGIS Valhalla server for travel times,
  through the adapter, within its rate rules, never from tests, CI or the app.
- Provider URLs, keys and the map style URL are configuration served by the backend, never
  constants in the app.
- Keep the two database schemas separate: `geo` for imported open data, `app` for user data.
  `app` refers to `geo` by identifier and does not copy its attributes. No foreign key may cross
  the schemas (a test enforces it). Data from different
  sources is stored as separate source records with their licence.
- The planning engine is deterministic: stable ordering, ties broken by identifier, fixed seeds,
  and the engine, configuration and data versions stored on every itinerary.
- Every generated itinerary must pass the independent validator.
- No Android-only native dependency without an ADR. Use Expo config plugins; do not hand-edit
  native projects.

## Planned stack

React Native with Expo and TypeScript; MapLibre React Native; Python with FastAPI; PostgreSQL
with PostGIS; Valhalla (FOSSGIS server per ADR 004, self-hosted only if S3 and the owner say so); Docker Compose for local development. No OR-Tools: spike S5
found the heuristic sequencer sufficient (D7). Exact versions are pinned in Phase 1 and recorded in
`docs/decisions/001-technology-stack.md`.

## Working conventions

- Follow the phases in `docs/app-plan.md`. Keep changes inside the current phase.
- Change a decision by adding or amending an ADR in `docs/decisions/`, numbered in sequence,
  with status, context, decision, alternatives and consequences.
- When a document states a provider quota or term, keep the source link and verification mark.
  Re-check the official page before relying on a figure; do not copy numbers from memory or
  from third-party lists.
- Update the affected documents in the same change as the work that makes them stale.
- Tests accompany every phase: engine golden tests, validator tests, adapter contract tests
  against recorded responses, API tests, app component tests.
- Attribution for OpenStreetMap, GeoNames and the tile provider must remain visible in the app.

## Commands

CI-first: everything below runs in GitHub Actions (`.github/workflows/ci.yml`) and in Claude Code
cloud sessions; nothing needs a local Windows toolchain. Details: `docs/development.md`.

From the repository root (Node 22):

- `npm ci`: install the JavaScript workspaces (`apps/mobile`, `packages/shared`)
- `npm run format:check` / `npm run format`: prettier
- `npm run typecheck`, `npm run lint`, `npm test`: tsc, eslint, jest
- `npm run generate`: regenerate `packages/shared/src/schema.d.ts` from `packages/shared/openapi.json`

From `services/api` (Python 3.13, `pip install -e ".[dev]"`):

- `ruff check . ../../tools` and `ruff format --check . ../../tools`
- `mypy` (strict)
- `pytest`: set `DETOUR_TEST_DATABASE_URL` to run the four database tests (CI always does)
- `python scripts/export_openapi.py`: rewrite `packages/shared/openapi.json`; run it, then
  `npm run generate`, whenever endpoints or models change (CI fails on drift)
- `pytest tests/test_planner_engine.py --update-golden`: rewrite the planner's golden files after
  an intended engine or configuration change (bump `CONFIG_VERSION`), then review the diff

Other:

- `python tools/check_dependencies.py`: fails if an LLM or generative-AI library is listed
- `python -m detour_api.importer region <id>` / `gazetteer <ISO2>...`: the imports (in CI they run
  through the "Import region" workflow; `osm2pgsql` and `osmium-tool` are needed locally)
- `python -m tests.e2e_seed` (from `services/api`): the fixture database for the Android end-to-end
  test (the "E2E Android" workflow, started by hand)
- `python -m detour_api.seed`: build the labelled seed trip from imported data
- The database tests also need `osm2pgsql` and `osmium` (CI installs them; locally the import
  tests are skipped without them)
- `docker compose --env-file .env -f infrastructure/docker-compose.yml up --build --wait`:
  optional local database and API (`cp .env.example .env` first)
- Android APK: run the "Android APK" workflow by hand (`docs/deployment.md`, steps 7 to 9)

Rules for this phase's code: no secrets in the repository (`.env.example` only; secrets live in
Render, Supabase and GitHub settings); pin exact versions; the app reads the map style URL from
`GET /v1/config`, never from a constant.
