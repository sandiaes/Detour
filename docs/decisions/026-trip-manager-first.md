# ADR 026 — Trip manager and history first; generated plans are sights only; no restaurants in the data

- **Status:** **Proposed** on 2026-11-14, at the owner's request. The documents were written first;
  **build steps 2 to 6 are built** (see the "As built" sections); destinations, export and Optimize
  follow in the order of "Build order". The
  owner confirms or changes the numbers marked *proposed*.
- **Date:** 2026-11-14
- **Related:** [`006-past-trips-archive.md`](006-past-trips-archive.md) (amended),
  [`009-region-readiness-thresholds.md`](009-region-readiness-thresholds.md) (amended),
  [`011-attraction-selection-rule-v2.md`](011-attraction-selection-rule-v2.md) (amended),
  [`014-phase-4-planner-v1.md`](014-phase-4-planner-v1.md),
  [`016-phase-6-meals-and-area-destinations.md`](016-phase-6-meals-and-area-destinations.md)
  (superseded in part), [`018-phase-7-add-place-and-recalculation.md`](018-phase-7-add-place-and-recalculation.md),
  [`019-phase-8-add-a-restaurant.md`](019-phase-8-add-a-restaurant.md) (superseded in part),
  [`020-trip-centred-app.md`](020-trip-centred-app.md),
  [`021-trip-manager-redesign.md`](021-trip-manager-redesign.md) (amended),
  [`../product-brief.md`](../product-brief.md), [`../data-model.md`](../data-model.md)

## Context

The owner (2026-11-14): in about 99 % of their trips they start from a fresh trip and do not
generate an itinerary. They want the essence of the app to be a **trip manager and a history of
trips**, not an itinerary generator. When an itinerary is generated, it should contain only
attractions, no restaurants and cafés. Restaurants will be added by hand, through Photon, so the
imported restaurant data and everything Photon cannot supply (cuisine, served meals) should go.
Past trips should keep their historical data. Destinations outside the imported regions come first
among the manager features, and exporting a trip second.

This changes the product's emphasis and removes a set of built features, so it needs an ADR
(CLAUDE.md rules 3 and 4). It adds no provider: Photon is already behind an adapter (ADR 002, 012).

## Decision

### 1. The essence

1. **Detour is a trip manager and a history.** A trip is created empty, filled by hand, kept while
   it happens and kept afterwards as a record. Generating itineraries is an optional helper on
   top ("Suggest sights"), not the front door.
2. **The new-trip screen leads with the empty trip.** "Start with an empty trip" becomes the dark
   main button; "Suggest itineraries" (was "Generate itineraries") becomes the outlined second one.
   The text and behaviour of both are otherwise unchanged.
3. **The generator is frozen, not removed.** Its engine, diversity gate, validator and recalculation
   stay and are maintained, but no new work goes into them unless the owner asks.

### 2. Generated plans: sights only, with a midday gap

4. **A generated plan has no meals and no places to eat.** The engine does not look up restaurants
   or cafés, does not reserve meal time and does not write meal items.
5. **A midday gap replaces the lunch.** Each day with visits gets one unplanned `free_time` item
   around midday, so days are not unrealistically dense. It names no restaurant and no meal, and
   the app shows it as "Free time". *Proposed:* 90 minutes, starting between 12:30 and 14:00 at the
   earliest point the sequencer's route allows. The user can edit or remove it like any item. The
   numbers live in `planner/config.py`.
6. **The day window goes back to sightseeing hours.** *Proposed:* 09:00 to 20:00 for both
   profiles. (Until 2026-11-14 it was 09:00 to 21:00, widened to 22:00 to fit a 20:00 dinner,
   ADR 021 amendment.) `free_minutes` goes back to a value that keeps the sightseeing volume as
   before the dinner change (60 for Essentials, 90 for Wider before 2026-11-14), to be re-tuned
   against the fixtures.
7. **The second profile no longer adds a snack.** Both profiles lose their `meals`.
8. **Recalculation (ADR 018) stops laying out meals.** After an addition it re-lays the midday gap
   with the same function the engine uses. Items the user added, restaurants included, are
   mandatory, as before: never left out, and they keep their day and times.
