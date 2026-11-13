# ADR 015 — Phase 5 mobile shell choices

- **Status:** Proposed (implemented 2026-11-12; awaits the owner's acceptance).
- **Date:** 2026-11-12
- **Related:** [`001-technology-stack.md`](001-technology-stack.md) (follow-up: navigation, server
  state, forms), [`004-fossgis-valhalla-demo-server.md`](004-fossgis-valhalla-demo-server.md),
  [`006-past-trips-archive.md`](006-past-trips-archive.md),
  [`008-no-app-stores.md`](008-no-app-stores.md), [`014-phase-4-planner-v1.md`](014-phase-4-planner-v1.md)

## Context

Phase 5 asked for the trip list, the create-trip form, the comparison of two proposals, the day
list, the map with transfer lines, selection, an on-device read cache and the error, offline and
cold-start states, with accessibility, performance and tests. ADR 001 left the navigation,
server-state and form libraries to this phase. The request said "development builds"; ADR 008's
addendum already replaced them with release-variant APKs.

## Decisions

1. **No navigation library.** A 60-line stack held in React state (`nav/Navigator.tsx`): two root
   tabs (Trips, Settings) and four pushed screens. It handles Android's back button. A library
   would bring a native screens module and a second state model for six screens. Revisit when
   Phase 7 adds screens that need deep links or a modal stack.
2. **No server-state or form library.** `data/DataProvider.tsx`: one in-memory map in front of the
   cache, in-flight requests de-duplicated by key, a 60 s freshness window (10 min for itineraries,
   which only change by a selection the app itself makes), and `put` and `update` so what the app
   changes appears at once without a refetch. Forms are plain state with small validators.
3. **On-device read cache: `expo-sqlite` 58.0.16** (already named in ADR 001; Expo's pinned
   version). One table of JSON values with a save time. Trips, the plan lists and each opened plan
   are kept; they are replaced by the next fetch and are never written back. Entries belong to one
   installation: a different installation id clears them. Nothing is edited offline and nothing
   syncs (scope guard). A failing database is never fatal (`safeStore`).
4. **Offline and cold start.** The screens read the cache first, then fetch. A server that cannot
   be reached (a failed request, or the backend connection in the error state) is "offline": saved
   data is shown with a notice and its age; with nothing saved the screen says so. While the
   connection is made after 4 s the app shows "Waking the server" (ADR 005): a full state when
   nothing is saved, a notice above saved trips otherwise. The app retries by itself when it comes
   back to the foreground. The map and anything that changes data need a connection, and say so.
5. **Map.** MapLibre React Native, as in S1. Stops are numbered `Marker`s (48 dp), added a batch at
   a time (`useProgressiveCount`); a line appears once both its stops are on the map. Transfer
   lines are **straight connectors between the stops**: the API returns no route geometry for
   stored transfers (ADR 013 stores none and no endpoint serves it). The time's label is drawn as
   solid (routed) or dashed (estimated) and explained under the map, together with the statement
   that lines are not the road path. Route geometry for the selected plan would need an endpoint
   and is not built. Attribution reuses `AttributionBar` (visible at start, collapsible, restorable)
   and is also listed in Settings from `GET /v1/attributions`.
6. **Comparison.** The "how they differ" summary is computed from the backend's `stats` and
   `diversity_score` through fixed sentence templates (`domain/compare.ts`). On a phone the plans
   are swiped in a snapping list and each has a button, so nothing needs a gesture; from 720 dp
   they sit side by side. "Cities covered" from the brief is not shown: every plan today covers the
   one destination city and the API returns no per-day city names.
7. **Areas cannot be chosen.** The backend rejects `POST …/generate` for areas
   (`area_not_supported`), so the search lists them but disables them with the reason, rather than
   creating a trip that cannot be planned. Regions that are not `available` are disabled the same
   way.
8. **Screens removed.** The Phase 1 placeholders for Map (the style-URL check, replaced by the plan
   map) and Saved Places (Phase 7) are gone; the Phase 1 shell tests were replaced.
9. **Design.** (Superseded on 2026-11-13 by [ADR 021](021-trip-manager-redesign.md): new tokens,
   line icons, illustrated covers, soft shadows; still no photos.) Warm paper background, one green accent, system type, 14 dp radius cards, no heavy
   shadows, no photos or illustrations. Text and control contrasts are asserted in `theme.test.ts`
   (4.5:1 and 3:1). English only; light theme only.
10. **Accessibility.** Controls are at least 48 dp (asserted over every screen in
    `accessibility.test.tsx`); every control has a spoken name; list rows read as one sentence;
    states carry words or marks as well as colour ("Routed"/"Estimated" tags with solid/dashed
    borders, "✓ Selected", "Offline." and "Problem." prefixes); live regions announce loading,
    errors and selection; layouts use minimum heights so text can scale. Not tested on a device
    with a screen reader or at the largest font scale (see Consequences).
11. **End-to-end test.** `.github/workflows/e2e-android.yml`: Postgres/PostGIS service, the
    fixture region imported by `services/api/tests/e2e_seed.py` (the API tests' invented extract),
    the API with routing and Photon **off** (no community server is called), a release x86_64 APK
    built with `DETOUR_E2E=1` (a local config plugin that only then allows cleartext HTTP to the
    runner at `10.0.2.2`), and **Maestro** (Apache-2.0 test tool; a CI tool, not an app dependency
    or a provider) running `apps/mobile/e2e/trip-flow.yaml` on an API 34 emulator. The Maestro
    version `2.8.0` was taken from a web search and **not verified** against the official
    releases page; the first run decides.

## Alternatives

| Alternative | Why not |
|---|---|
| React Navigation / Expo Router | A native module and its own state for six screens; no deep links needed yet |
| TanStack Query | A dependency for one fetch pattern with a persistent cache we need to control (per-installation, offline notice) |
| Detox or Appium for the end-to-end test | Heavier native and Gradle setup; Maestro drives the installed APK from one YAML file |
| `expo-dev-client` builds | Need a development server (ADR 008 addendum); the release variant has the same native code |
| Map lines from Valhalla geometry | No stored geometry; would need a new endpoint and provider calls (ADR 013) |

## Consequences

- Two API behaviours the screens rely on were read from the code and checked against the running
  API on the seeded fixture: plans come back whole from `generate` (so no follow-up request), and
  `PATCH /v1/trips/{id}` with `selected_itinerary_id` flips the statuses.
- Plan notes are verbose (seven per plan); the app shows them behind one control, including "Opening
  hours are not checked".
- **Not verified:** the end-to-end workflow has never run; the APK has not been built or run on a
  device in this change (Metro bundles the app and `expo prebuild` succeeds, and the seeded API was
  exercised by hand); screen-reader behaviour and large-font layouts are checked by tests of
  labels and sizes only; map performance on a low-end phone is untested (the plan's marker
  clustering risk stands; a day has at most 40 stops).
- New dependency: `expo-sqlite`. New CI tool: Maestro. No LLM dependency.

## Addendum (2026-11-13)

- The owner reported that the app works on the phone, and asked for the end-to-end workflow to be
  **manual**: `e2e-android.yml` now runs only on `workflow_dispatch` (no pull-request or push
  trigger). It has still not been run.
- The currency and meal-budget fields are removed from the new-trip form, and the trip screen no
  longer shows a budget ([ADR 017](017-no-budgets-currencies-or-prices.md)).
- Area destinations can be chosen (Phase 6, [ADR 016](016-phase-6-meals-and-area-destinations.md));
  the backend's `unavailable_reason` greys out regions without data and areas in Japan. The day
  list shows meals (meal, venue type, cuisine or "Cuisine not specified"), the base city of each
  day of a multi-base plan, and the drive between base cities with its Routed/Estimated tag.
