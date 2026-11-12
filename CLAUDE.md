# CLAUDE.md

Guidance for AI-assisted work in this repository.

## Project

Detour is a cross-platform travel-itinerary planner: Android first, iPhone later. The user
gives a destination or area and a trip length; the app proposes at least two meaningfully
different itineraries and recalculates when the user adds places or restaurants.

## Current state

**Documentation only.** There is no application code, no build, and no commands to run. The
decisions in `docs/app-plan.md` section 1 are recorded; hosting (D3) is decided in ADR 005, the
licence is Apache-2.0 (ADR 007), and the app is not distributed through app stores (ADR 008). Do not scaffold a project or write production code until the owner asks for
implementation.

## Read first

| Need | Document |
|---|---|
| What the product does and does not do | `docs/product-brief.md` |
| System design and planning engine | `docs/architecture.md` |
| Which providers may be used, and on what terms | `docs/api-evaluation.md` |
| Tables and the restaurant price model | `docs/data-model.md` |
| Phases, dependencies, exclusions | `docs/app-plan.md` |
| Targets | `docs/kpis.md` |
| Recorded decisions | `docs/decisions/` |

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
  `app` refers to `geo` by identifier and does not copy its attributes. Data from different
  sources is stored as separate source records with their licence.
- The planning engine is deterministic: stable ordering, ties broken by identifier, fixed seeds,
  and the engine, configuration and data versions stored on every itinerary.
- Every generated itinerary must pass the independent validator.
- No Android-only native dependency without an ADR. Use Expo config plugins; do not hand-edit
  native projects.

## Planned stack

React Native with Expo and TypeScript; MapLibre React Native; Python with FastAPI; PostgreSQL
with PostGIS; Valhalla (FOSSGIS server per ADR 004, self-hosted only if S3 and the owner say so); Docker Compose for local development. OR-Tools only if the
Phase 0 spike justifies it. Exact versions are pinned in Phase 1 and recorded in
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

None yet. This section is filled in when Phase 1 creates the project.
