# ADR 032 — Manual transport legs

- **Status:** **Accepted** on 2026-11-16: the owner answered the four questions below as
  recommended (see "Owner decisions"). Written as **Proposed** the same day, at the owner's request
  (the owner chose this option after reviewing an analysis of public transport). **Built** the same
  day (see "As built"), awaiting acceptance of the build. Checked by tests only: **not tried on a
  device** and not run against the production database (migration `0021`).
- **Date:** 2026-11-16
- **Related:** [`026-trip-manager-first.md`](026-trip-manager-first.md),
  [`021-trip-manager-redesign.md`](021-trip-manager-redesign.md) (decisions 92 and 99),
  [`023-trip-documents-on-the-device.md`](023-trip-documents-on-the-device.md),
  [`024-multi-city-trips.md`](024-multi-city-trips.md),
  [`028-trip-export-and-import.md`](028-trip-export-and-import.md),
  [`029-optimize-a-hand-made-trip.md`](029-optimize-a-hand-made-trip.md),
  [`030-accommodation-stays.md`](030-accommodation-stays.md),
  [`017-no-budgets-currencies-or-prices.md`](017-no-budgets-currencies-or-prices.md),
  [`../api-evaluation.md`](../api-evaluation.md) section 8

## Questions for the owner (recommendations first; answered 2026-11-16, see "Owner decisions")

| # | Question | Recommendation |
|---|---|---|
| 1 | **The "Public transport" pill** on the new-trip screen is local state: it is not sent, not stored and not used. Remove it, with its hint text, its tests and the lines that describe it (decision 9 below)? | **Remove it.** Keep Car as it is. Recording how you travelled is done with transport legs instead. |
| 2 | **Optimize without a car.** Today `uses_car = false` makes Optimize walk every leg however long, so a 12 km leg is laid out as a 2 h 30 walk. Which rule (decision 6)? (a) Keep walking every leg, but use the user's transport legs as they are and **name the long walks** in the preview ("2 legs are walks over 2 km: add a transport leg for how you will travel"). (b) Legs over 2 km are **not timed**: the search orders them by distance, the layout keeps the user's start times after them, and the preview says their time is unknown. (c) Legs over 2 km are timed as **drives, labelled "by road, an estimate"**, even without a car. | **(a).** It changes nothing hidden, never invents a time, and the user's legs fill the gaps where it matters. (b) makes laid-out days less predictable; (c) puts a car time on a trip without a car. |
| 3 | **Where a leg may sit in the first step:** between two stops of a day, as the journey between two cities (ADR 024), or both? | **Both.** One item type serves both; the journey case is where the Japan gap is. |
| 4 | **Trip file.** Transport legs need trip file version 2 (decision 8). Carry the trip's **stays** (ADR 030) and its **Car** choice in the same version? | **Yes.** The version changes anyway; stays and Car were left out of version 1 only because they did not exist when it was written, and an import today silently loses them. |

Smaller choices made here without a question (the owner may change any): legs are items of the plan
(decision 1), a leg that passes midnight (decision 3), a day with a leg in Optimize's across-days
scope (decision 5), document links (decision 7).

## Context

Detour is a trip manager and travel history first (ADR 026); the owner almost never generates
itineraries. Public transport is today only a dead pill: on the new-trip screen "Public transport"
is local state, not sent, not stored and ignored by the planner (`CreateTripScreen.tsx`, the
`publicTransport` state and the "Getting around" pills). The Add sheet has a disabled "Transport"
row (`nav/BottomNav.tsx`). Travel between stops is walk or drive only (`planner/travel.py`,
`adapters/valhalla.py`). Between the cities of a generated multi-city plan the app shows a driving
time even when the user took a train, and a journey into or out of Japan reads "time not calculated:
public transport is not built yet" (ADR 024). A manual multi-city plan has no journey row at all
(`create_manual` writes no arrival leg).

What a trip manager needs is to **record how the user actually moved**: "train Rome to Florence,
10:12, 1 h 30". This is a new feature (CLAUDE.md rule 3). It adds **no provider** and no language
model: every value is typed by the user. Routing through Transitous or MOTIS (Phase 10) is not
started; see "Later: a suggestion for one leg".

## Decision

### 1. What a transport leg is

