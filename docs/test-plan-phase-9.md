# Phase 9 test plan and results (2026-11-15)

Each journey of Prompt 10, task 5, with how it was checked and the result. **Pass** means the check
ran in this session and passed. **Needs the owner** means it has to be done on the phone: nothing in
this phase ran on a device, and the "E2E Android" emulator workflow could not run (GitHub Actions did
not start jobs, see [`audit-phase-9.md`](audit-phase-9.md)). Every journey below is therefore
**checked by tests only**.

Where: a Claude Code cloud container; PostgreSQL 16 with PostGIS 3, `osm2pgsql` and `osmium`; the
fixture database is the real import of the invented region in `tests/fixtures/region-sample.osm`
plus the GeoNames-shaped fixture (`conftest.py`); Photon is a recorded-format stub; there is no routing
provider (every travel time is a labelled estimate). App tests run with Jest against a fake server.

## 1. Journeys

| | Journey | Fixture database (API) | App (component tests) | Phone |
|---|---|---|---|---|
| a | Fresh empty trip; add a sight, a town, a pin, a restaurant through Photon and one by hand with a chosen day and time | **Pass**: `test_journeys.py` (one chained test, a then e, l, h and i); `test_an_empty_plan_can_be_filled_by_hand_and_nothing_is_suggested`; `test_manual_entry_keeps_what_the_user_gave_and_nothing_else` | **Pass**: CreateTrip "an empty trip is created without proposals…"; AddPlace (sight, town, address, pin); AddRestaurant (saved, by hand, café, wider search, used-up search) | Needs the owner |
| b | Generate for a 3-day city trip; compare; choose; "Free time"; no restaurants | **Pass**: `test_generation_stores_versioned_valid_itineraries`, `test_a_larger_city_gets_two_distinct_itineraries`, engine golden tests (sights only) | **Pass**: CreateTrip "the whole flow…"; Itinerary "an idle stretch… is a Free time row" | Needs the owner (a real Austrian or Italian city) |
| c | Multi-city (2 to 6 cities): add, edit, remove a city through a change set | **Pass**: `test_api_routes.py` (edit_stops change sets), `test_planner_routes_recalc.py` | **Pass**: MultiCity (adding, editing opens the preview, stop rules) | Needs the owner |
| d | Add a place to a planned itinerary, preview; an impossible addition; undo | **Pass**: `test_a_preview_changes_nothing_until_it_is_applied`, `test_infeasible_additions_say_which_constraint_conflicts`, `test_adding_then_removing_a_place_restores_the_previous_plan` | **Pass**: AddPlace (suggestions, "does not fit" with reasons), ChangePreview | Needs the owner |
| e | Optimize within a day and across days, locked and ticketed stops; preview, apply, undo | **Pass**: `test_api_optimize.py` (9 tests), `test_optimize.py` (18, one of them run on 12 seeded plans), and the chained journey (apply, undo, order restored) | **Pass**: Optimize (6: stops with documents preselected, locked always kept, undo only right after) | Needs the owner |
| f | Destination outside the imported regions: empty place trip; suggestions refused | **Pass**: `test_place_destinations.py` (8, incl. `destination_not_plannable`) | **Pass**: CreateTrip (no sight data offers only an empty trip; Photon; by hand) | Needs the owner |
| g | Documents: add, link to a day or place, open, delete with confirmation; on the phone only | n/a (no backend) | **Pass**: Documents (11) with a fake file module; the native picker and viewer are not exercised | **Needs the owner** (real PDF and photo) |
| h | Export one and all trips (with and without documents); import as new; damaged or oversized file refused | **Pass**: `test_trip_export.py` (9), chained journey (export, import, same stops, damaged file 422) | **Pass**: Exchange (14: switch on and off, missing file named, backup of all, refused file, "open with") | **Needs the owner** (share sheet, Files, open with) |
| i | Mark past; past by date; Days tab keeps stops, order, start, length; clear skipped; size report | **Pass**: `test_past_trips.py` (9), chained journey | **Pass**: PastTripScreen (17) | Needs the owner |
| j | A non-Latin name: English-facing name, local name kept, found by either, Edit display name persists | **Pass on fixtures**: `test_a_japanese_place_gets_its_english_name_and_keeps_the_original`, `test_the_import_keeps_search_aliases_and_search_finds_them`, `test_an_override_wins_is_reversible_and_applies_to_that_place_only` | **Pass**: PlaceDetail (English name leads, local under it, "Automatically romanized", edit and undo) | **Cannot be done on the phone today**: no non-Latin region is imported (Austria and Italy only) |
| k | Cover and place photos with credits; Change photo; Image credits | **Pass**: `test_api_cover.py`, `test_images.py`, `test_api_images.py` | **Pass**: Photos (6), PlaceDetail photo and credit, Cover fallback (new) | Needs the owner (689 photos in production) |
| l | No network (read cache); restart and recover; Render cold start; paused database; FOSSGIS unavailable (estimates labelled); Photon unavailable | **Pass**: `test_the_database_unavailable_is_a_503_not_a_crash`, `test_database_unreachable.py`, chained journey (every leg labelled), Photon timeout and 429 tests in `test_photon.py` | **Pass**: Trips and Itinerary offline and waking tests; BackendProvider retry with backoff (new); ResourceNotices for a paused database (new); AddPlace "not available" for Photon (new) | **Needs the owner**: airplane mode, force-stop and reopen, open after 20 idle minutes |

