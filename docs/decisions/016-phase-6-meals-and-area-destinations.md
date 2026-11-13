# ADR 016 — Phase 6: meals and area destinations

- **Status:** **Proposed** on 2026-11-13. The code is built and tested
  (`services/api/src/detour_api/planner/`, migration `0006`); the owner confirms or changes the
  decisions below, especially the meal windows and the base-city rules, which have only been tried
  on synthetic fixtures.
- **Date:** 2026-11-13
- **Related:** [`003-scope-opening-hours-and-attractions.md`](003-scope-opening-hours-and-attractions.md),
  [`004-fossgis-valhalla-demo-server.md`](004-fossgis-valhalla-demo-server.md),
  [`013-phase-3-travel-time-service.md`](013-phase-3-travel-time-service.md),
  [`014-phase-4-planner-v1.md`](014-phase-4-planner-v1.md) (amended below),
  [`017-no-budgets-currencies-or-prices.md`](017-no-budgets-currencies-or-prices.md),
  [`../architecture.md`](../architecture.md) section 5, [`../app-plan.md`](../app-plan.md) Phase 6
  and D4

## Context

Phase 6 (build prompt 7) asks for meals in the itineraries and for area destinations: fixed meal
windows by meal type (breakfast, lunch, dinner, snack) and venue type; places to eat chosen by
proximity, cuisine variety and venue type from the imported data only, with unknown cuisine shown
as "Cuisine not specified" and no price, rating or opening hours; for an area, base cities and an
allocation of days to them using inter-city legs from the travel-time service (route requests for
legs beyond 150 km); Japan limited to single-city trips (D4); reason codes for every placement;
the validator checking meal windows and day length; golden tests updated. Out of scope: manually
added restaurants, prices, recalculation after edits, opening hours, reservations, ratings,
reviews, hotels and accommodation.

## Decision

### 1. Meal windows and meal lengths (`planner/config.py`)

| Meal | Window (starts at or after, ends by) | Length |
|---|---|---|
| Breakfast | 07:30–10:00 | café 30 min |
| Lunch | 12:00–14:30 | restaurant 60 min |
| Afternoon snack | 15:00–17:30 | café 30 min |
| Dinner | 18:30–21:00 | restaurant 90 min |

The length is keyed by meal type **and venue type** (`meal_minutes_by_venue`); another venue type
would take the meal type's default. Which meals a place serves is the import's fixed rule from its
venue type (`geo.restaurant_profile.meal_types`: restaurant → lunch, dinner; café → breakfast,
snack). These are planning choices, not facts about a place: opening hours are out of scope
(ADR 003), so a place may be closed at the planned time, as the plans say.

### 2. Which meals each profile plans

| | Essentials | Wider |
|---|---|---|
| Meals | lunch, dinner | lunch, afternoon snack, dinner |
| Day ends by | 20:30 | 21:00 |
| Time left unplanned per day | 60 min | 90 min |

**Breakfast is not placed by default**: the day starts at its first item at 09:00, after breakfast,
because accommodation is not modelled (product brief, section 9). The engine supports it (a test
plans it before the first visit). Meals are placed only on days with visits.

**Amends ADR 014 section 4:** the profiles' day ends move from 18:00/19:00 (visits only) to
20:30/21:00 (including dinner). The sequencer keeps, per day, each meal's default length plus
15 minutes to reach it, and the profile's unplanned time; what is left is for visits and their
transfers (Essentials 510 − 60 = 450 min, Wider 495 − 90 = 405 min). The unplanned time keeps day
utilisation, which now counts meals as the KPI defines it, inside 60–90 %.

### 3. Choosing a place to eat (`planner/meals.py`)

From the imported data only: active, **named** places of kind `restaurant` with a profile (an
unnamed place could not be found by the traveller). For each meal, between the item before it and
the item after it:

1. the place must list the meal type;
2. rings of 600 m, 1.5 km and 3 km (straight line) around those two items, nearest ring first;
3. places not yet used in the plan first; only if none lies within 3 km may a place used on an
   **earlier** day be chosen again (reason `PLACE_REPEATED`); never twice on one day;
4. within the first ring that has any: the lowest `detour in metres + 400 if one of its cuisines is
   already in the plan + 150 if the data states no cuisine`, ties by place id.

No suitable place within 3 km: the meal is not planned and the plan says how many
(`MEALS_NOT_PLANNED`). A place to eat is never invented.

### 4. Laying out a day with its meals

