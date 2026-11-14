# ADR 026 — Trip manager and history first; generated plans are sights only; no restaurants in the data

- **Status:** **Proposed** on 2026-11-14, at the owner's request. This ADR is documentation only:
  nothing below is built yet. The code follows in the order of "Build order". The owner confirms
  or changes the numbers marked *proposed*.
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
    with a map, days, documents and manually added places. Needs ADR 027: how the destination is
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
3. **Data:** importer rules version, the migration that deletes restaurants and cafés and drops
   `geo.restaurant_profile` and the cuisine and meal-type columns, gates 1 to 3 of ADR 009 removed.
4. **Retire the slot engine** (item 17) and move Add a restaurant to Photon and manual entry.
5. **History:** the archive keeps the day record (item 19), the past-trip screen shows days.
6. **App:** the new-trip buttons, labels, proposals and overview figures.
7. Then destinations (ADR 027), then export (ADR 028), then Optimize (ADR 029).

Each step ends green: ruff, mypy, pytest, typecheck, lint and jest; the OpenAPI export and the
generated client are rebuilt whenever endpoints or models change.

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
