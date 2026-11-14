# ADR 006 — Past trips archive

- **Status:** Accepted on 2026-11-12 (owner request). Release timing is not yet decided.
- **Date:** 2026-11-12
- **Related:** [`../product-brief.md`](../product-brief.md), [`../data-model.md`](../data-model.md),
  [`005-free-managed-hosting.md`](005-free-managed-hosting.md)

## Context

The owner wants to look back at past trips in the app, on a map showing the cities and the
attractions visited, without routing information for past trips. This is a new product goal
(CLAUDE.md rule 3), so it needs an ADR. It also bears on database size: Supabase Free allows
500 MB (ADR 005).

## Decision

1. A trip can be marked **past** (by the user, or automatically after its last day).
2. When a trip becomes past, the backend keeps a compact **archive** and deletes the rest of its
   planning data:
   - **Kept:** title, destination, start date and duration, and one row per city and attraction
     of the selected itinerary with a **snapshot** of its name, coordinates, kind and day number,
     plus the `geo` identifier it came from.
   - **Deleted:** transfers, route geometry, unselected and superseded itineraries, itinerary
     versions and seeds.
3. The app shows a past trip as a map with markers for the visited cities and attractions and a
   list grouped by city. No routes, travel times or turn-by-turn information are shown.
4. Snapshots are used because the `geo` data is re-imported over time and identifiers or
   attributes may change; the archive must not break. This is an intentional exception to
   "`app` does not copy `geo` attributes", limited to name, coordinates and kind.
5. Restaurants and prices are **not** part of the archive unless the owner asks. (Prices no longer
   exist in the product, ADR 017.)

## Open question for the owner

The archive keeps what was *planned*. The app cannot know what was actually visited. Default
proposed: all planned city and attraction visits count as visited, and the user can remove any
that were skipped. Confirm or change. (Built as proposed, see the amendment below; the owner has
not yet confirmed it.)

## Alternatives

| Alternative | Why not |
|---|---|
| Keep the full itinerary for past trips | Stores route geometry the owner does not want; grows the database. |
| Reference `geo` rows only, no snapshot | Past trips can break or change when region data is re-imported. |

## Consequences

- New table for archived visits (`app.trip_visit`) and a trip status; see `data-model.md`.
- Archiving is a one-way step for routing data: a past trip cannot be re-planned from its archive.
- Size: an archived trip is a few dozen small rows, so past trips add little to the 500 MB.
  The real consumers are the `geo` data and the travel-time cache; archiving bounds the growth of
  per-trip data (route geometry, versions) but does not change the total today.

## Amendment of 2026-11-13: built (awaits acceptance)

The archive is built end to end: the backend (manual and automatic archiving, the size report) and
the app's past-trip screen. It is tried on synthetic fixtures only; no real region has been
imported. Decisions the build had to make:

1. **Automatic archiving needs no scheduled job.** When the app reads the trips (`GET /v1/trips`,
   `GET /v1/trips/{id}`), the backend first archives the caller's active trips whose last day ended
   **two days ago or more** (`AUTO_ARCHIVE_GRACE_DAYS`). The last day is a calendar date without a
   time zone and a destination can be anywhere from UTC-12 to UTC+14, so two days make sure that
   day is over everywhere before anything is deleted; the effect is the same as the user marking
   the trip. A trip without a start date has no last day and never becomes past by itself, and the
   seed trip (illustrative data) is left alone. A trip nobody opens stays as it is until its owner
   next opens the app, which is when it would be looked at anyway.
2. **What is kept** is exactly the list in decision 2: the trip row (title, destination snapshot,
   start date, duration) and one `app.trip_visit` row per city and attraction of the selected
   itinerary. Each base city is listed once however many days are spent there; a town the user
   added by hand that has the name of a base city already listed is not listed again. Without a
   selected itinerary a city destination keeps its destination city; an area destination keeps
   nothing. **Deleted** is every itinerary of the trip and, by cascade, its days, items, transfers
   with their route geometry, itinerary versions and change sets. User places stay.
3. **The list is grouped by city on the device.** The archive stores no city for an attraction, so
   the app puts each attraction under the nearest city row (and, with no city row, under the
   destination's name). No schema change.
4. **Skipped visits** are the `confirmed` flag, as proposed. A cleared visit leaves the map, stays
   in the list marked as skipped and can be restored; it is not deleted. Cities can be cleared too.
5. **The size is reported.** `GET /v1/trips/{id}/archive` returns the number of cities and
   attractions, how many were cleared, and `size_bytes`: the stored row data of the trip row and
   its visit rows (PostgreSQL `pg_column_size`; indexes and page overhead are not counted). The
   past-trip screen shows it, and every archiving writes it to the log with the number of
   itineraries deleted. Measured in the test on the synthetic Testburg plan: 28 visits, 4,519 bytes.
6. **A past trip needs no routing data.** The visits, archive and trips endpoints read `app.trip`
   and `app.trip_visit` only; a test renames `app.transfer` and `geo.travel_time` away and the past
   trip still lists. The map has no line layer. A re-import of `geo` data cannot touch an archived
   trip: the rows hold snapshots and there is no foreign key (a test re-imports the region, which
   deletes the places the archive names).
7. **The user can mark a trip as past** from Trip settings, after a confirmation that says what is
   kept and what is deleted. Archiving cannot be undone. A past trip is read-only except for
   clearing visits and deleting the trip.

## Amendment of 2026-11-14 (ADR 026): the archive keeps the days (proposed, not built)

The owner wants the historical data kept. [ADR 026](026-trip-manager-first.md) section 5 changes
decision 2: a past trip keeps **every item of the selected itinerary** as snapshots (day, order,
start, length, kind, name, point, `geo` identifier, visited flag, note), not only one row per city
and attraction. Restaurants and cafés the user added are part of the record. Route geometry,
transfers, other itineraries, versions and change sets are still deleted. The past-trip screen
gains the day list; documents on the phone stay linked to its days and places. The map of visited
places and the "each city once" rule are unchanged. Decision 5 (restaurants are not archived) no
longer holds. Until ADR 026 step 5 is built, the archive works as described above.
