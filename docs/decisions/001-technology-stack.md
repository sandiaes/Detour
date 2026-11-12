# ADR 001 — Technology stack

- **Status:** Accepted on 2026-11-12, except hosting (D3), which is open.
- **Date:** 2026-11-12
- **Related:** [`../architecture.md`](../architecture.md), [`002-api-strategy.md`](002-api-strategy.md)

## Context

Detour is a travel-itinerary planner that must ship first on Android, reach iPhone later
without a substantial rewrite, plan deterministically without any LLM at runtime, and rely on
free or open data and services. A provisional stack was proposed and had to be evaluated.

Facts established from official sources on the decision date:

- Expo SDK 58 targets React Native 0.88. Since SDK 55 the New Architecture is always enabled.
  Minimum platforms: Android 7 and iOS 16.4.
- MapLibre React Native v11 is MIT-licensed, supports only the New Architecture, requires
  React Native ≥ 0.80, and cannot run in Expo Go; it needs a development build and its config
  plugin.
- `expo-maps` is alpha and renders Google Maps on Android and Apple Maps on iOS.
- The EAS free plan includes 15 Android and 15 iOS builds per month.
- The recommended PostGIS image is `postgis/postgis:18-3.7`; older `-3.5` and `-3.6` tags are
  no longer updated.
- OR-Tools is Apache 2.0 and its routing solver documents time windows, optional visits with
  penalties, search limits and selectable search strategies.
- Valhalla is MIT-licensed, ships Docker images, builds from OSM extracts and provides routes
  and time-distance matrices for several travel modes from one dataset.
- The public community routing, geocoding and query servers do not permit application-scale
  use (see ADR 002).

## Decision

| Layer | Decision |
|---|---|
| Mobile | React Native with Expo (SDK 58 at the time of writing) and TypeScript. Continuous Native Generation; development builds from day one; no hand-maintained native projects. |
| Maps in the app | MapLibre React Native with vector tiles from an OSM-compatible provider. |
| On-device storage | `expo-sqlite` as a read cache of trips. |
| Backend | Python with FastAPI, exposing a versioned OpenAPI contract from which the app's types are generated. |
| Database | PostgreSQL with PostGIS, in two schemas: `geo` (imported open data) and `app` (user data). |
| Routing | Valhalla, self-hosted per imported region, behind a travel-time interface with a straight-line fallback. |
| Planning | A deterministic engine in the backend, with an independent validator and structured reason codes. |
| Optimisation | A `Sequencer` interface with a simple heuristic as baseline. OR-Tools becomes the default implementation only if the Phase 0 spike justifies it. |
| Local development | Docker Compose: database, API, Valhalla, and one-shot import jobs. |
| Identity | Anonymous installation with a bearer token. No accounts in the MVP. |

All planning logic lives in the backend so that Android and iOS share it completely.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Native Android (Kotlin) first | The iPhone version would be a second application. |
| Flutter | Viable, but offers no advantage over the proposed stack here and changes the owner's stated direction. |
| `expo-maps` or Google Maps SDK | Alpha status; different renderers per platform; needs a Google Cloud project; ties place data to Google's display terms. |
| Planning engine on the device | Would duplicate geospatial queries, routing and the solver in a mobile runtime, and complicate the iOS port. |
| OSRM for routing | Faster, but needs a separately preprocessed dataset per travel mode. Kept as the fallback engine. |
| Hosted routing free tiers | Small quotas or unverified terms; see ADR 002. |
| OR-Tools from the first planner version | Adds a native dependency and reproducibility questions before the simpler approach has been measured. |
| A document or key-value database | The workload is relational and spatial. |

## Consequences

**Positive**

- One codebase for Android and iOS; iOS is a build, permission and testing task.
- No per-request provider cost in the core planning path.
- Reproducible itineraries that can be tested with golden fixtures.
- Providers can change without an app release.

**Negative**

- A backend must be operated, including a routing container and a spatial database.
- Coverage is limited to imported regions until on-demand import exists.
- Development builds are required from the first day; Expo Go cannot be used.
- Two languages (TypeScript and Python) and a contract between them to maintain.

**Risks**

- Resource needs of Valhalla for Italy are measured (S3: about 8 GB RAM to build, 2.4 GB of tiles); the other countries are not.
- MapLibre React Native is community-maintained and outside the Expo SDK.
- OR-Tools searches bounded by wall-clock time may not be reproducible across machines.

## Decision record

| ID | Decision | Status |
|---|---|---|
| D3 | Backend hosting beyond a local machine | **Open.** Supabase is a candidate for the database only; the API server and Valhalla need a separate host. Owner constraint: free, managed services (app-plan D14). Decide after S3. Details in `../app-plan.md`, section 1. |
| D5 | Anonymous installation identity, no accounts | Approved 2026-11-12 |
| D7 | OR-Tools adopted only if the spike shows better plans within the latency budget | Approved 2026-11-12 |

## Follow-up

- Pin exact versions (Expo SDK, React Native, MapLibre, Python, FastAPI, PostGIS image) in
  Phase 1 and record them here.
- Record the navigation, server-state and form libraries for the app in a new ADR in Phase 5.
