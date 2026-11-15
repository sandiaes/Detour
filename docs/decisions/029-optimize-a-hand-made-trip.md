# ADR 029 — Optimize a hand-made trip

- **Status:** **Accepted** on 2026-11-15 (the owner accepted all five points of the revision as recommended; building). Was **Proposed** on 2026-11-14, at the owner's request, after the owner answered the
  design questions (see "Owner decisions"). **Revised on 2026-11-15** now that ADRs 027 and 028 are
  built (see "Revision of 2026-11-15"): it awaits the owner's acceptance of the five points there.
  Documentation only: nothing is built. It is the **third** manager feature, after destinations
  outside the imported regions (ADR 027) and trip export (ADR 028).
- **Built:** 2026-11-15 (see "As built"); awaiting acceptance of the build.
- **Date:** 2026-11-14
- **Related:** [`026-trip-manager-first.md`](026-trip-manager-first.md),
  [`014-phase-4-planner-v1.md`](014-phase-4-planner-v1.md),
  [`018-phase-7-add-place-and-recalculation.md`](018-phase-7-add-place-and-recalculation.md),
  [`013-phase-3-travel-time-service.md`](013-phase-3-travel-time-service.md),
  [`004-fossgis-valhalla-demo-server.md`](004-fossgis-valhalla-demo-server.md),
  [`023-trip-documents-on-the-device.md`](023-trip-documents-on-the-device.md),
  [`024-multi-city-trips.md`](024-multi-city-trips.md),
  [`../architecture.md`](../architecture.md) section 5

## Context

Most trips are now made by hand (ADR 026). The owner wants an **Optimize** option on a hand-made
trip: the planning engine checks every attraction and restaurant the user put in the plan, on all
days, and proposes a new order of the visits to shorten the distances. An attraction may move from
one day to another. This is a new feature (CLAUDE.md rule 3). It adds no provider and no language
model: it reuses the deterministic sequencer, the travel-time service (ADR 013) and the change-set
pipeline (ADR 018).

## Decision

### 1. What it is

1. **Optimize** is an action on a trip's plan, offered for manual plans and also for planned ones.
   It proposes a new order of the stops; the user reviews a diff and a saving, then applies or
   discards, as with any change set. Nothing changes until the user applies it.
2. **It is a change set** with the action `optimize` (ADR 018's pipeline: preview with a diff,
   apply, discard, itinerary versions). Applying makes a new version, so the previous order can be
   restored exactly with the same undo that removing an addition uses. Whether that undo needs
   widening beyond "the latest addition" is checked when it is built.
3. **Two scopes**, chosen by the user in a sheet before the preview:
   - **Reorder within each day:** no stop changes day; each day is reordered for the least travel.
   - **Reorder across all days:** attractions may also change day, and each day is reordered.
4. **It never loses or adds a stop.** Every item with a place stays in the plan; free-time items
   stay in their day. It changes order, day (across-days scope) and start times only.

### 2. Rules (owner decisions of 2026-11-14)

5. **Attractions** are free to move: within a day in both scopes, between days in the second.
6. **Restaurants and cafés** move **within 60 minutes of the start time the user chose**, on the
   same day, and never start later than **21:00** (so a dinner starts at the latest at 21:00). They
   count in the distances: the attractions are ordered around them. They never change day.
7. **Locked items** keep their day, start and end, as in every recalculation. **Stops with a document
   attached** are offered as fixed: the backend cannot see the documents (ADR 023: phone only), so
   the app lists them in the sheet, pre-selected as "Keep in place", and sends their item ids as
   `fixed_item_ids`; the user can unselect any. A fixed item behaves like a locked one for this
   action only and is not locked afterwards.
8. **A multi-city trip keeps its cities** (ADR 024): a stop stays in the days of its own city (its
   nearest stop of the trip), so a Salzburg sight never moves to a Vienna day, and the order of
   the cities and the days of each city are not changed. Inter-city legs are not reordered.
9. **Day length.** A day may not end later than the **later of** the plan's day window end (09:00 to
   20:00, ADR 026 item 6, *proposed*) and that day's own current end, so Optimize never forces an
   impossible day and never needs a window the user's plan did not already use. Visit lengths are
   the user's, unchanged.
10. **Day start.** Each day starts at its current first item's start time, or 09:00 when it has
    none. Times are laid out again from there; an item whose start changes is shown in the diff as
    retimed.
11. **Objective:** least total travel minutes, walking and driving, over the whole plan (or, in the
    first scope, over each day). Ties are broken by earlier day, then position, then identifier.
    There is no randomness and no clock.
12. **Never worse.** The search starts from the user's current order and accepts only strictly
    improving moves (2-opt within a day; relocating or swapping a stop within a day and, in the
    second scope, between days), so the proposal's total travel is never higher than the current
    plan's. If nothing improves, the app says so and offers no change.
13. **Not optimal, and said so.** The heuristic finds a good order, not a proven best one (ADR 014
    and spike S5, decision D7). The preview shows the saving in minutes and kilometres and says
    "A shorter order, not necessarily the shortest".

### 3. Travel times

