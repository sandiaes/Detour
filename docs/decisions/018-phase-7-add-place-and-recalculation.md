# ADR 018 — Phase 7: adding a place, recalculation and itinerary versions

- **Status:** **Proposed** on 2026-11-13. The code is built and tested
  (`services/api/src/detour_api/planner/recalc.py`, `diff.py`, `revision_validator.py`,
  `change_service.py`; `repo/changes.py`, `repo/plan_state.py`; migration `0007`; the app's
  add-place and preview screens). The owner confirms or changes the decisions below, especially
  the stability costs and the 20 km "new base" distance, which have only been tried on synthetic
  fixtures.
- **Date:** 2026-11-13
- **Related:** [`014-phase-4-planner-v1.md`](014-phase-4-planner-v1.md),
  [`016-phase-6-meals-and-area-destinations.md`](016-phase-6-meals-and-area-destinations.md),
  [`017-no-budgets-currencies-or-prices.md`](017-no-budgets-currencies-or-prices.md),
  [`../architecture.md`](../architecture.md) section 5.4, [`../app-plan.md`](../app-plan.md)
  Phase 7, [`../kpis.md`](../kpis.md) section 2

## Context

Phase 7 (build prompt 8) asks that the user can add a city or place that was not in a proposal,
by search or by a pin; that it becomes a mandatory visit; that the engine recalculates with
minimal disruption (a stability cost, locked items never moved or removed, day length and meal
windows kept, meals moving with the day and staying at imported places to eat, a distant addition
re-allocating days to a new base city with ADR 016's inter-city legs); that the app previews the
change as a diff and nothing changes until the user accepts; that accepting creates a new version
and keeps the previous one, and that adding then removing the place restores the previous plan;
and that an infeasible change says exactly which constraints conflict. Out of scope: adding
restaurants (Phase 8), minimum or preferred nights, "trip may grow" options, per-city
protections, prices (ADR 017), any LLM, booking.

## Decision

### 1. Repair, not re-plan

A recalculation changes the plan the user has; it does not plan the trip again. Planning again
with the S5 sequencer and a stability term would have touched every day and changed the measured
generation path and its golden files. The repair touches the day that receives the place and, at
most, the days that take visits it pushes out (or, for a distant place, the re-allocated day and
the day after it). Days that do not change are copied exactly, and the validator checks that.

### 2. Item states

| State | Rule |
|---|---|
| `locked` | Keeps its day, its start and its end: a fixed block the day is laid out around. Never removed; a locked visit cannot be removed by the user either ("unlock it first") |
| Added by the user (`origin = user`) | **Mandatory**: never left out. May change position in its day. The added place gets the reason `ADDED_BY_YOU` |
| A meal the user added | Kept at its day and time (Phase 8 decides more) |
| Engine visit | May be moved to another day or left out, at a stability cost |
| Engine meal | Laid out again in its window on a changed day; keeps its place to eat when that place is still within the 3 km ring, else the ADR 016 choice |

### 3. Stability cost (`RecalcConfig`)

All integers, in the engine's value units (a 50-point sight is worth 500; a minute of travel costs
the profile's travel weight, 10 for Essentials, 4 for Wider):

    travel weight x added travel minutes (transfers and inter-city drives)
    + 300 per existing visit that changes day
    + its value + 200 per existing visit left out
    + 5 per existing item whose start time changes

Ties go to the earlier day, then the earlier position.

### 4. Adding a place near the plan

If the place is within **20 km** (straight line, ADR 016's base separation) of a base city of the
plan, every day at such a base is tried: the place is inserted at the four cheapest positions (by
added travel); if the day no longer fits, its lowest-value engine visits are taken out one at a
time; each one taken out is moved to another day at the same bases if it fits there without
pushing anything out, else it is left out. The option with the lowest stability cost wins.

### 5. Adding a place far away

Farther than 20 km from every base: the new base is the **nearest gazetteer town within 25 km** of
the place (GeoNames cities, without city sections and historical places, as in ADR 016). One day
is re-allocated to it: the first or last day of a base's run, from a base that has **at least two
days**, so runs stay consecutive and no city disappears. The new day starts with the drive from
the previous base; the next day starts with the drive from the new base (ADR 016 legs, routed or
labelled). It holds the place plus the sights the heuristic sequencer picks within the profile's
radius of the new base. The old day's visits move to the other days of their base if they fit,
else they are left out. Days with locked items or items the user added are not re-allocated.
Exactly one day: there are no minimum or preferred nights (scope guard).

### 6. Removing a place

The visit is taken out and its day is laid out again (its meals follow). The freed time is not
refilled: a removal should not bring in something the user did not ask for. **Undo through
versioning:** if the visit is the place the latest accepted change set added, and the itinerary
has not changed since, the removal restores the stored previous version exactly (items, their
ids, transfers, summary, and the engine, configuration and data versions). The preview says so
(`PLAN_RESTORED`).

### 7. Travel times

Choosing uses cached times and labelled estimates only. Then the changed days' legs are asked of
the travel source with the provider allowed (ADR 004, within `DETOUR_RECALC_PROVIDER_MAX_SECONDS`,
2 s, so the preview stays inside the 3 s KPI), the days are laid out again, and a day that no
longer fits loses its lowest-value engine visit (shown in the diff). A mandatory item never;
then the change is refused (`ROUTED_TIMES_TOO_LONG`). Unchanged days keep their stored transfers.

### 8. When it cannot be done

`422 recalculation_impossible` with one issue per conflict, rendered through fixed templates:
`ALREADY_IN_PLAN`, `ADDITION_LONGER_THAN_DAY`, `DAY_FULL_OF_FIXED_ITEMS` (names the items that
cannot move, per day), `DAY_TOO_SHORT_FOR_ADDITION`, `NO_TOWN_NEAR_ADDITION`, `NO_DAY_FOR_NEW_BASE`
(names the bases that have one day each), `DAY_HAS_FIXED_ITEMS`, `DRIVE_LEAVES_NO_TIME`,
`SINGLE_CITY_ONLY` (a far place on a trip in Japan, D4), `UNSCHEDULED_ITEMS` (free time or
untimed items from hand edits), `ITEM_LOCKED`, `NOT_A_VISIT`,
`ROUTED_TIMES_TOO_LONG`. Nothing is left out silently: every item that leaves the plan is in the
diff's `removed` list and in a `VISITS_DROPPED` note, and the app shows it under a warning.

### 9. Validation

An independent validator (`planner/revision_validator.py`) checks every recalculated plan before
it can be previewed: unchanged days identical; **locked items on the same day at the same times**;
every user-added item present; the added place present once with `ADDED_BY_YOU`, a removed one
absent; carried items unchanged except time; new visits are given sights with default lengths;
engine meals at given places to eat, of the profile's types, in their windows, with the table's
lengths, once a day; non-fixed items inside the day after its drive and by the profile's day end;
no overlaps; every transfer and drive exactly what the travel source returned; known bases with a
drive exactly when the base changes; templates for every reason and note; statistics. A violation
is a bug: `500 plan_invalid`, never a preview.

### 10. Change sets and versions (migration `0007`)

- `POST /v1/itineraries/{id}/change-sets` previews `add_place` (an imported attraction by
  `place_id`, or a user place of kind `city` or `location` by `user_place_id` with
  `duration_minutes`) or `remove_place` (`item_id`). The change set is stored (`app.change_set`)
  with the proposal (the plan rows to write), the diff and the change's notes. **Nothing in the
  itinerary changes.** One open preview per itinerary: a newer one expires the older.
- `POST /v1/change-sets/{id}/apply` keeps the current version in `app.itinerary_version`, writes
  the stored proposal **exactly as previewed** (the same rows), and increments the version. If the
  itinerary changed since the preview (any hand edit, a lock), the change set expires: `409
  change_set_stale`. `POST /v1/change-sets/{id}/discard` closes it. `GET /v1/change-sets/{id}` and
  `GET /v1/itineraries/{id}/versions` read them.
- **Every replaced version is kept**, whether a change set or a hand edit of an item replaced it,
  up to 30 per itinerary (the oldest go first). A decided change set keeps its diff; its proposal
  is cleared.
- Stored states hold the items' own snapshots (name, point) only; venue types and cuisines stay
  in `geo` and are joined at read time (data model section 1).
- A recalculated itinerary records `engine_version` `planner-2.0.0+recalc-1.0.0` and
  `config_version` `<planner config>+recalc-2026-11-13.1`; the generation's engine and its golden
  files are unchanged.
- A town chosen from destination search is saved as a user place with `search_provider:
  geonames` and its gazetteer id (GeoNames is an existing source, ADR 012; no new provider).

### 11. App

"Add a place" on a planned itinerary: search sights near the trip (local), towns (gazetteer) and,
when nothing matches, a wider search (Photon through the backend); or drop a pin on the map and
name it. A sight takes its typical length unless the user picks one; a town or pin needs one (2 h
for a town, 1 h otherwise, by default). The preview shows a one-line summary, the travel change,
what is added, **what is left out (under a warning)**, what moves to another day, base city
changes, new times and the estimated travel times, with Accept and Discard. Each visit has Lock or
Unlock and Remove (disabled while locked). No price, rating or opening hours anywhere.

## Measured (2026-11-13, Claude Code cloud container, synthetic fixtures, no routing provider)

Ten additions of unplanned sights to each plan, engine only:

| Trip | Profile | Mean / max | Days changed (max) | Visits moved to another day (max) |
|---|---|---:|---:|---:|
| City, 3 days | Essentials / Wider | 12 / 14 ms, 13 / 17 ms | 1 | 0 |
| City, 7 days | Essentials / Wider | 79 / 108 ms, 92 / 117 ms | 1 | 0 |
| City, 14 days | Essentials / Wider | 488 / 690 ms, 108 / 152 ms | 1 | 0 |
| Area, 7 days | Essentials / Wider | 16 / 22 ms, 10 / 12 ms | 1 | 0 |
| Area, 14 days | Essentials / Wider | 32 / 41 ms, 30 / 47 ms | 1 | 0 |

Through the API with the database (2- and 3-day trips): 20 to 200 ms per preview. Against the KPIs:
locked items moved 0 (tests); disruption on add 0 % of visits changing day on these fixtures
(target at most 20 %); diff fidelity by construction and tested (the applied rows are the
previewed rows; the diff recomputed from the stored versions equals the preview); recalculation
latency far under 3 s without the provider (the provider share is capped at 2 s).

**Not measured:** real imported data; the provider share; recalculation acceptance (a log KPI:
`change_previewed`, `change_applied`, `change_discarded`).

## Alternatives

| Alternative | Why not chosen |
|---|---|
| Re-solve the whole plan with the sequencer and a per-day stability bonus | Changes the S5 heuristic and every golden file; tends to touch every day; harder to explain in a diff |
| Store each version as a new itinerary row (`status = superseded`) | Counts against the 5-itineraries limit and the selection rules; mixes history with proposals |
| Undo by recalculating without the place | Not guaranteed to give back the same plan; the brief asks that it does |
| Let locked items keep their day but not their time | "Never moved" would then mean less than the user expects; fixed times are easy to check (KPI 0) |
| A new base city for any place beyond the profile radius (5 or 15 km) | Day trips of 20 km are usual from a city; 20 km matches ADR 016's base separation |
| Re-allocate more than one day to a far place | Needs nights per city, which is excluded (build prompts section 4) |
| Refill the time a removal frees | Brings in places the user did not ask for; the previous version is restored when the removal undoes an addition |

## Consequences and open items (owner)

1. **Confirm the stability costs** (section 3) and the 20 km / 25 km distances (sections 4 and 5)
   on real data once Austria is imported.
2. Untimed items and free time (hand edits only; the app cannot make them) block recalculation of
   their itinerary with `UNSCHEDULED_ITEMS`.
3. A user place saved for a preview stays in the user's places when the preview is discarded.
4. Phase 8 (add a restaurant) builds on the same change sets.
5. Japan stays single-city (D4, ADR 016): a far addition to a trip in Japan is refused with
   `SINGLE_CITY_ONLY` instead of getting a new base city and a driving leg.

## Addendum (2026-11-13, ADR 021 step 4)

- `add_place` takes an optional `day`: the recalculation then tries only that day
  (`recalc.add_place(..., only_day=...)`), and refuses with `DAY_NOT_NEAR_ADDITION` when that day
  cannot take the place. Without `day` the behaviour is unchanged.
- `POST /v1/itineraries/{id}/place-suggestions` runs the recalculation once per day without the
  routing provider and returns up to three days ranked by its stability cost (now on `Revision`),
  each with its time, travel and diff. Nothing is stored. See
  [ADR 021](021-trip-manager-redesign.md), decisions 19 to 24.
