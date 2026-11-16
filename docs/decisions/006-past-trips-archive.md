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

## Amendment of 2026-11-14 (ADR 026): the archive keeps the days (built, awaits acceptance)

The owner wants the historical data kept. [ADR 026](026-trip-manager-first.md) section 5 changes
decision 2: a past trip keeps **every item of the selected itinerary** as snapshots (day, order,
start, length, kind, name, point, `geo` identifier, visited flag, note), not only one row per city
and attraction. Restaurants and cafés the user added are part of the record. Route geometry,
transfers, other itineraries, versions and change sets are still deleted. The past-trip screen
gains the day list; documents on the phone stay linked to its days and places. The map of visited
places and the "each city once" rule are unchanged. Decision 5 (restaurants are not archived) no
longer holds. Built as migration `0015` on `app.trip_visit` (no new table); see ADR 026, "As built:
step 5".

## Amendment of 2026-11-16: a past trip keeps its plan (owner request; built, awaits acceptance)

The owner asked for past trips to work like upcoming ones, with routes and the other functions
that the archive removed. This changes decision 2 and replaces the snapshot of decisions 4 and 5
and the amendment of 2026-11-14.

1. **Becoming past deletes nothing but old undo history.** Marking a trip (or the two-day rule)
   sets `status = 'past'` and `archived_at`, and nothing else: itineraries, days, items,
   transfers with their route geometry, change sets, stays and the chosen plan stay, and
   `selected_itinerary_id` is kept. No `app.trip_visit` rows are written.
2. **Undo history is capped at five versions for a past trip** (`MAX_VERSIONS_PAST` in
   `repo/plan_state.py`; 30 for any other trip). Archiving prunes every plan of the trip to the
   newest five stored versions and later changes keep that cap. Measured on the one real trip in
   production (2026-11-16), `itinerary_version` was the largest part of a trip's database footprint
   (30 versions, about 0.5 MB of about 1.5 MB on disk with indexes), so this is where a past trip
   saves space.
3. **A past trip is editable.** The `trip_archived` refusals are gone: the plan can be changed,
   optimized, given stays, new proposals and a new title, as before. The trip stays in the Past tab.
   Marking as past is still one-way for the status (there is no "back to upcoming" yet).
4. **Export and import** carry a past trip's plan (`days`) like any trip; the file's `visits` are
   used only for a trip with no plan.
5. **Trips archived before this amendment** keep their `trip_visit` rows and no plan. The app opens
   them on the old past-trip screen (map, Days, list, skip and restore); the endpoints
   `GET /v1/trips/{id}/archive`, `GET .../visits` and `PATCH .../visits/{id}` stay for them.
   They can be given a new plan like any trip. Nothing is migrated.

Consequences: a past trip costs what any trip costs (a few hundred KB at most), plus nothing for
routing, because route lines are fetched for the selected plan only and cached travel times are
shared. The archive size report is only meaningful for older archives.

## Amendment of 2026-11-17: a past trip is read-only and can be reopened (owner request; built, awaits acceptance)

The owner reviewed the 2026-11-16 behaviour on the phone and asked that a past trip not be
editable: only photo-album links and documents (both kept on the phone) may be added. This reverses
point 3 of the amendment of 2026-11-16 and adds the "back to upcoming" step it said was missing.

1. **Every change to a past trip's plan is refused with 409 `trip_past`**: adding, changing or
   removing an item, a stay or a transport leg; change sets (preview, apply, Optimize and its
   undo, place suggestions, city edits); a new empty plan, new proposals and deleting a plan; the
   trip's own fields (name, dates, days, car, chosen plan); and the cover choice. The check is in
   the server (`trips.require_open_trip`, `trips.refuse_if_past`), not only in the app. Reading,
   export, deleting the whole trip and discarding a change set that was already pending still work.
   Import creates a new trip, so it is unaffected. Documents and photo links need no server call.
2. **Reopen**: `POST /v1/trips/{id}/reopen` makes a past trip `active` again, clears `archived_at`
   and sets `app.trip.reopened_at` (migration `0022`). The two-day rule skips a trip with
   `reopened_at`, so it does not become past again by itself the next time the trips are read; the
   user can mark it past by hand again. Only a past trip can be reopened (409 `not_archived`).
3. **App**: a past trip hides Optimize, Undo Optimize, Where you're staying, Original proposals,
   Get new proposals and Edit cities; the Add sheet disables Place, Restaurant and Transport (the
   Document row stays); a transport leg opens as a read-only note; the cover can still be chosen
   from the phone but not from destination photos; Trip settings offers **Reopen trip** and
   Delete. The place screen already hid Edit time, Lock and Remove for a past trip.
4. **New-trip screen**: a start date before today shows a warning (the whole trip is over, or its
   first days have happened). It never blocks: a journey already taken stays a valid trip (ADR 026,
   decision 23).
5. The undo-history cap of five versions for a past trip stays; reopening does not restore versions
   that were pruned.