9. **The engine's output changes**, so `CONFIG_VERSION` is bumped and the golden files are
   regenerated and reviewed. Plans already stored keep their own engine and configuration
   versions and are not rewritten; their meals stay as ordinary restaurant or café stops.
10. **The validator and the revision validator** drop the meal-window and meal-length checks and
    gain a check for the gap (inside the day, not overlapping an item). The KPIs "Meals in their
    windows" and "Meals planned" are removed; "Day utilisation" is measured against the new window
    (`kpis.md`).

### 3. Restaurants and cafés: by hand, through Photon only

11. **No restaurants or cafés in `geo`.** The importer stops selecting `amenity=restaurant` and
    `amenity=cafe` (rules version bumped), including the 500 m and town rules of ADR 011. A
    migration deletes the rows already loaded and everything in `geo` that hangs on them (images,
    aliases, cached names). This also frees most of the database: restaurants and cafés were about
    57 % of Austria's places (ADR 011).
12. **`geo.restaurant_profile` is dropped** (cuisines, venue type, meal types). `geo.place.kind`
    has only `attraction` (`transport_hub` and `other` stay reserved).
13. **Adding a restaurant or café** works in two ways only: **search through Photon** (through the
    backend, with the adapter's cache, budget and fallback, ADR 012), or **manual entry** (a name
    and a pin or typed coordinates, and the kind: restaurant or café). The result becomes a user
    place of kind `restaurant` or `cafe`. Photon gives the OSM key and value, so a Photon result
    gets its kind from `amenity=restaurant|cafe`; any other value asks the user to choose.
14. **Everything Photon cannot supply is removed:** cuisine and served meal types (on user places,
    in the API and in the app), "Cuisine not specified", the repeated-cuisine rule, the cuisine
    picker and meal picker of the add-restaurant screen, and the cuisine line of the place screen.
    The data model keeps only what is known: name, point, kind, address when Photon gave one.
15. **A restaurant is placed by the user.** The user picks the day and a start time, and the length
    defaults by kind and can be changed (*proposed:* restaurant 75 minutes, café 45 minutes;
    "default length" labelling as for every visit, brief section 7). There is no lunch or dinner
    label, no meal window and no meal type: the item reads "Restaurant · 1 h 15 min" or "Café ·
    45 min". The existing "Choose day and time" step (ADR 021 amendment) is the one way to place it,
    on empty and on generated plans alike.
16. **The item type `meal` stays internal** as the type of a restaurant or café stop (a stop with a
    place of kind `restaurant` or `cafe`); `meal_type` is dropped. Old stored items keep their
    times and show as restaurant or café stops.

### 4. The Phase 8 slot engine is retired

17. **`planner/restaurant_slots.py` and its API are removed:** the endpoint
    `POST /v1/itineraries/{id}/restaurant-suggestions`, the change-set action `add_restaurant` and
    its columns (migration `0008`), the app's suggested slots, reasons and detour display, and their
    tests. The Phase 7 change sets stay for adding and removing sights and for editing cities.
    A restaurant is added through the manual-item flow (item 15), which has its own preview-free
    save (`POST /v1/itineraries/{id}/days/{n}/items`).
18. **KPIs "Restaurant placement acceptance" and "Restaurant placement latency" are removed.**

### 5. History: past trips keep their days

19. **A past trip keeps its day-by-day record.** This amends ADR 006 decision 2. When a trip
    becomes past (by the user, or two days after its last day), the backend keeps:
    - the trip row (name, destination snapshot, dates, length);
    - **every item of the selected itinerary**, as snapshots: day number, order, start and length,
      kind, name, point, the `geo` identifier it came from, whether it was visited, and the user's
      note when notes exist (ADR 021, "not built"); restaurants and cafés the user added are in
      the record like any stop;
    - the cities, once each, as today (`app.trip_visit`), for the map of visited places.

    It still deletes the route geometry, transfers, unselected and superseded itineraries,
    itinerary versions, change sets and seeds. A past trip still cannot be re-planned or edited,
    except for visited marks, notes and its documents.