The day's visits are walked in the sequencer's order from 09:00 (later after an inter-city drive).
A pending meal is put in front of the next visit when its window has opened by the time that visit
would start, or when doing that visit first would leave no time to reach the meal before its
window closes. A meal starts at its window's start at the earliest; the wait is free time. If a
meal cannot end inside its window, or the day runs past its end, the day's lowest-value visit is
dropped and the day is laid out again (note `VISITS_REMOVED_TO_FIT`, which replaces
`VISITS_REMOVED_AFTER_ROUTING`). Meals that fall entirely before a late start (a long drive) are
skipped (`MEALS_SKIPPED_FOR_TRAVEL`).

### 5. Area destinations (`planner/areas.py`)

An area is an OSM administrative boundary (`geo.admin_area`). The engine plans it from **base
cities**: towns of the area where the traveller stays for a run of consecutive days.

1. **Towns:** gazetteer cities inside the area, the 60 most populous, without city sections and
   historical or abandoned places (GeoNames `PPLX`, `PPLH`, `PPLQ`, `PPLW`).
2. **Eligible:** at least 3 named sights within 5 km. **Score:** the sum of those sights' base
   values (notability and category points, as in ADR 014) plus population points
   (`population // 1,000`, at most 1,000; unknown counts 0). Integers, ties by city id.
3. **Main towns only:** of towns closer than 20 km to each other, only the most populous can be a
   base (a village next to a city is not a base).
4. **How many:** `ceil(days / 4)` for Essentials, `ceil(days / 3)` for Wider, at most 6, the number
   of days and the eligible towns. Fewer bases means fewer moves; more bases means more of the
   area: this is the "different allocation of days" of the diversity gate (architecture
   section 5.3).
5. **Which and where:** best score first, at least 20 km apart; each sight belongs to its nearest
   base, within the profile's radius.
6. **Days:** one each, the rest in proportion to the score (largest remainder).
7. **Order:** the best base first, then always the nearest remaining base by inter-city travel
   time from the travel-time service (cache only while planning).
8. **Inter-city legs:** the first day at each later base starts at 09:00 with the drive from the
   previous base city (`app.itinerary_day.arrival_*`); its visits start when it ends, and that day's
   visit budget is shorter by the drive. Once the plans exist the legs are asked of the travel
   service with the provider allowed, like every transfer; a leg beyond 150 km is one route request
   (ADR 004, ADR 013), so it comes back `routed` or stays a labelled estimate.

**Diversity gate (amends ADR 014 section 8):** two plans are distinct when their visit sets overlap
at most 60 % **or** their bases or days per base differ; the second must still have at least half
as many visits. The validator applies the same rule.

### 6. Japan: single-city trips only (D4)

