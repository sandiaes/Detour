# Detour

A mobile travel-itinerary planner. Give it a destination or area and a trip length; it proposes
at least two clearly different itineraries and keeps the plan coherent as you add places and
restaurants. Planning is deterministic: **no LLM is used at runtime.**

Android first. The architecture is built so that an iPhone version is a build and testing
task, not a rewrite.

## Status

**Phase 1 (foundation) is built:** a monorepo with a placeholder Android-first app, a FastAPI
backend, a generated typed API client, CI, an APK build workflow, and Render and Supabase
deployment configuration.

**Phase 2 (data and search) is built, awaiting the owner's acceptance:** the `geo` and `app`
database schemas, a region import (manually started GitHub Actions workflow: Geofabrik extract,
selection rule, data quality report and readiness gates), a GeoNames gazetteer import, destination
and place search with Photon as the only external fallback, a seed trip, and endpoints for trips,
user places and itinerary items. **Phases 3 to 7 are built and await acceptance:** travel times
(ADR 013), the planner (two itineraries for a city, ADR 014), the mobile screens with the day list
and map (ADR 015), meals and area destinations (ADR 016), and adding or removing a place with a
previewed recalculation and itinerary versions (ADR 018). The app has no budgets, currencies or
prices (ADR 017). Later work follows the phases in [`docs/app-plan.md`](docs/app-plan.md). The architecture, API strategy,
hosting, licence and distribution are decided (see below).

## Repository layout

| Path | Contents |
|---|---|
| `apps/mobile` | Expo SDK 58 + TypeScript app, MapLibre React Native |
| `services/api` | Python + FastAPI backend, Alembic migrations, tests |
| `packages/shared` | OpenAPI contract and the generated typed client |
| `infrastructure` | Docker Compose with PostgreSQL and PostGIS (optional, for a capable machine) |
| `render.yaml` | Render Blueprint for the API |
| `docs` | Product, architecture and decision documents |

Everything is built and tested in GitHub Actions; no local toolchain is required
([`docs/development.md`](docs/development.md)). To deploy and try the app on a phone, follow
[`docs/deployment.md`](docs/deployment.md).

## Documents

| Document | Contents |
|---|---|
| [`docs/product-brief.md`](docs/product-brief.md) | Goals, user flows, scope, assumptions |
| [`docs/architecture.md`](docs/architecture.md) | System design, planning engine, integration rules |
| [`docs/api-evaluation.md`](docs/api-evaluation.md) | Every candidate API and data source, with verified terms |
| [`docs/data-model.md`](docs/data-model.md) | Logical data model, lifecycle, licence boundary |
| [`docs/app-plan.md`](docs/app-plan.md) | Phased plan, dependencies, risks, MVP exclusions |
| [`docs/kpis.md`](docs/kpis.md) | Proposed targets and how each is measured |
| [`docs/decisions/001-technology-stack.md`](docs/decisions/001-technology-stack.md) | ADR: technology stack |
| [`docs/decisions/002-api-strategy.md`](docs/decisions/002-api-strategy.md) | ADR: API and data-source strategy |
| [`docs/development.md`](docs/development.md) | CI-first development, commands, optional local Docker Compose |
| [`docs/deployment.md`](docs/deployment.md) | Step-by-step Render, Supabase and phone setup |
| [`docs/decisions/010-phase-1-foundation-choices.md`](docs/decisions/010-phase-1-foundation-choices.md) | ADR: Phase 1 choices and pinned versions |
| [`docs/data-model.md`](docs/data-model.md) | The `geo` and `app` schemas, lifecycle, deletion and licence rules |
| [`docs/decisions/011-attraction-selection-rule-v2.md`](docs/decisions/011-attraction-selection-rule-v2.md) | ADR: stricter memorial test and generic `historic=*` classes |
| [`docs/decisions/012-phase-2-data-and-search-choices.md`](docs/decisions/012-phase-2-data-and-search-choices.md) | ADR: Phase 2 choices, terms read, open items |
| [`CLAUDE.md`](CLAUDE.md) | Working rules for AI-assisted development in this repository |

## Proposed architecture in brief

| Layer | Choice |
|---|---|
| Mobile app | React Native, Expo, TypeScript; MapLibre React Native for maps |
| Backend | Python, FastAPI; deterministic planning engine |
| Data | PostgreSQL with PostGIS; open data imported per region |
| Routing | FOSSGIS Valhalla server through a cached adapter (ADR 004), from Phase 3 |
| Hosting | Supabase Free (database), Render free web service (API), GitHub Actions (ADR 005) |
| Local development | GitHub Actions first; Docker Compose optional |

Open data (OpenStreetMap, GeoNames, Wikidata) is imported into the project's own database, so
generating an itinerary makes no third-party API calls. The few external services (map tiles,
fallback place search, daily exchange rates) sit behind backend adapters with named fallbacks.

## Decisions

Decided on 2026-11-12: the project is open source and non-commercial (D1); the MVP covers
Japan, Italy and Central Europe (Austria, Czechia and Hungary at least) (D2); D4 to D10 are
approved as recommended.

Since then: opening hours are out of scope (ADR 003); travel times come from the FOSSGIS Valhalla
server through a cached adapter (ADR 004); hosting is Supabase Free, a Render free web service
and a GitHub Actions import job (ADR 005); past trips are kept as an archive (ADR 006); the
licence is Apache-2.0 (ADR 007); there are no app stores (ADR 008); region readiness gates are
set (ADR 009). The repository stays private until the owner decides to publish it.

Details: [`docs/app-plan.md`](docs/app-plan.md), section 1.

## Scope guards

Not part of this product: booking, payments, hotel availability, flight-price comparison, and
any LLM or generative-AI dependency.

## Data attribution

The planned data sources require attribution, including "© OpenStreetMap contributors"
(ODbL) and GeoNames (CC BY 4.0). The full list is maintained in
[`docs/api-evaluation.md`](docs/api-evaluation.md).

## Licence

The Detour source code is licensed under the Apache License 2.0; see [`LICENSE`](LICENSE).
Imported map data keeps its own licence (for example ODbL for OpenStreetMap).