14. The search uses cached times and **labelled estimates**. Then the legs of the days that changed
    are asked of the travel source through the adapter, within its budget and rate rules
    (ADR 004), the days are laid out again, and the saving shown is computed from those legs. Any
    leg that stays estimated is labelled as such, and the saving says which part is estimated.
    This is the same two-stage approach as recalculation (ADR 018). Plan generation makes no
    other third-party call, and tests make none.
15. For a trip with many stops, estimates choose the order and the provider is asked only for the
    legs of the final days, so the number of calls is bounded by the legs in the proposal, not by
    pairs of stops.

### 4. Checks

16. **An independent revision validator** checks every proposal: no stop lost or duplicated; locked
    and fixed items unchanged; every restaurant on its day within 60 minutes of its chosen time and
    not after 21:00; no day longer than rule 9; every stop in the days of its city; no overlap;
    total travel not higher than before. A proposal that fails is not offered.
17. **No opening hours** are used (ADR 003). The preview says so: "Opening hours are not known; a
    place may be closed on its new day."

### 5. API and app

18. **API:** the change-set endpoint (ADR 018) accepts the action `optimize` with `scope`
    (`within_days` or `across_days`) and optional `fixed_item_ids`; the preview carries the diff,
    the total travel before and after and how much of it is estimated. A new module,
    `planner/optimize.py`, holds the search and works on manual plans (today `recalc.py` refuses a
    manual plan as "not recalculable"); it reuses the plan structures of `recalc.py`, the sequencer's
    moves, the travel service and the revision-validator pattern. OpenAPI and the generated client
    are rebuilt.
19. **App:** an **Optimize** row in the trip menu and on the Itinerary tab (shown when the plan has
    at least three stops with places). A sheet asks for the scope and lists the stops to keep in
    place (pre-selected from the documents). The preview is the existing change preview (the diff),
    with the saving at the top and the two notes of rules 13 and 17. Apply, Discard, and an
    undo for the applied version.

### 6. Tests

20. Golden tests for the search on synthetic fixtures; property tests that the total travel never
    increases, that every stop survives, that restaurants stay within their window, that locked
    and fixed items do not move and that a stop stays in its city's days; a determinism test;
    API tests for both scopes; app component tests for the sheet and the preview.

## Alternatives

| Alternative | Why not |
|---|---|
| Let restaurants move days, or keep them fixed | The owner chose 60 minutes around the chosen time: it lets the route improve without turning dinner into breakfast. |
| One scope only (across days) | Moving stops between days is a big change; the owner wants the gentler option too. |
| Solve optimally with OR-Tools | Spike S5 found it slower, and the heuristic enough (D7). The interface allows it later. |
| Optimize automatically whenever a place is added | The user chose their order on purpose; Optimize is a request, with a preview. |
| Treat every stop as fixed when it has a document | Documents are on the phone only, so the app decides and the user can change the list. |

## Consequences

- Hand-made trips get the planner's strength without giving up the order the user chose: the user
  asks, sees the saving and decides.
