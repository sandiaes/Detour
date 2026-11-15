# ADR 030 — Accommodation: where the traveller sleeps

- **Status:** **Accepted** on 2026-11-15 (owner request and answers of the same day), **built**
  2026-11-15 and awaiting acceptance of the build. Not run against the production database
  (migration `0019`), not tried on a device.
- **Date:** 2026-11-15
- **Related:** [`029-optimize-a-hand-made-trip.md`](029-optimize-a-hand-made-trip.md),
  [`026-trip-manager-first.md`](026-trip-manager-first.md),
  [`014-phase-4-planner-v1.md`](014-phase-4-planner-v1.md),
  [`013-phase-3-travel-time-service.md`](013-phase-3-travel-time-service.md),
  [`028-trip-export-and-import.md`](028-trip-export-and-import.md)

## Context

The planner and Optimize treat a day as an open path that starts at its first stop (product brief,
section 9: no accommodation). The owner wants to say where they sleep, so the app knows where the
day begins and routes from there. This is a new feature (CLAUDE.md rule 3). It adds no provider, no
language model and no booking: a stay is a place the user names, nothing about availability or price.

## Decision

1. **A trip has stays** (`app.trip_stay`, migration `0019`): a name, a point and a **range of days**
   (first to last). Several are allowed (owner answer 1: "several hotels, day range"); ranges may not
   overlap or leave the trip's days (`409 stay_overlap`, `422 day_out_of_range`); a past trip's stays
   cannot change. A day without a stay behaves as before. The stay is found by Photon through the
   backend (the existing external search) or typed by hand with coordinates.
2. **API.** `GET/POST /v1/trips/{id}/stays`, `PATCH/DELETE /v1/trips/{id}/stays/{stay_id}`. `Day.start`
   (read-only) is the morning leg from the day's stay to its first stop with a place: mode, time,
   distance and whether it is routed or an estimate. **It is worked out when a plan is read**, from
   the cache and labelled estimates only (never a provider call), and is **not stored**: a plan edited
   by Add a place, Optimize or a hand edit therefore never loses it, and a stay added later shows on
   plans that already exist.
3. **Optimize** (`planner/optimize.py`, `optimize-1.0.0`): each day's travel also counts the leg from
   its stay to its first stop, so the search prefers an order that starts near the stay, and a stop
   may move to a day whose stay is closer. The day starts at its stay: its first stop starts that
   many minutes after the day does. **No leg back to the stay at the end of the day** (owner answer
   2). The saving in the preview includes these legs. The independent check counts them too.
4. **Generated itineraries** (owner answer 3: include). `PlanRequest.stays`; the sequencer's problem
   has an optional per-day `start_travel` (minutes from the day's stay to each place), counted in the
   day's travel and its time budget; the day is laid out starting after that leg. Days at one base are
   no longer interchangeable when a stay exists, so a segment with stays keeps the days in order
   instead of "fullest day first". The day of a drive to a new base city starts from that drive and
   ignores its stay. Without stays nothing changes: the golden files are the same. The stay's
   legs are not part of the plan's stored travel statistics.
5. **App.** "Where you're staying" in the trip menu opens a screen with the stays (day range under
   the name), Add a stay (search, or name and coordinates, and From/To day steppers defaulting to the
   first days that have none), edit and remove (confirmation sheet). The map shows a navy house mark
   and a line to the first stop; the key has "Your stay"; the day list starts with a hairline row
   "Walk from Hotel Alpen · 10 min · 800 m"; the Optimize preview draws the same for the proposed
   plan (`ChangeSet.proposed.starts`).

## Alternatives considered

- **One stay per trip.** Simpler, but a trip that changes hotels would be wrong half the time.
- **Store the morning leg on the day.** It would be lost by every recalculation that rebuilds days
  from the plan state, and a new stay would need every plan rewritten. Reading it is cheap (cache).
- **A leg back to the stay at night.** Owner answer 2: not wanted.
- **Treat the stay as a base city.** Base cities carry the area-trip logic and a drive between
  them; a hotel is a point inside a city.

## Consequences

- The recalculation for Add a place (ADR 018) still plans without the stay; the leg on the day is
  shown, but the choice of day and position does not count it. Optimize afterwards does.
- Export and import (ADR 028) do not carry stays yet: an imported trip has none.
- A stay is a user-entered point; the app shows no photo, rating or price for it.
- Tested: `test_optimize.py` and `test_planner_engine.py` (no database), `test_api_stays.py` (needs
  the database; **not run here**), `Stays.test.tsx` and the preview tests in the app.