## 2. E2E Android

- `e2e/trip-flow.yaml` was **rewritten** for the manager-first screens (fresh trip, Add a place with a
  day and time, the day's map and credits, the Upcoming list). The old flow tapped "Plan a trip" and
  `day-row-1`, which no longer exist, so it could not have passed.
- `e2e/screenshot-tour.yaml`: the same two stale controls were fixed.
- **Run once (screenshot tour) on 2026-11-15: not run.** Run 43758197451 on this branch failed within
  five seconds with no runner, like every workflow of the repository since about 18:16 UTC that day.
  Both flows are therefore still unrun. Owner: once Actions runs again, Actions, "E2E Android", Run
  workflow on this branch, flow `screenshot-tour`, then `trip-flow`; record the result here.

## 3. The owner's phone check (about 30 minutes)

Install the APK built from this branch (or `main` after merging; [`android-release.md`](android-release.md)).
Before anything: **More, Back up all trips** with documents, and keep the file off the phone.

1. Airplane mode on, open Detour: the trips show with "saved … ago"; turn it off: within a minute the
   notice goes without tapping anything.
2. New trip, a city in Austria or Italy, **Start a fresh trip**; Add, Place: a sight, a town, a pin;
   Add, Restaurant: one from the wider search, one by hand at a chosen day and time.
3. On the same or another trip, **Generate itineraries** for 3 days: two cards; choose one; the day
   list shows "Free time" and no restaurant.
4. Trip menu, **Optimize**: across days, preview, apply, then Undo Optimize.
5. Documents tab: add a PDF and a photo, link one to a day, open it, delete it (confirmation).
6. Trip menu, Export trip with documents: the share sheet opens; then More, Import a trip with that
   file: a new copy with its documents.
7. Trip settings, Mark as past trip: the text says every stop is kept; the past trip's Days tab
   shows the stops with times; clear one visit.
8. A trip to a place outside Austria and Italy: only "Start a fresh trip" is offered.
9. Photos: a cover with its "i" credit; trip menu, Change photo; More, Image credits.
10. Leave the phone for 20 minutes, open Detour: "Waking the server", then the trips.

Write down every screen that looks or behaves wrong, with the step number. That list is what Phase 9
still needs: the report "everything is wrong" could not be traced to a cause from here.

## 4. Performance (task 7)

Measured in this container (not on Render, not on a phone). Engine: `python scripts/measure_performance.py`
from `services/api`. API: `tests/test_performance_api.py` (run with `-s` to print), fixture database.

| Measurement | Median | Worst | Target (KPI, p95) | Met |
|---|---|---|---|---|
| Generate two plans, city, 3 / 7 / 14 days (largest fixture, `city-large`) | 39 / 122 / 296 ms | 41 / 178 / 306 ms | 5 s | Yes |
| Generate, area, 3 / 7 / 14 days | 36 / 68 / 119 ms | 36 / 73 / 140 ms | 5 s | Yes |
| Multi-city planner, 3 cities 6 days / 6 stops 12 days | 55 / 110 ms | 55 / 115 ms | 5 s | Yes |
| Optimize engine, 30 stops over 7 days, within / across days | 3 / 42 ms | 3 / 46 ms | 5 s (up to 30 stops) | Yes |
| Optimize engine, 200 stops over 14 days, across days | 986 ms | 987 ms | none (beyond the KPI) | n/a |
| API: trip list, 20 trips | 9 ms | 10 ms | 3 s app start (device) | Server side yes; device not measured |
| API: a plan of 30 stops (day list and map read the same) | 9 ms | 10 ms | n/a | n/a |
| API: Optimize preview, 30 stops, across days | 117 ms | 147 ms | 5 s | Yes |
| API: destination search | 7 ms | 11 ms | 300 ms | Yes |
| App: a 14-day plan renders one day at a time (40 stops, not 560) | component test | | | Yes |
| App start to trip list, map and list scrolling on the phone | **not measured** | | 3 s | Needs the owner |

No target was missed. On Render's free instance (a share of one CPU) the server figures will be
several times higher and the first request after 15 idle minutes about a minute (ADR 005); routed
travel times add up to `planner_provider_max_seconds` (3 s) to a generation. These are not measured.

## 5. Counts

| Suite | Result |
|---|---|
| API (`pytest`, every database test on) | 813 passed, 0 failed; 94 % line coverage |
| App (`npm test`) | 52 suites, 502 tests, all passing |