- A new module and one more change-set action; the manual-plan restriction of recalculation is not
  lifted for adding places (that remains the user's choice of day and time).
- The proposal's quality depends on travel times: cached and estimated at first, routed for the
  final legs; estimates are labelled.
- Opening hours and the reasons behind a hand-made order are unknown to the app: it asks only for
  locks and fixed stops.
- It depends on ADR 026 (sights-only data, restaurants as user items) and, for trips outside
  imported regions, on ADR 027; travel times there come from the same adapter.

## Revision of 2026-11-15 (after reading the code, ADRs 027 and 028 built)

The code shows four things the first draft left open. They change no owner decision of 2026-11-14.

1. **Manual plans and place trips are the main case, and today's pipeline refuses both.**
   `repo/changes.py` `_head` answers `not_recalculable` for a manual itinerary and
   `destination_not_plannable` for a place trip (ADR 027). Optimize needs neither the planner's
   sight data nor the destination's region, only the plan's items and their points. So `optimize`
   gets its own load step: it takes the itinerary of any profile and any destination kind, reads
   the stored plan state, and leaves the other actions' checks as they are. A past trip is still
   refused (`trip_archived`).
2. **Rule 8 for trips without a `geo` city (ADR 027 item 14, ADR 029 rule 8).** A stop's "own city"
   is decided as follows:
   - *multi-city trip (ADR 024):* the nearest of the trip's stops (their stored points);
   - *place trip:* a stop within **25 km** of the trip's point may move freely; one further away
     (a day trip) **keeps its day**, and is offered in the sheet as fixed;
   - *city or area trip:* no restriction, as today's planned itineraries.
   The 25 km is a fixed constant in `planner/config.py`, recorded with the other planner numbers.
3. **Undo.** `_restorable` today undoes only "the latest `add_place`". It is widened by one case:
   the latest applied change set, when it is an `optimize` and the plan has no later version,
   can be undone by restoring its base version (a new "Undo optimize" action on the trip, offered
   until the plan changes). No new table: `app.change_set` already stores `base_version`,
   `result_version` and the action; its action check constraint gains `optimize` (migration
   `0017`).
4. **Travel legs and manual plans.** A manual plan stores its legs as the user's order implies
   (travel is written between consecutive stops by the travel-time service). Optimize recomputes the
   legs of every day it changes, as rule 14 says, and writes them as the planner does, labelled
   routed or estimated.

### Build order (each step ends green: ruff, mypy, pytest, typecheck, lint, jest)

1. **Search and checks** (`planner/optimize.py`, `planner/optimize_validator.py`): the objective,
   2-opt and relocate within a day, relocate and swap between days, restaurants' 60-minute window
   and 21:00 limit, fixed items, day length, city rule; golden and property tests on synthetic
   fixtures. No database.
2. **Pipeline:** the `optimize` action, the context loader, the preview (estimates first, then the
   provider for the changed days), saving, apply, the widened undo, migration `0017`, OpenAPI and
   the generated client.
3. **App:** the sheet (scope, stops to keep, pre-selected from the documents), the preview with
   the saving and the two notes, the Optimize rows (trip menu, Itinerary tab), "Undo optimize".
4. **Docs in the same change:** architecture section 5, data model, design, brief, app plan,
   CLAUDE.md.

### Questions for the owner (recommendations first)

| # | Question | Recommendation |
|---|---|---|
| 1 | Allow Optimize on manual plans and place trips by giving it its own load step (point 1)? | Yes: it is the main case. |
| 2 | On a place trip, a stop more than **25 km** from the trip's point keeps its day (point 2)? | Yes; 25 km is a starting value, easy to change. |
| 3 | Offer "Undo optimize" for the latest applied optimize, until the plan changes (point 3)? | Yes. |
| 4 | Show the saving as minutes of travel and kilometres, and say which part is estimated (rule 14)? | Yes. |
| 5 | Offer Optimize only from three stops with places (rule 19)? | Yes. |

## Owner decisions (2026-11-14)

1. Restaurants may move within 60 minutes of the chosen time.
2. Both scopes, within each day and across all days.
3. A stop never moves between cities of a multi-city trip.
4. Dinner starts at the latest at 21:00.
5. Build it third, after destinations (ADR 027) and export (ADR 028).

## As built (2026-11-15, awaiting acceptance)

Migration `0017_optimize_change_sets`. Backend and app tested on synthetic fixtures and fake
servers; **not run against the production database** and not tried on a device. Travel times in the
tests are labelled estimates: nothing called the routing provider.

- **API.** `POST /v1/itineraries/{id}/optimize` (`scope`, `fixed_item_ids`) returns a change set
  (action `optimize`) with the diff, the saving and the notes; applying and discarding are the
  ordinary endpoints. `POST /v1/itineraries/{id}/optimize/undo` previews restoring the version from
  before the latest applied Optimize, while nothing changed the plan since (`409 nothing_to_undo`
  otherwise). `409 no_better_order` when nothing is shorter; `422 not_enough_stops` (under three
  stops with a place), `422 too_many_stops` (over 200), `422 unknown_items`. `ItineraryVersion`
  gained `restores_version`, so the app can tell an Optimize from its undo.
- **Search** (`planner/optimize.py`), checks (`planner/optimize_validator.py`), service
  (`planner/optimize_service.py`). Tests: `test_optimize.py` (search, rules, property tests on 12
  seeded plans), `test_api_optimize.py` (both scopes, apply, undo, refusals, a place trip), and
  `Optimize.test.tsx` in the app.
- **App.** An Optimize screen (scope, stops to keep, pre-selected from the documents), an Optimize
  row in the trip menu and at the top of the Itinerary tab, "Undo Optimize" in the trip menu, and the
  ordinary change preview with its notes shown open for Optimize.
- **Deviations from the draft.**
  (a) **Empty days stay empty and a day with stops keeps at least one.** The draft did not say so;
  without it a day boundary (which has no travel) makes the search spread a day's stops over the
  trip's empty days. Found by the first API test.
  (b) **A restaurant never starts earlier than the time the user chose**; it starts then, or up to
  60 minutes later when the stops before it take longer (never after 21:00). The draft allowed 60
  minutes either way; earlier never helps the route, and the independent check still accepts both.
  (c) **A day's end limit** is the later of the day window end, the day's own end and a
  restaurant's end at its latest start, so a dinner at 21:00 does not make the day "too long".
  (d) **Legs are written for every day of an Optimize proposal**, also for unchanged days, so the
  saving compares the same measure before and after; times of unchanged days are not touched. A
  manual plan had no stored legs before.
  (e) **Far stops on a place trip** keep their day and are named in a note ("N stops far from X keep
  their day"); the sheet does not list them as fixed, as the draft said, because the rule is the
  server's.
  (f) **Estimates and modes.** The walk or drive mode comes from the planner's existing rule (up to
  2 km straight line is walked), so an estimated walk of 1 km can take longer than an estimated
  drive of 2.5 km; the search follows the labelled times it is given.
  (g) A free-time block keeps its day and times and no leg is counted across it; a day with an item
  that has no time is left exactly as it is.
- **Not built / not verified.** No device check; no production run (migrations 0014 to 0017 are
  still to be run on the real database); the shortest order is not claimed, only a shorter one.

