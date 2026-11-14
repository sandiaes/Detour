# ADR 029 — Optimize a hand-made trip

- **Status:** **Proposed** on 2026-11-14, at the owner's request, after the owner answered the
  design questions (see "Owner decisions"). Documentation only: nothing is built. It is the **third**
  manager feature, after destinations outside the imported regions (ADR 027) and trip export
  (ADR 028).
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

## Owner decisions (2026-11-14)

1. Restaurants may move within 60 minutes of the chosen time.
2. Both scopes, within each day and across all days.
3. A stop never moves between cities of a multi-city trip.
4. Dinner starts at the latest at 21:00.
5. Build it third, after destinations (ADR 027) and export (ADR 028).