1. **A leg is an item of the plan**, a new `itinerary_item.type = 'transport'` beside `visit`,
   `meal` and `free_time`. It has a day, a position among the day's items, an optional start time
   and length, `origin = 'user'` and `locked = true`. Being an item, it is in every itinerary
   version, so **undo, versions, change sets, the 40-items-a-day limit and deleting a trip** work as
   for any other stop, with no new table. A leg belongs to the plan it was added to: new proposals
   do not have it.
2. **What the user enters** (migration `0021`, columns on `app.itinerary_item`, all null for other
   types; a CHECK ties them to `type = 'transport'`):
   - `transport_mode`: one of `train`, `bus`, `metro_tram`, `ferry`, `taxi`, `walk`, `other` (a
     fixed list; `taxi` reads "Taxi or ride"). Each has an icon drawn in the `components/ds` style
     (`Icon` names `train`, `bus`, `metro`, `ferry`, `taxi`, `walk`, `transport`).
   - **From** and **to**: a name (1 to 120 characters) and an optional point, picked from the trip's
     stops, cities (ADR 024 stops, base cities) or stays (ADR 030), or typed as free text (no
     point). Stored as snapshots (`from_name`, `from_point`, `to_name`, `to_point`), like every
     item's `display_name`; `display_name` is "Train to Florence" (built from mode and to).
   - **Start time** (optional) and **length** (optional), or **arrival time** instead of length: the
     app turns an arrival into a length; only the length is stored (`duration_minutes`). A length
     the user did not enter is **unknown**, stored as null and shown as "time not entered" (hard
     constraint 5). `duration_source` is `user` when a length is set.
   - **Note** (optional, up to 500 characters, `note`).
   - No price, fare, operator, seat, booking reference or ticket purchase (ADR 017, hard
     constraint 2). A ticket belongs in a document (decision 7).
3. **Times.** A leg with a start and a length has `end_time` = start + length when that is the same
   day. A leg that **passes midnight** (a night train) stores its start and length with `end_time`
   null and is shown "arrives 07:10 the next day"; it must be the last timed item of its day. For a
   leg, `duration_minutes` may be null and `start_time` may be set without `end_time` (the item
   CHECKs gain these two exceptions for `type = 'transport'` only). The overlap check counts a leg
   from its start to its end, or to the end of the day when it passes midnight, or as a point when
   its length is unknown.
4. **Two places a leg can sit** (question 3):
   - **Between two stops of a day:** its position puts it between them. It **replaces the computed
     leg** between the stop before and the stop after: no transfer is written across it, and its
     length is the travel time of that stretch. The walk to the station is not invented: the user
     can add a second leg (mode walk) if they want it shown.
   - **The journey between two cities:** a leg marked `is_journey = true`, placed first on the
     first day at the new city (from the previous city, to this one, prefilled). It **replaces**
     the day's computed arrival (`Day.arrival`, ADR 016 and 024) in the day list and on the map, and
     fills "time not calculated" for a journey into or out of Japan. On a manual multi-city plan,
     which has no arrival row, it is the journey row. `Day.arrival` stays stored as computed; the
     read model marks it `covered_by_item_id` and the day's travel total uses the leg instead.

### 2. Planner, recalculation and Optimize

