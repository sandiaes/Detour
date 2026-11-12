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
5. Restaurants and prices are **not** part of the archive unless the owner asks. Prices already
   recorded stay in `app.price_record` and are untouched by archiving.

## Open question for the owner

The archive keeps what was *planned*. The app cannot know what was actually visited. Default
proposed: all planned city and attraction visits count as visited, and the user can remove any
that were skipped. Confirm or change.

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