An area whose country (or, without one, whose region's countries) is Japan is refused:
`422 area_single_city_only` when a trip is created or planned, and destination search marks such
areas `unavailable_reason: area_single_city_only` so the app greys them out. Cities in Japan are
planned as before. The rule is configuration (`single_city_countries`); public transport
(Phase 10) is the way to lift it.

### 7. Reason codes and notes (`planner/reasons.py`)

Meals: `BREAKFAST_WINDOW`, `LUNCH_WINDOW`, `SNACK_WINDOW`, `DINNER_WINDOW`, `VENUE_SUITS_MEAL`,
`ON_THE_WAY` (first ring) or `NEAREST_SUITABLE`, `NEW_CUISINE`, `CUISINE_NOT_SPECIFIED`,
`PLACE_REPEATED`. Plan notes: `BASE_CITY` (each base, its days and sights), `INTER_CITY_TRAVEL`
(each drive, its minutes and label), `DISTINCT_ALLOCATION`, `MEALS_NOT_PLANNED`,
`MEALS_SKIPPED_FOR_TRAVEL`, `VISITS_REMOVED_TO_FIT`, and the fixed `MEALS_FROM_MAP_DATA`
(venue type and cuisine only; no prices, ratings or opening hours), which replaces
`NO_MEALS_YET`. Issue `NO_BASE_CITIES`. The old codes stay in the template table so itineraries
written by `planner-1.0.0` still render.

### 8. Validator (amends ADR 014 section 9)

Added: each meal is at an imported place to eat with its name, point, venue type and cuisines; the
place serves that meal; the meal type is one of the profile's, at most once a day; a place at most
once a day, and again on a later day only with `PLACE_REPEATED`; the meal length follows the table;
**the meal starts and ends inside its window**; meals only on days with visits; every item ends by
the profile's day end and starts after the day's inter-city leg (**day length respected**);
each day's base is the destination city (city trip) or one of the area's towns; an inter-city leg
exactly when the base changes, from the previous base, checked against the travel source like any
transfer; statistics including meals and inter-city legs.

### 9. Data and API

- Migration `0006`: `app.itinerary_item.meal_type` also allows `snack`; `app.itinerary_day` gains
  `base_city_name` (snapshot) and `arrival_mode`, `arrival_seconds`, `arrival_meters`,
  `arrival_confidence` (all or none).
- Meal items are written like visits (`type = 'meal'`, `duration_source = 'category_default'`).
  Reads add `restaurant: {venue_type, cuisines}` to meal items, joined from
  `geo.restaurant_profile` (or the user place) by identifier at read time, never copied into `app`;
  and `base_city_name` and `arrival` (with the previous base's id and name) to days. Statistics add
  `meals`, `meal_minutes` and `intercity_legs`.
- `POST /v1/trips/{id}/itineraries/generate` plans areas; `422 area_not_supported` is gone.
- Versions: `planner-2.0.0`, configuration `2026-11-13.1+durations-2026-11-12.1`.

### 10. App

The create-trip form accepts areas (greyed out only when the backend says so). Meal rows show the
meal, the venue type and the cuisines or "Cuisine not specified"; day headers of a multi-base plan
name the base city and show the drive with its Routed/Estimated tag; the comparison has a Meals
row. No price, rating or opening hours anywhere.

## Measured (2026-11-13, Claude Code cloud container, synthetic fixtures, no routing provider)

| Trip | Engine | Visits E / W | Meals E / W | Day utilisation E / W | Travel share E / W | Jaccard | Days per base E / W |
|---|---:|---:|---:|---:|---:|---:|---|
| City, 3 days, 180 sights | 57 ms | 26 / 26 | 6 / 9 | 86.2 / 89.2 % | 12.7 / 18.7 % | 0.53 | 3 / 3 |
| City, 7 days | 154 ms | 61 / 58 | 14 / 21 | 85.7 / 88.8 % | 11.2 / 17.4 % | 0.59 | 7 / 7 |
| City, 14 days | 346 ms | 134 / 113 | 28 / 41 | 85.2 / 86.8 % | 12.5 / 16.4 % | 0.51 | 14 / 14 |
| Town, 1 day, 8 sights | 2 ms | 4 / 7 | 2 / 3 | 85.4 / 64.1 % | 13.8 / 15.5 % | 0.38 | 1 / 1 |
| Town, 3 days, 8 sights | 3 ms | 6 | 6 | 34.1 % | 12.4 % | one plan | 3 |
| Area, 3 days, 6 towns | 54 ms | 27 / 25 | 6 / 9 | 85.6 / 86.1 % | 12.9 / 17.5 % | 0.53 | 3 / 3 |
| Area, 7 days | 116 ms | 60 / 52 | 14 / 21 | 85.7 / 85.4 % | 16.0 / 22.2 % | 0.42 | 4, 3 / 3, 2, 2 |
| Area, 14 days | 209 ms | 118 / 99 | 27 / 38 | 85.7 / 82.9 % | 20.0 / 23.7 % | 0.58 | 5, 4, 3, 2 / same |

Every plan passed the validator. Day utilisation is inside 60–90 % except the 8-sight town over 3
days (it runs out of sights), and travel share is under 25 % (Essentials) everywhere. The 3-day
8-sight town drops two visits: a 4-hour theme park cannot share a day with lunch.

## Alternatives

| Alternative | Why not chosen |
|---|---|
| Meals as time-windowed nodes inside the sequencer | A larger change to the S5 heuristic and its golden behaviour; reserving time and laying meals out afterwards keeps the sequencer as measured, and the validator checks the result either way |
| Choose places to eat by routed travel time | A provider call per candidate place; straight-line detour is deterministic and free, and the chosen legs are routed afterwards like any transfer |
| Exclude places used earlier in the plan always | Small towns would lose their meals after the first day |
| Base cities from accommodation | Accommodation is not modelled (product brief section 9; scope guard) |
| One base per city of the area above a population threshold | Ignores where the sights are; a large suburb could win |
| Allow areas in Japan with driving legs | D4: rail is the main inter-city transport there; plans would be misleading |

## Consequences and open items (owner)

1. **Confirm the meal windows and lengths** (section 1) and the profiles' meals (section 2),
   including that breakfast is not planned.
2. **Confirm the base-city rules** (section 5) on real areas once Austria is imported: the 20 km
   separation, the 3-sight minimum and the population weight are untested on real data.
3. Area trips load every sight and place to eat inside the boundary; a very large area (a whole
   country-level boundary) has not been measured.
4. The first plans of an area have estimated inter-city legs until the cache holds them; legs over
   150 km cost one route request each.
5. Meals are not recalculated after hand edits (Phase 7), and a restaurant cannot yet be added by
   hand (Phase 8).
