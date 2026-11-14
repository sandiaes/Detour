# ADR 019 — Phase 8: adding a restaurant and placing it in the best slot

- **Status:** **Proposed** on 2026-11-13. The code is built and tested
  (`services/api/src/detour_api/planner/restaurant_slots.py`, `routers/restaurants.py`,
  `repo/changes.py`, migration `0008`, the app's add-a-restaurant screen); the owner confirms or
  changes the decisions below, especially the slot costs of section 3, which have only been tried
  on synthetic fixtures.
- **Date:** 2026-11-13
- **Related:** [`002-api-strategy.md`](002-api-strategy.md),
  [`003-scope-opening-hours-and-attractions.md`](003-scope-opening-hours-and-attractions.md),
  [`016-phase-6-meals-and-area-destinations.md`](016-phase-6-meals-and-area-destinations.md),
  [`017-no-budgets-currencies-or-prices.md`](017-no-budgets-currencies-or-prices.md),
  [`018-phase-7-add-place-and-recalculation.md`](018-phase-7-add-place-and-recalculation.md),
  [`../architecture.md`](../architecture.md) section 5.4, [`../app-plan.md`](../app-plan.md)
  Phase 8, [`../api-evaluation.md`](../api-evaluation.md) section 2.1

## Context

Phase 8 (build prompt 9) asks that the user can add a restaurant (search the local data first, then
Photon through the backend, then manual entry with a name and a map pin or typed coordinates, with
optional cuisines and served meals that otherwise stay unknown and shown as such) and that the app
place it in the best slot: every day and meal slot scored by location, neighbouring activities,
meal type and venue type, meal window (ADR 016) and travel impact; up to three suggestions with
reasons, the estimated detour and which items move; the meal inside its window and the day inside
its hours, both checked by the validator. Out of scope: opening hours (ADR 003), reservations,
prices, budgets, price bands and currencies (ADR 017), ratings and reviews, weather, accounts, any
LLM.

## Decision

### 1. Adding: local data, then Photon, then manual entry

`GET /v1/restaurants/search?q=` searches in this order and stops at the first source with an
answer:

1. **Imported places to eat** (`geo.place` of kind `restaurant` with its profile), by name, near a
   point if given. Each result carries cuisines (null = the data states none, shown as "Cuisine not
   specified"), venue type and meal types.
2. **The user's own saved restaurants** (`app.user_place`, kind `restaurant`) whose name matches.
3. **Photon**, only with `include_external=true` and only when 1 and 2 are empty, through the
   existing adapter (User-Agent, timeout, week-long cache, daily budget counter, pause after a
   failure). The request adds Photon's `osm_tag` filter (`amenity:restaurant`, `amenity:cafe`) and
   the backend **filters the answer again** (`osm_key = amenity`, value `restaurant` or `cafe`),
   because the filter is documented as deprecated and may be ignored. A result carries a venue type
   and meal types from the same fixed rule as imported places (restaurant: lunch, dinner; café:
   breakfast, snack: `importer/derive.py`), and **no cuisine**: Photon's answer carries none that
   this adapter reads, so it stays unknown unless the user gives one.
4. **Manual entry** is a user place (`POST /v1/user-places`, kind `restaurant`) with a name,
   `lat` and `lon` (tapped on the map or typed), optional cuisines and optional meal types. Without
   cuisines or meal types they are stored as null and shown as "Cuisine not specified" and "Meals
   not specified"; nothing is guessed. A Photon result the user wants is saved the same way, with
   `search_provider = photon` and its reference.

**Photon terms, re-read 2026-11-13** (<https://photon.komoot.io/>, <https://github.com/komoot/photon>,
`docs/api-v1.md`): unchanged from the 2026-11-12 reading in `api-evaluation.md` section 2.1: "You are
welcome to use the API for your project as long as the number of requests stay in a reasonable
limit. Extensive usage will be throttled or completely banned. We do not give guarantees for
availability and reserve the right to implement changes without notice." No new number, no card, no
key. The API reference documents `q`, `limit`, `lang`, `lat`/`lon`, `layer`, `countrycode`, the
tag filter `osm_tag` (marked deprecated in favour of category filters, whose categories depend on
the installation) and `extra` tags in results. The adapter uses `osm_tag` only to narrow results,
never relies on it, and does not read `extra`. Limits kept: 300 calls a day (`photon_daily_budget`),
results cached a week, a 60 s pause after a failure and 300 s after a 429. **No new provider.** A
live call from the build environment was not made: tests use a recorded-style stub, as before
(CLAUDE.md: no public community server from tests).

### 2. A restaurant is a meal the user adds

The restaurant becomes an `itinerary_item` of type `meal` with `origin = user` (ADR 018 already
defines it: "kept at its day and time"), at a day, meal type and time the layout finds. Its length
follows the table (ADR 016): by meal type and venue type, the meal type's default for a place of
the user's own (no venue type). It carries `restaurant: {venue_type, cuisines}` read at read time.
Placing is a **change set** (action `add_restaurant`, migration `0008`), so the preview with a diff,
apply, discard, expiry, versions and the independent validator are those of ADR 018. A restaurant
already in the plan is refused (`ALREADY_IN_PLAN`); a meal the user added or locked keeps its slot
(`MEAL_SLOT_TAKEN`); a day with no visits has nothing to place a meal between
(`DAY_HAS_NO_VISITS`).

To find the time, the new meal is first a **floating** entry in the day's sequence
(`Entry.floating`, never stored): `recalc._Work.lay_out` starts it when its meal window opens or
when the traveller arrives, whichever is later, and **refuses the layout** if it would end after
its window or the profile's day end. The layout's result is stored as a fixed meal. Visits never
change day and **no visit is left out** to make room: a slot that would need that is not offered
(`MEAL_DOES_NOT_FIT` when asked for explicitly). If routed times later make the day too long, the
rule of ADR 018 section 7 applies (the lowest-value engine visit may go, shown in the diff).

### 3. Scoring the slots (`planner/restaurant_slots.py`, `RecalcConfig`)

A slot is a day with visits and a meal type the place serves (all four when its meal types are
unknown). In each slot the meal goes between two neighbouring stops (visits, or meals the user
fixed); of the positions that can plausibly fit in time (judged from the plan's current times) the
four with the least added travel are laid out in full and the cheapest wins. The engine meal of the
slot's type, if any, is replaced. Costs are integers (lower is better; planning choices, not facts):

    travel weight (10 Essentials, 4 Wider) x added travel minutes of the day, never below zero
    + straight-line detour in metres // 20                         (location, neighbouring stops)
    + 5 per other item that starts at another time + 1 per minute of shift
    + 2 per minute of waiting for the meal window to open
    + 200 if it replaces a meal the plan has
    + 150 if one of its cuisines is in a meal of this day or the days either side
    + 100 if the meals the place serves are unknown

Ties go to the earlier day, then the earlier start, then the meal order. One candidate per
(day, meal type); the cheapest **three** are returned. The travel term is floored at zero because
dropping the replaced meal's own legs would otherwise reward a restaurant far from the stops around
it (seen on the synthetic fixtures before the floor). Travel times while scoring come from the cache
and labelled estimates only; the preview that follows asks the provider for the changed day's legs
(ADR 018 section 7), so a suggestion's detour is labelled `estimated` unless every leg next to the
meal was routed. No opening hours, so a restaurant may be closed at the suggested time, as for every
planned meal.

Each suggestion carries its day, meal type, start and end, the stops before and after, the added
travel minutes and label, the straight-line detour, the meal it replaces, **which other items start
at another time**, its score and its **reasons**: codes from a fixed table (`SLOT_TEMPLATES` in
`planner/reasons.py`) rendered with the numbers the scoring computed: the window and the slot's
times, why the meal type is served (venue type, the user, or unknown), distance to the stops before
and after, the end of the day, the travel change, replacing or filling an empty slot, waiting, what
moves, and the cuisine (new, repeated, or not specified). There is no generated text.

### 4. Validator

`revision_validator.validate_revision(..., added_meal=Dining)` adds, for the new meal: the place,
name, point, venue type and cuisines as given; the place serves the meal (when known); the table's
length; **the meal starts and ends inside its window; the meal starts after the day's start and
ends by the day's end**; it is not floating or locked; it is the only meal of its type that day and
the place is used once that day. Carried items and unchanged days are checked as in ADR 018. A
violation is a bug: `500 plan_invalid`, never a preview.

### 5. API and data

| Endpoint | Purpose |
|---|---|
| `GET /v1/restaurants/search` | The order of section 1. Parameters `q`, `region`, `lat`, `lon`, `radius_m`, `limit`, `include_external`, `lang`. Result: `results` (imported), `your_places`, `external` (state, and restaurants and cafés with venue type and meal types) |
| `POST /v1/itineraries/{id}/restaurant-suggestions` | Body: `place_id` or `user_place_id`, optionally `day` and `meal_type` to place it manually in a chosen slot. Up to three suggestions, or none with `issues` saying why. Nothing is stored. `422 recalculation_impossible` with `issues` (already in the plan, does not serve that meal, a locked slot) |
| `POST /v1/itineraries/{id}/change-sets` | New action `add_restaurant` with `place_id` or `user_place_id`, `day`, `meal_type` and `after_item_id` (the stop the meal follows; null: first), exactly as a suggestion gives them |

Migration `0008`: `app.change_set.action` allows `add_restaurant`; new columns `slot_day`,
`slot_meal`, `after_item_id` (constraints keep them for that action only). Versions:
`RECALC_VERSION` `recalc-1.1.0`, `RecalcConfig.version` `2026-11-13.2` (a recalculated itinerary
records `planner-2.0.0+recalc-1.1.0` and `<config>+recalc-2026-11-13.2`); the generation engine and
its golden files are unchanged. New item reason codes `MEAL_SERVED_PER_YOU`,
`MEAL_TYPE_NOT_SPECIFIED`, `CUISINE_NOT_SPECIFIED_BY_YOU`; notes `RESTAURANT_ADDED`,
`MEAL_REPLACED`; issues `RESTAURANT_DOES_NOT_SERVE_MEAL`, `DAY_HAS_NO_VISITS`, `MEAL_SLOT_TAKEN`,
`SLOT_NOT_FOUND`, `MEAL_DOES_NOT_FIT`, `NO_SLOT_FITS`.

### 6. App

"Add a restaurant" on a planned plan: search (the map data first; "Search more widely" asks Photon
through the server when nothing matches; "Enter by hand" always works, including when the outside
search is unavailable or its budget is used up); a hand-entered or externally found restaurant has
a name, optional cuisines, optional meals (none chosen: "not specified") and a place by tapping
the map or typing latitude and longitude. "Find the best day and meal" shows up to three cards with
day, meal and time, the neighbouring stops, the estimated detour, which items move, what it
replaces and the reasons; choosing one opens the Phase 7 preview (diff, Accept, Discard). A
restaurant entered by hand is saved as a user place once, and updated rather than saved again if
the user changes it and asks again. No price, rating, opening hours or reservation anywhere.

## Measured (2026-11-13, Claude Code cloud container, synthetic fixtures, no routing provider)

Suggestions for ten restaurants placed near each plan (engine only, all slots scored):

| Trip | Profile | Slots tried | Mean / max |
|---|---|---:|---:|
| City, 3 days | Essentials / Wider | 9 | 12 / 21 ms, 11 / 16 ms |
| City, 7 days | Essentials / Wider | 21 | 32 / 48 ms, 44 / 56 ms |
| City, 14 days | Essentials / Wider | 42 | 110 / 154 ms, 76 / 117 ms |

Every one of the ten returned three suggestions on every plan, and each was then placed and passed
the validator. Through the API with the database (a 3-day plan, provider off): a suggestion request
took about 35 ms (20 loading, 14 scoring) and a preview about 120 ms (mostly loading the data around
the plan). **Not measured:** real imported data; the routing provider's share of a
preview; whether users accept the first suggestion (a log KPI: `restaurant_slots_suggested`,
`change_previewed`, `change_applied`).

## Alternatives

| Alternative | Why not chosen |
|---|---|
| Re-plan the day's meals with the sequencer and a pinned restaurant | Changes the S5 heuristic and the golden files; the repair of ADR 018 already lays a day out around fixed items |
| Let a restaurant push a visit out when no slot fits | The user asked for a restaurant, not for a lost sight; a slot that needs that is simply not offered, and the reason is stated |
| Score by routed times | A provider call per slot (up to 56 slots on 14 days); the preview routes the chosen day |
| Reward the travel a replaced meal no longer needs | Favours restaurants far from the stops around them |
| Photon without the post-filter | The tag filter is deprecated and may be ignored; the backend would pass on places that are not restaurants |
| Read Photon's `extra` for cuisine | Not verified against a live answer, and a cuisine must never be invented; unknown stays unknown |
| A separate "move this meal" action | Not asked for (CLAUDE.md rule 3); the slot filters (`day`, `meal_type`) of the suggestions let the user pick a day and meal by hand |

## Consequences and open items (owner)

1. **Confirm the slot costs** of section 3 (200 to replace a meal, 150 for a repeated cuisine, 100
   for unknown meal types, 2 per minute of waiting, the detour divisor) on a real imported city:
   they have only been tried on synthetic fixtures.
2. **Removing a restaurant is not built**: `remove_place` still refuses meals (`NOT_A_VISIT`).
   Discarding the preview and the stored versions are the undo for now. A "remove meal" action
   needs the owner's approval (CLAUDE.md rule 3).
3. A restaurant is offered only on days with visits and inside the four meal windows of ADR 016;
   a breakfast before the first visit pushes the day by its length and the travel.
4. Photon results have no cuisine; a cuisine typed by the user is the user's, not the map data's.
5. A restaurant the user saved stays among their places when its preview is discarded (as for
   places, ADR 018); at most 500 places per installation.
6. The Photon public instance has no availability guarantee: manual entry is always possible, and
   self-hosting Photon with a country extract is the named fallback (`api-evaluation.md`).

## Amendment of 2026-11-14 (ADR 026): slot engine retired (proposed, not built)

[ADR 026](026-trip-manager-first.md) retires the slot engine: `planner/restaurant_slots.py`, the
endpoint `POST /v1/itineraries/{id}/restaurant-suggestions`, the change-set action `add_restaurant`,
and the app's suggested slots with reasons and detours. A restaurant is added by **searching
Photon** (the imported restaurants and the local-data search are gone: migration `0014`) **or by manual entry**, with no
cuisine and no served meals, and the user chooses its day and time ("Choose day and time"). The
Photon adapter, the manual pin or typed coordinates, and the rule that a restaurant the user added
is never left out by a recalculation stay. Until ADR 026 step 4 is built, this ADR describes the
app as it is.
