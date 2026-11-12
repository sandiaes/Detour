# Detour

A mobile travel-itinerary planner. Give it a destination or area and a trip length; it proposes
at least two clearly different itineraries and keeps the plan coherent as you add places and
restaurants. Planning is deterministic: **no LLM is used at runtime.**

Android first. The architecture is built so that an iPhone version is a build and testing
task, not a rewrite.

## Status

**Planning and documentation only.** No application code, no project scaffolding. The
architecture, API strategy, hosting, licence and distribution are decided (see below).

## Documents

| Document | Contents |
|---|---|
| [`docs/product-brief.md`](docs/product-brief.md) | Goals, user flows, scope, assumptions |
| [`docs/architecture.md`](docs/architecture.md) | System design, planning engine, integration rules |
| [`docs/api-evaluation.md`](docs/api-evaluation.md) | Every candidate API and data source, with verified terms |
| [`docs/data-model.md`](docs/data-model.md) | Logical data model, restaurant price model, licence boundary |
| [`docs/app-plan.md`](docs/app-plan.md) | Phased plan, dependencies, risks, MVP exclusions |
| [`docs/kpis.md`](docs/kpis.md) | Proposed targets and how each is measured |
| [`docs/decisions/001-technology-stack.md`](docs/decisions/001-technology-stack.md) | ADR: technology stack |
| [`docs/decisions/002-api-strategy.md`](docs/decisions/002-api-strategy.md) | ADR: API and data-source strategy |
| [`CLAUDE.md`](CLAUDE.md) | Working rules for AI-assisted development in this repository |

## Proposed architecture in brief

| Layer | Choice |
|---|---|
| Mobile app | React Native, Expo, TypeScript; MapLibre React Native for maps |
| Backend | Python, FastAPI; deterministic planning engine |
| Data | PostgreSQL with PostGIS; open data imported per region |
| Routing | Self-hosted Valhalla |
| Local development | Docker Compose |

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