20. **Visited marks.** Every stop has a visited flag; it defaults to "planned" on a future trip and
    to "visited" at archiving, as ADR 006's "skipped visits" does, and the user can clear any
    stop. The map of visited places and its list use the flag.
21. **The past-trip screen shows the days** (a day list like the itinerary tab, without routes or
    travel times) as well as the map and the list by city. Documents on the phone (ADR 023) stay
    linked to a past trip's days and places.
22. **Size.** A trip's record is a few hundred small rows (no geometry), so history adds little to
    the 500 MB (ADR 005); the archive size line of ADR 006 stays and now counts the records.
23. **Past trips can be created directly.** A trip with dates entirely in the past starts as an
    ordinary trip the user can fill and then mark past, so a journey already taken can be recorded.
    The two-day rule applies as for any trip.

### 6. What comes next (each needs its own ADR before it is built)

24. **First: destinations outside the imported regions.** A trip can be created for any place
    found through Photon, with no imported data. Such a trip is empty by nature (no suggestions),
    with a map, days, documents and manually added places. Drafted as [ADR 027](027-destinations-outside-imported-regions.md) (proposed): how the destination is
    stored without a `geo` area, its cover photo, and what "Add a place" searches there.
25. **Second: export and import of a trip as a file** (trip, days, places, notes and, optionally,
    documents), because trips and documents live under an anonymous installation token and on the
    phone, so a reinstall loses the history (D5, ADR 023). Needs ADR 028. No accounts.
26. **Third: Optimize a hand-made trip** (ADR 029): the engine reorders the user's stops, across
    days if asked, for the least travel, with a preview.
27. **Then, in the owner's order:** saved ideas with no day, manual reordering and moving stops
    between days, notes, the trip summary and photos.

## Build order

1. **This change: documents only.** ADR 026, the amendments to ADR 006, 009, 011, 016, 019 and
   021, and the product brief, CLAUDE.md, KPIs, design, app plan, architecture and data model.
2. **Planner:** sights only, the midday gap, the day window, recalculation and validators,
   `CONFIG_VERSION`, golden files.
3. **Data (built):** importer rules version, the migration that deletes restaurants and cafés and drops
   `geo.restaurant_profile` and the cuisine and meal-type columns, gates 1 to 3 of ADR 009 removed.
4. **Retire the slot engine** (item 17) and move Add a restaurant to Photon and manual entry.
5. **History (built):** the archive keeps the day record (item 19), the past-trip screen shows days.
6. **App (built):** the new-trip buttons, labels, proposals and the Free time row.
7. Then destinations (ADR 027), then export (ADR 028), then Optimize (ADR 029).

Each step ends green: ruff, mypy, pytest, typecheck, lint and jest; the OpenAPI export and the
generated client are rebuilt whenever endpoints or models change.

## As built: step 2 (2026-11-14, awaiting acceptance)

Built and tested on synthetic fixtures; engine `planner-3.0.0`, planner configuration
`2026-11-14.3`, recalculation `recalc-2.0.0` (`RecalcConfig` `2026-11-14.1`).

- **The midday gap is idle time, not an item.** A `free_time` item has no place, so it cannot join
  the transfer chain (a transfer joins the next item), and `free_time` items stop a recalculation
  today. The next stop starts 90 minutes later than its transfer needs. One rule,
  `daylayout.gap_start`, decides where: before the first stop the traveller reaches at or after
  12:30 (not after 14:00), or before the stop that would push the gap's start past 14:00; never
  before the first stop of a day or after the last; a day that begins too late has none. Both the
  engine and recalculation use it, and both validators check that any idle stretch is the gap and
  that there is at most one a day. The app draws a "Free time" row for such an idle stretch (design
  §5; app step 6).
- **Day window 09:00 to 20:00; `free_minutes` 120 (Essentials) and 165 (Wider)**, so the visit budget
  stays 450 and 405 minutes, as before 2026-11-14 (not 60 and 90: with a 20:00 end and a 90-minute
  gap those would add sights). Measured on the fixtures: days end by about 18:00; day utilisation
  (visits and travel over the 660-minute window) 59 to 67 %, travel share 6 to 29 %; the KPI band is
  now 55 to 90 %.
