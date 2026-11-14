# ADR 024 — Multi-city trips with stops the user chooses

- **Status:** **Approved** by the owner on 2026-11-14 ("Approved, go ahead with your defaults. For
  2 - Finer names."), **built and awaiting acceptance** (see "Built" at the end); tried on synthetic
  fixtures only.
- **Date:** 2026-11-14
- **Related:** [`../briefs/multi-city-trips-and-photos.md`](../briefs/multi-city-trips-and-photos.md)
  (Part 1), [`016-phase-6-meals-and-area-destinations.md`](016-phase-6-meals-and-area-destinations.md)
  (area trips, base cities, `single_city_countries`),
  [`018-phase-7-add-place-and-recalculation.md`](018-phase-7-add-place-and-recalculation.md) (change
  sets, versions, locks), [`019-phase-8-add-a-restaurant.md`](019-phase-8-add-a-restaurant.md),
  [`009-region-readiness-thresholds.md`](009-region-readiness-thresholds.md) (gate 5, Japan),
  [`021-trip-manager-redesign.md`](021-trip-manager-redesign.md) (trip names and cards),
  [`004-fossgis-valhalla-demo-server.md`](004-fossgis-valhalla-demo-server.md)

## Context

The owner and their partner want trips they lay out themselves: Tokyo, then Kyoto, then Osaka, in
that order, with the days they choose for each. Today a trip has one destination. A city is planned
from one base; an area gets base cities chosen by the planner (`planner/areas.py`: eligible towns,
how many, which, days by score, order by travel time) joined by driving legs. Japanese areas are
refused (`area_single_city_only`) because rail, not driving, joins Japanese cities, and the planner
has no public transport (Phase 10).

**What already exists and is reused** (checked in the code on 2026-11-14):

- The engine plans a trip as **segments**: a base city with a run of consecutive days
  (`engine._Segment`), solved base by base, with the first day at a later base shortened by the
  arrival leg (`engine._solve`, `engine._arrival`). An area trip builds its segments in
  `engine._scope` from `areas.choose_bases`, `areas.order_bases` and `areas.allocate_days`; a city
  trip is one segment. A route trip only needs a third way to build the segments: from the user's
  stops, in the user's order, with the user's days. Candidates are assigned to the nearest base, as
  for areas.
- `app.itinerary_day` already holds `base_city_id`, `base_city_name` and the arrival leg
  (`arrival_mode`, `arrival_seconds`, `arrival_meters`, `arrival_confidence`); the API's `Day` has
  `base_city_lat`/`lon`; the app draws transport markers for a new base city and the day's base
  city line.
- The recalculation (`planner/recalc.py`) already chooses the days of the bases near an addition
  (`add_place`: bases within `new_base_min_m`, `only_day` for place suggestions); restaurant slots
  build on it. It can also open a **new base** for a far addition (`_new_base`), which a route trip
  must not do (decision 13).
- The diversity gate (`engine._distinct`) passes two plans that divide the days between different
  bases **or** whose visits overlap little. With the bases fixed by the user, only the overlap test
  is left, which is what the brief asks for.
- The past-trip archive keeps one `trip_visit` per base city, so it works for route trips unchanged.

## Decision

### Data

1. **`app.trip_stop`** (migration `0012`; `0011` is the photo amendment of ADR 022, built first):
   `id` uuid, `trip_id` (fk to `app.trip`, `ON DELETE CASCADE`), `position` (1, 2, …; unique per
   trip), `city_id` (the GeoNames id, bigint, **no foreign key into `geo`**), a snapshot of
   `city_name`, `country_iso2` and `point` taken when the stop is added, and `days` (at least 1).
   The API checks that the city exists and is in an available region.
2. **`app.trip.destination_kind` gains `route`.** For a route trip `destination_ref` is the first
   stop's city id, `destination_name` the trip's name (decision 16) and `destination_point` the
   first stop's point, so code that reads one destination keeps working. City and area trips are
   unchanged and gain no stops.
3. **`app.itinerary.stops_version`** (integer, null for city and area trips): the trip's stop list
   version the plan was made for. `app.trip.stops_version` goes up with every applied stop edit.

### Rules for the stops

4. **Two to six stops** (six is the planner's `max_bases`). A route of one stop is refused
   (`route_needs_two_stops`): that is a city trip.
5. **Days.** Each stop has at least one day; the stops' days add up to the trip's length (1 to 30);
   the API refuses anything else (`stop_days_mismatch`). The new-trip screen splits the length
   evenly (the remainder to the first stops) and the user changes it.
6. **Order is the user's.** The planner never reorders stops. Two consecutive stops may not be the
   same city (`stop_repeated`); the same city may come back later (Tokyo, Kyoto, Tokyo for the
   flight home). A place visited at one stop is not planned again at a later stop of the same city.
7. **Regions.** Every stop must be a city in an `available` region (ADR 009); otherwise `422
   region_not_available` naming the stop's position. Stops may be in different countries.
8. **No driving distance on the new-trip screen.** It would call the routing server on every edit
   of the form. The plan's legs show the time and distance once it is generated.

### Legs between stops

9. **Where driving is sensible, the leg is driven**, as for area trips: the travel-time service
   (cache, then FOSSGIS Valhalla, then the labelled estimate), shown with its confidence.
10. **Where either end is in a rail-dominant country** (`single_city_countries`, today Japan), the
    leg is a transport marker whose **time is unknown**: `arrival_mode` `unknown`,
    `arrival_seconds` and `arrival_meters` null, `arrival_confidence` `unknown` (a new value). The
    app writes "Travel to Kyoto · time not calculated: public transport is not built yet". No
    figure is shown or used. Phase 10 fills these legs in.
11. **The arrival day after an unknown leg is planned as a normal full day and marked** (a note
    `ARRIVAL_TIME_UNKNOWN` through the fixed templates: "Day 4 starts in Kyoto; the journey from
    Tokyo is not included in the day's times"). No reserve is invented. *Proposed default; the owner
    confirms.* Alternative: plan that day as half a day. Not proposed, because half a day is itself
    an invented duration.
12. **Japan as a whole stays refused as an area** (`area_single_city_only`). Explicit stops in Japan
    are allowed on the basis of decisions 10 and 11, **once Japan is imported and passes its gates**
    (decision 22).

### Planning

13. **The generator plans per stop.** `PlanRequest` gains `kind = "route"` and the stops;
    `engine._scope` builds one segment per stop from them and skips `areas.eligible_bases`,
    `choose_bases`, `order_bases` and `allocate_days`. Each stop's candidates are those within the
    profile's radius of the stop, assigned to the nearest stop (ties by position). Both profiles use
    the same stops and days.
14. **Two meaningfully different plans.** The bases are fixed, so plans differ by their visits: the
    existing overlap gate applies to the whole plan **and** to every stop where both plans have at
    least three visits. If a stop is too small to differ (few sights), the plans may share its
    visits and a note says so (`STOP_TOO_SMALL_TO_VARY`). The diversity rounds re-solve Wider as
    today.
15. **`CONFIG_VERSION` is bumped**; golden files are rewritten with `--update-golden` and the diff
    reviewed; existing city and area goldens must not change except for the version string.
16. **The independent validator** also checks, for a route plan: the days' base cities follow the
    stops in order with each stop's day count; every first day at a later stop has an arrival leg
    (routed, estimated or unknown) and no other day has one; an unknown leg only where an end is in
    `single_city_countries`; the days add up to the trip's length; every visit lies within the
    radius of its day's stop; no place appears twice.
17. **New reason codes** (`ARRIVAL_TIME_UNKNOWN`, `STOP_TOO_SMALL_TO_VARY`, `OUTSIDE_STOPS`,
    `STOP_REMOVED_ITEMS`) only through the fixed template table (`planner/reasons.py`). No other
    text is generated.

### Recalculation (adding, removing, locking)

18. **Adding a place or a restaurant** picks the days of the stops near it (`add_place` as today;
    `place-suggestions` and `only_day` unchanged). **A route trip never gets a new base** from an
    addition: a place farther than `new_base_min_m` from every stop is refused with `OUTSIDE_STOPS`
    ("Hallstatt is 45 km from your stops; add it as a stop first"). Removing and locking work as
    today. Tested on a synthetic three-stop trip.

### Editing the stops after creation (owner: stops can be edited)

19. **A stop edit is a change set**, action `edit_stops` (Phase 7 mechanism: preview with a diff,
    then apply or discard; a new itinerary version on apply; removing the latest change restores the
    previous version). The payload is the whole new stop list. It applies to the trip's **active**
    itinerary; the preview is made by repair, not by generating a new plan:
    - **An unchanged stop** keeps its days and items; only its day numbers and dates move.
    - **A stop with fewer days** drops whole days from its end, keeping locked items by moving them
      into the remaining days where they fit; if they do not fit, the preview says so and Apply is
      refused until the user unlocks or keeps the days.
    - **A stop with more days** gets empty days at its end, filled from that stop's unplanned
      candidates by the sequencer with the plan's profile (a manual plan's days stay empty).
    - **A new stop** gets its days planned the same way (empty in a manual plan).
    - **A removed stop** drops its days and every item on them, **including places the user added and
      locked items**. The preview lists them by name with "added by you" and "locked" marks
      (`STOP_REMOVED_ITEMS`), so nothing disappears silently. The user's places stay in the trip's
      list (`app.user_place`) and can be added again.
    - **A reorder** moves each stop's days with it; the arrival legs are recomputed (decisions 9 and
      10). A stop that becomes first loses its arrival leg; its first day is not refilled.
    - The trip's length becomes the new sum of days; the name follows the stops (decision 21) unless
      the user has renamed the trip.
20. **The other itineraries** of the trip (the original proposals) keep their `stops_version`. When
    it no longer matches the trip's, they are shown as "made for the earlier stops" and cannot be
    chosen; "New proposals" in Trip settings generates new ones for the current stops.

### API

21. `TripCreate` gains `destination_kind: "route"` and `stops: [{city_id, days}]` (required for a
    route, refused otherwise); `Trip` gains `stops: [{position, city_id, name, country_iso2, lat,
    lon, days}]` (empty for other kinds) and `stops_version`. `POST
    /v1/trips/{id}/itineraries/generate` plans per stop. `POST /v1/itineraries/{id}/changes` accepts
    `edit_stops`. `422` reasons: `region_not_available` (with the stop's position),
    `route_needs_two_stops`, `stop_days_mismatch`, `stop_repeated`, `too_many_stops`. `openapi.json`
    is regenerated (`python scripts/export_openapi.py`, `npm run generate`).

### Trip name (owner decision)

22. **Two stops:** "Tokyo to Osaka" (first city to last). **Three or more:** "Multi-city <place>":
    the country's name when every stop is in one country ("Multi-city Japan"), else the continent
    when all stops share one ("Multi-city Europe"), else "Multi-city trip". The country name comes
    from `geo.country.name`; the continent from GeoNames' `countryInfo.txt` continent code, kept as
    a new `geo.country.continent` column (filled by re-running the gazetteer command), mapped by a
    fixed table: `EU` Europe, `AS` Asia, `AF` Africa, `NA` North America, `SA` South America, `OC`
    Oceania, `AN` Antarctica. No generated text. The name follows stop edits. *The continent wording
    is a proposed default; the owner confirms or names finer regions (decision 25).*
23. **Cover:** the first stop's photo unless the user chose one (ADR 022 amendment, "Change photo"
    offers candidates of every stop's city).

### Mobile

24. **New trip:** the destination field becomes the first stop; "Add another city" adds a stop with
    its own search; each stop is a hairline row with the city, days (minus and plus) and a drag
    handle to reorder (and Remove); the total length is shown and must match. With one stop the
    screen is today's city trip. "Start with an empty trip" makes a manual plan with each day's base
    city set. **Overview and Itinerary** show each day's city and the existing transport markers;
    an unknown leg reads "time not calculated". **Trip settings** gains "Edit stops", which opens the
    same stop list and then the change preview.

### Japan (decision 12)

25. **Japan is not imported and fails gate 5** (73 to 79 % of names without Latin letters, spike S2).
    `DISPLAY_RULE_IMPLEMENTED` is `False`. A display rule could be: show the English name
    (`name:en`, kept since migration `0010`) where OpenStreetMap has one, else the local name; gate 5
    would then count a name as displayable if it has Latin letters **or** an English name. Whether
    that reaches 90 % is unknown; it is measured by a dry-run import of Japan (the report gains that
    share) before anything is decided. If it does not pass, the owner chooses between: accepting
    local-script names for places without an English one (restaurants mostly), lowering the gate
    for Japan, or not using Japan yet. Transliteration is not proposed: reading kanji is ambiguous,
    so it would show guessed names.

## Open for the owner

- **Arrival day after an unknown leg** (decision 11): planned as a normal day and marked. Confirm.
- **Wording across countries** (decision 22): continents only ("Multi-city Europe"), or a finer
  table (for example "Central Europe", "Southeast Asia")?
- **Japan names** (decision 25): after the dry-run figures.

## Alternatives

| Alternative | Why not |
|---|---|
| Let the planner choose and order the stops (area trips) | The owner wants their own cities and order |
| A rail estimate between Japanese cities | Rule 5: no invented travel times; the owner chose to wait for Phase 10 |
| Regenerate the whole plan on a stop edit | Loses the user's additions and locks silently; the brief asks for change sets |
| Store stops as JSON on `app.trip` | Harder to validate and to version; a table is plain |
| A foreign key from `trip_stop` to `geo.city` | Forbidden: no key crosses the schemas |
| Allow a new base when adding a far place to a route | The bases are the user's; a stop is added explicitly instead |

## Consequences

- Migrations `0012` (`app.trip_stop`, `stops_version` columns, the new `destination_kind`, the
  `unknown` arrival values) and a `geo.country.continent` column (in `0012`, filled by the gazetteer).
- Tests, all on synthetic fixtures: engine goldens for a two- and three-stop route (one in a
  `single_city_countries` country with unknown legs), validator tests for every new check, recalc
  tests on a three-stop trip (add near each stop, `OUTSIDE_STOPS`, `only_day`, remove, lock), stop
  edit change-set tests (each case of decision 19), API tests for the `422` reasons, app component
  tests for the stop list and the unknown-leg text. No test calls a public server.
- Docs in the same change as the code: this ADR (status), `architecture.md` (planning and API),
  `data-model.md`, `app-plan.md`, `design.md`, `CLAUDE.md`.
- Japan stays unusable until it is imported and gate 5 is settled; the multi-city feature is useful
  in Austria (and in Czechia, Hungary and Italy once imported) before that.
- Build order (after the photo work of the ADR 022 amendment): data and API; planner, validator and
  goldens; recalculation and stop edits; app.

## Built (2026-11-14, awaiting acceptance)

The owner's answers to "Open for the owner": the arrival day after an unknown leg is planned as a
normal day and marked (decision 11, as proposed); trips across countries get **finer names** than
continents (decision 22); Japan's names wait for the dry-run figures (decision 25).

Where the build differs from the decisions above, and why:

- **Names (decision 22):** the regions and continents are a fixed table in code
  (`detour_api/naming.py`: Central, Western, Northern, Southern and Eastern Europe, the Balkans, East,
  Southeast and South Asia, the Middle East, North Africa, North America, Australia and New Zealand),
  keyed by the stops' GeoNames country codes, so no `geo.country.continent` column and no gazetteer
  re-run were needed. Country names come from `geo.country.name`. "Unless the user has renamed the
  trip" is not built: the name always follows the cities.
- **Region refusal (decisions 7, 21):** `region_not_available` is **409**, as it already is for a
  single destination, not 422.
- **Stop edits (decision 19):** the preview is `POST /v1/trips/{id}/stops/preview` (a change set
  with action `edit_stops`, applied and discarded with the usual endpoints), not an action of
  `POST /v1/itineraries/{id}/change-sets`. A trip without a chosen plan changes its stops directly
  with `PUT /v1/trips/{id}/stops`. **A locked item on a day that a shorter stay drops stops the
  edit** (`LOCKED_ON_DROPPED_DAY`: unlock it or keep the day); moving it into the remaining days is
  not built. A manual plan keeps its days as they are, with empty new days and no layout.
- **New days** are filled by the planner's own plan of that city (the engine on the city, the plan's
  profile, leaving out places the trip has), then every changed day is laid out again by the
  recalculation and checked by the revision validator against the assembled plan.
- **Reordering in the app** is Up and Down buttons on each row, not a drag handle (no gesture
  library is added; the buttons are larger targets and work with a screen reader).
- **Japan (decision 25)** is not measured yet: the dry-run import of Japan, with the share of names
  that have Latin letters or an English name, is still to be run by the operator.
- Migration `0012` also relaxes `change_set_place_xor` for `edit_stops`; `CONFIG_VERSION` is
  `2026-11-14.2`; the existing goldens changed only by the new `arrival_unknown: false` field.