5. **A leg is fixed.** Optimize (ADR 029) and recalculation (ADR 018) never move, retime or remove
   it, and **never reorder across it**: the stops before a leg stay before it and the stops after
   stay after it, each side ordered on its own. Its length (or "unknown") is the travel time of
   that stretch, used instead of a walk or drive time; no transfer is computed across it. In
   Optimize's across-days scope, a day with a leg keeps its own stops (none move in or out), because
   a leg usually means the stops on its two sides are in different places. The independent checks
   (`optimize_validator.py`, `revision_validator.py`) gain: every leg unchanged, no stop crossed a
   leg. A leg is shown in the preview as unchanged. Generation (`planner-3.0.0`) is not changed:
   golden files stay as they are and `CONFIG_VERSION` is not bumped, unless the build finds the
   sequencer has to know about legs (then the ADR's "As built" says why).
6. **Optimize without a car** (question 2, recommendation (a)). Without a car Optimize keeps
   walking every computed leg, uses the user's transport legs as they are, and the preview names
   the walks over 2 km (`walk_max_m`): "2 legs are walks over 2 km: add a transport leg for how
   you will travel". The default stays as built: off when a trip is created (decision 99), true
   for trips created before migration `0018` and, until the trip file carries it, for an imported
   trip (decision 8 fixes that).

### 3. Documents, export, versions

7. **Documents (ADR 023).** "Attach a document" on a leg links it as a **journey** link with the
   leg's day and name ("Train to Florence", day 2): the documents stay on the phone, and the link
   is kept by name and day as for places, so it survives plan changes. The leg's detail sheet lists
   its documents. The backend learns nothing about documents (Optimize's "Keep in place" list does
   not need legs: they are always fixed).
8. **Trip file version 2 (ADR 028).** A transport leg is a stop of kind `transport` in a day's
   stops, with mode, from and to (name and point), start, length or null, journey flag and note.
   Version 2 also carries the trip's **stays** and its **Car** choice (question 4). Export writes
   version 2; import reads versions 1 and 2 (version 1 keeps importing, as ADR 028 promises); an
   app that knows only version 1 refuses a version 2 file with "update the app" (`format_too_new`,
   as built). A leg imports as a leg of the manual plan, unchanged.

### 4. App

9. **The "Public transport" pill is removed** (question 1): the pill, its local state, the hint's
   second sentence ("Public transport is saved for later…"), its test and accessibility line, and
   the lines describing it in `docs/design.md` (section 3, "Getting around", and the open point
   in section 7), `docs/design-audit.md`, `docs/known-limitations.md` and `CLAUDE.md`; ADR 021
   decisions 92 and 99 are amended, not rewritten. Car stays as it is.
10. **Add a leg.** The Add sheet's "Transport" row is enabled ("A train, bus or ferry you took or
    will take"). It opens **Add transport**: a mode drop-down with icons, From and To (each a
    drop-down of the day's stops, the trip's cities and stays, or "Type a name"), Day (drop-down),
    Start time (the time roulette, optional), Length (one free field, as for stops, or "Arrival
    time" instead), "Journey between cities" (shown on a multi-city trip or when From and To are
    different cities), Note. The day and position default to the open day, after its last stop.
    Saving writes the item (`POST /v1/itineraries/{id}/days/{n}/items` with `type = transport`);
    the leg's own sheet edits or removes it (confirmation sheet).