- **Restaurants and cafés are fixed stops in a recalculation** (a stop the user added or one a plan
  made before this ADR holds): they keep their day and times, and the sights are laid out around
  them; the midday gap is skipped on a day that has such a stop between 11:30 and 15:00. A
  recalculation never creates a meal (`MEAL_CREATED` is a violation).
- **Slot engine retired with this step** because it was built on the removed meal windows and
  floating meals: `planner/restaurant_slots.py`, `POST /v1/itineraries/{id}/restaurant-suggestions`,
  the `add_restaurant` request action, the request fields `meal_type` and `after_item_id`, and the
  slot models are gone; the app's add-a-restaurant screen now always offers "Choose day and time".
  Stored change sets with the action `add_restaurant` still read until the data step (the response
  models keep the value); step 3 deleted them.
- **Reason and note templates of meals stay** (stored plans render them); `SIGHTS_ONLY` replaces
  `MEALS_FROM_MAP_DATA` in new plans. `PlanStats.meals` and `meal_minutes` stay (a plan with
  restaurants the user added counts them; generated plans have 0).
- **Not built yet after step 2:** see "As built: step 3" below for the data step; history and the
  app's Free-time row and buttons remain.

## As built: step 3, data (2026-11-14, awaiting acceptance)

Migration `0014_no_imported_restaurants`; importer rules `2026-11-14.1`. Tested on the synthetic
extract and on a database filled at revision `0013` (`tests/test_migration_0014.py`); **not run
against the production database**.

- **Importer.** `amenity=restaurant|cafe` is not a candidate (no longer in the `osmium` tag filter or
  `osm.lua`; `amenity`, `cuisine` and `diet:*` are no longer copied out of the extract), the 500 m and
  town rules and `importer/proximity.py` are gone, nothing builds a restaurant profile, and the
  report has no restaurant counts or cuisine share. **Gates 1 to 3 are retired and 4, 5 and 6 keep
  their numbers** (not renumbered: every earlier reference stays valid, ADR 009 amendment).
- **Migration.** Every itinerary stop that pointed at an imported restaurant becomes the same
  installation's own place (`app.user_place`, kind `restaurant`, or `cafe` for category `cafe`, name
  from the stop, point from the place) so no stored plan loses a stop, a name, a point or a time;
  then the imported restaurants and cafés and everything in `geo` that hangs on them (source rows,
  signals, profile, names, name lookups, photo lookups, name overrides) are deleted;
  `geo.restaurant_profile` is dropped and `geo.place.kind` no longer allows `restaurant`. The
  downgrade restores the structure only; the data comes back by importing the region again with an
  earlier importer.
- **Dropped columns:** `app.user_place.cuisines` and `meal_types`, `app.itinerary_item.meal_type`,
  `app.change_set.slot_meal` and `after_item_id` (and the `add_restaurant` action and its rows). The
  user-place kind `cafe` is new. `slot_day` stays (the one day an add-place preview was limited to).
- **API.** `cuisines`, `meal_types`, `diet_flags` and `venue_type` are gone from place search, place
  detail and user places; `kind=restaurant` is no longer a place-search filter; an item has no
  `meal_type` (the field is refused); `restaurant` on an item is `{venue_type}` read from the user's
  place; `GET /v1/restaurants/search` returns `your_places` and `external` only (no `results`), and a
  Photon result carries its `venue_type` and nothing else; adding a stop of type `meal` needs a user
  place of kind `restaurant` or `cafe`, with the default lengths 75 and 45 minutes when none is given.
- **App.** The add-a-restaurant screen has no cuisine or meal fields and no local-data results: it
  searches the user's saved places, then Photon, or takes a name, a kind (Restaurant or Café) and a
  pin; the day-and-time step suggests 13:00 but has no meal chips; stops read "Restaurant · 1 h
  15 min" or "Café · 45 min"; the day totals count "places to eat"; the add-place search asks for
  sights and towns only.
- **Leftovers to know about.** An itinerary version saved before the migration still holds meal
  stops whose place is the deleted imported one; restoring it brings the stop back with its stored
  name, point and times but no place behind it (it is not recalculated). Stored plans' meal reason
  texts still render. The restaurant counters in `PlanStats` stay (user-added restaurants count).

## As built: steps 5 and 6, history and app (2026-11-14, awaiting acceptance)

Migration `0015_trip_day_record`. Tested on the synthetic fixtures and on a database filled at
revision `0014` (`tests/test_migration_0015.py`); **not run against the production database**.

- **Where the record lives.** `app.trip_visit` (no new table) holds a row per base city (once each,
  no time) and per stop of the selected itinerary: kind `attraction`, `restaurant` or `cafe`
  (a town the user added keeps `city` and is not listed twice if it is a base city), `day_number`,
  `position`, `start_time` and `duration_minutes`. Free time is not a stop. The route geometry,
  transfers, other itineraries, versions and change sets are deleted as before. The API's
  `TripVisit` gained `position`, `start_time` and `duration_minutes`, and its `kind` the two eating
  kinds; `ArchiveInfo` gained `places_to_eat`; the size line counts the rows.
- **Visited flag.** `confirmed` is the flag: every stop is visited when archived and the user can
  clear any of them (restaurants and cafés too), as before. A "planned" mark on stops of a trip
  that has not ended is **not built** (nothing reads it until the trip is past). **Notes** are not
  built (ADR 021), so the record has no note column.
- **Older archives.** Rows archived before `0015` keep their map data and have no order or time (the
  plans were gone, nothing is invented); the Days tab then says no stops were kept by day.
- **Past trips created directly (decision 23).** The calendar never blocked past dates; what
  changed is the auto-archive rule: a trip **created after its last day** is not archived by
  itself, so there is time to fill it (the two-day rule still applies to every trip made before its
  last day). The user marks it past with "Mark as past" as for any trip.
- **App.** The past-trip screen has Map, **Days** and List tabs; the Days tab is the day record with
  each stop's kind, start and length. New trip: "Start with an empty trip" is the dark main button
  and "Suggest itineraries" the outlined second (labels, hints and the planning notice no longer
  mention places to eat). Day lists draw a "Free time" row for any idle stretch of 30 minutes or
  more after the transfer (the midday gap of a generated plan, or any gap in a hand-made plan).
  The comparison of the proposals drops its "Meals" row when neither plan has places to eat
  (renamed "Places to eat" when one does).
- **Not changed.** The Trip overview's per-day line and the restaurant figure still count the
  restaurants and cafés a plan holds (user-added ones, or those of plans made before this ADR).

## Alternatives

| Alternative | Why not |
|---|---|
| Keep the restaurant import for local search | The owner wants it gone, and restaurants are most of the `geo` data. Photon covers adding one. |
| Keep cuisine and meal types as optional manual fields | Photon cannot supply them; the owner asked to remove everything it cannot give. |
| Keep the Phase 8 slot engine for generated plans | A generated plan has no meals to slot into, and 99 % of trips are empty plans the engine cannot recalculate. About 670 lines and one change-set action for little use. |
| Pack the freed midday with more sights | Makes the days dense; the owner chose the gap. |
| Delete the generator | It is built and tested, and the owner still uses it sometimes; freezing costs nothing. |
| Keep a past trip as only the visited map (ADR 006 as built) | The owner wants the historical data: what was done on which day. |

## Consequences

- The backend loses about 670 lines of slot engine, one endpoint, one change-set action and
  the meal-layout code; the app loses cuisine, meal and slot UI. A migration removes data, so it is
  one-way: restoring restaurants means a new import.
- Adding a restaurant now depends on Photon (a public community server with a small daily budget,
  ADR 012) or on manual entry. If Photon is unavailable, manual entry still works.
- Search for a restaurant returns nothing from local data, and results carry no cuisine. A
  restaurant is a name, a point and a kind.
- Past trips cost more storage than the map-only archive but carry no geometry; this is bounded
  and small.
- Items 24 and 25 are decided in direction only. Until ADR 027 is built, a trip can still be
  created only for a destination in an imported region.
- Documents and amendments elsewhere (brief, CLAUDE.md, design, KPIs, plan, architecture, data
  model) say "as built" for the parts that change only when the corresponding build step is done.
  While steps 2 to 6 are open, the documents mark the affected text as "to change (ADR 026)".