11. **Day list and map.** A leg is a hairline row like travel between stops, but with the mode icon
    and words: "Train · 1 h 30 · 10:12 to 11:42", or "Train · time not entered". Its spoken label
    names the mode, from, to, times and "entered by you". A journey leg is the journey row ("To
    Florence", "Train from Rome · 1 h 30"). On the map a leg is a line from its from-point to its
    to-point (or between the neighbouring stops when a point is missing) with the mode icon at its
    middle; no line when neither end has a point. All from the existing tokens and components;
    `styleTokens.test.ts` must pass (no own colours, sizes, radii, spacing; a focus ring on every
    tappable thing).

### 5. API

12. `ItemCreate` and `ItemUpdate` accept `type = transport` with `transport_mode`, `from`, `to`
    (`{name, lat?, lon?}`), `start_time?`, `duration_minutes?`, `is_journey`, `note?`; `Item` gains
    `transport` (null for other types) and allows `duration_minutes` null for a leg; `Arrival` gains
    `covered_by_item_id`. OpenAPI is exported and the client regenerated. A leg cannot be added to a
    proposal that is not the trip's plan (as other hand edits).

### 6. Build order (each step ends green: ruff, mypy, pytest, typecheck, lint, jest)

1. **Migration `0021` and API:** the item type, columns and CHECKs, create, update, delete, read,
   overlap, versions; `export_openapi.py`, `npm run generate`. API tests.
2. **Planner and Optimize:** legs as fixed segment boundaries in `optimize.py` and `recalc.py`, the
   validators, the long-walk note; tests (property tests: a leg never moves, no stop crosses a leg).
3. **Export and import, version 2:** legs, stays and Car; round-trip tests; version 1 still imports.
4. **App:** Add transport, the leg rows and map lines, the journey row, documents on a leg, the
   pill removed; component and accessibility tests.
5. **Docs in the same change as each step:** CLAUDE.md, `design.md`, `data-model.md`,
   `known-limitations.md`, `app-plan.md`, `product-brief.md`, `build-prompts.md`.

## Owner decisions (2026-11-16)

1. Remove the "Public transport" pill; keep Car as it is.
2. Optimize without a car: rule (a), walk every computed leg, use the user's legs as entered and
   name the walks over 2 km in the preview.
3. Both: legs between two stops of a day and journeys between two cities.
4. Trip file version 2 carries transport legs, stays and the Car choice.

## As built (2026-11-16, awaiting acceptance)

Migration `0021_transport_legs`. Backend and app tested on synthetic fixtures and fake servers;
**not run against the production database and not tried on a device.**

- **API.** `ItemCreate.type = transport` with `transport` (`TransportInfo`: `mode`, `from_name`,
  `from_lat/lon`, `to_name`, `to_lat/lon`, `is_journey`, `note`), optional `start_time` and
  `duration_minutes`; `ItemUpdate.transport` replaces it and `duration_minutes: null` makes a leg's
  length unknown; `Item.transport`, `Item.duration_minutes` nullable, `Arrival.covered_by_item_id`.
  A leg is always locked; `locked: false` is ignored for it. A journey leg added without a position
  goes first on its day. Overlaps: a leg of unknown length is a point (it clashes only inside another
  stop), a night train takes the rest of its day. Errors: `422` for a leg without details, with a
  place, with a half point or an unknown field (a price, for example), `422 not_transport` for
  transport details on another item, `409 overlap`.
- **Planner.** `planner/optimize.py` (`optimize-1.0.0`, unchanged version: a plan without legs gives
  the same answer as before), `optimize_validator.py` ("a transport leg moved", "a stop crossed a
  transport leg"), `optimize_service.py` (the `OPTIMIZE_LONG_WALKS` note without a car),
  `repo/plan_state.py` (`TRANSPORT_LEG_DAY`). Generation is unchanged: no golden file changed and
  `CONFIG_VERSION` is not bumped.
- **Trip file version 2** (`models/exchange.py`, `repo/exchange.py`; `FORMAT_VERSION = 2` in the app).
- **App.** `domain/transport.ts`, `screens/TransportLegScreen.tsx` (Add transport and Change
  transport), the leg row and journey row in `components/plan/DayPlan.tsx`, the leg line and mode
  mark in `components/ItineraryMap.tsx`, five new icons (bus, metro, ferry, taxi, walk; a train is
  the existing transport icon), the Add sheet's Transport row, "Attach a document" on a leg. The
  Public transport pill is gone (`CreateTripScreen.tsx`).
- **Tests.** `test_api_transport.py` (12), new cases in `test_optimize.py` (13 with the property
  tests), `test_trip_export.py` (3), `test_planner_recalc.py` (1); `domain/transport.test.ts`,
  `screens/TransportLeg.test.tsx`, cases in `ItineraryMap.test.tsx`, `BottomNav.test.tsx`,
  `documents/model.test.ts`, `accessibility.test.tsx`, `CreateTripScreen.test.tsx`.
- **Deviations from the draft.**
  (a) **One jsonb column `transport`**, not seven columns: the API validates it (`TransportInfo`),
  and a CHECK ties it to `type = 'transport'`. It travels through versions and change sets as one
  value.
  (b) **Recalculation does not plan around a leg** (decision 5 said it would treat it as fixed). Add a
  place's suggestions on a generated plan name the day with a leg (`TRANSPORT_LEG_DAY`) and the user
  chooses the day and time, as on an empty trip. Optimize, which owners use on hand-made trips, does
  respect legs as decided.
  (c) **Documents** use the existing journey link (`leg`, by day and name), as decision 7 said; a
  leg's own screen offers "Attach a document" rather than listing its documents.
  (d) **The journey row's unknown-time text** now reads "time not calculated: add how you travel as
  transport", and the backend's `ARRIVAL_TIME_UNKNOWN` note says "add how you travel as a transport
  leg", instead of "public transport is not built yet".
  (e) The map key's transport line reads "Travel to a new base city, or transport you entered".
- **Not built / not verified.** No device check; no production run; recalculation around legs
  (deviation b); listing a leg's documents on its screen.

## Amendment of 2026-11-16: where a leg goes, and the stops after it (owner request)

The owner found that a leg added after an Optimize landed at the bottom of the day, while the walk
it was meant to replace stayed between the two stops. Owner decisions of the same day:

1. **Placement.** A new leg, or a changed one whose day, From, start or journey mark changed, goes
   (a) right after its **From stop** when From is a stop of that day, so it replaces the computed
   walk or drive from that stop (the server already drops a transfer that no longer joins two
   neighbours); (b) otherwise **first** for a journey between cities; (c) otherwise in **time
   order** by its start; (d) otherwise after the last item. The app works the position out
   (`legPosition` in `domain/transport.ts`) and sends it; the server is unchanged here.
2. **Times: move the later stops (owner's choice (b)).** When the leg runs into the items after it,
   the app asks "Move the later stops?" and names the first one and the minutes ("Move them 24 min
   later"); on yes, every timed item after the leg on that day moves that many minutes later in the
   same edit (`shift_later_minutes` on `ItemCreate` and `ItemUpdate`, transport legs only; one
   version, so one undo). Order and lengths stay; locked stops and restaurants move too, because the
   user asked. A move that would take an item past midnight is refused (`422 shift_past_midnight`;
   the app says so before sending). A leg that leaves before the stop **before** it ends is not
   fixed for the user: the app names that stop and its end, and nothing is saved. A leg of unknown
   length is a point and pushes nothing.

## Alternatives

| Alternative | Why not |
|---|---|
| A separate table `app.transport_leg` joining two items | A reorder or removal breaks the pair; versions, undo and export would each need new code. An item already has day, position, time and length. |
| Attach a leg to a transfer row (`app.transfer`) | Transfers are rewritten by every recalculation and Optimize (ADR 018, 029); a hand-entered leg would be lost. |
| Store the leg on the trip, not the plan | A leg sits between stops of one plan; another proposal has other stops. |
| Keep the "Public transport" pill and use it later | It has never done anything; a pill that does nothing reads as a broken promise. Legs say what the user did. |
| Compute transit times now (Transitous) | Phase 10, not approved; the owner chose manual legs first. See "Later". |
| Let Optimize move legs | The user entered a real departure; moving it would contradict the ticket. |

## Consequences

- A trip can record how the user travelled, including into and out of Japan, with no provider.
- Item rules get type-specific exceptions (null length, start without end, midnight). The read
  model, overlap check, version state and export all learn one new type.
- Optimize and recalculation see more fixed points, so they may find smaller savings on days with
  legs; never a wrong order across a train.
- The trip file moves to version 2; old files keep importing; an old app refuses a new file.
- The dead pill and its notes go; "public transport is not built yet" goes from the journey row
  when a leg covers it (it stays for a journey with no leg).

## Later: a suggestion for one leg

**Option D: suggest a time for one transport leg** (2026-11-16; candidate, **not approved**; do
not build it without a new request from the owner). After manual transport legs exist, the user
may ask Detour for a suggested public-transport time for one leg: from here to there, on this day
and time. The backend asks Transitous (MOTIS 2 API) for a single journey and the app shows it as a
labelled estimate: the user accepts it (it becomes a normal manual leg, editable) or ignores it. No
planner change, no bulk routing, no use inside generation or Optimize, no real-time data.

- **Why it fits:** light use, one request per tap, well under Transitous's coordination threshold
  of 720 requests a day (`api-evaluation.md` 8.1); the repository is public (ADR 007 addendum),
  which removes the old D11 blocker.
- **Preconditions:** an ADR citing the Transitous terms and the date read (CLAUDE.md rule 4;
  `api-evaluation.md` section 8.1 has the verified summary and must be re-checked); an adapter with
  a timeout, a cache, a daily budget counter and an identifying User-Agent; a visible link to
  <https://transitous.org/sources/> and each source's attribution; a fallback of "no suggestion,
  enter it by hand".
- **Risks:** a best-effort service that can be withdrawn at any time (the manual leg must keep
  working without it); feed quality varies by region; schedule data only (a time on a day weeks
  ahead is a timetable, not a promise). If Transitous becomes unavailable, self-hosted MOTIS is not
  in scope at this size.
