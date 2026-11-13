# ADR 020 — A trip manager: open on the chosen plan, tell sights from places to eat, delete trips

- **Status:** **Proposed** on 2026-11-13, at the owner's request. Built and tested in the mobile
  app only; there is no backend change (the delete endpoint already existed). The owner confirms
  or changes the decisions below.
- **Date:** 2026-11-13
- **Related:** [`006-past-trips-archive.md`](006-past-trips-archive.md),
  [`015-phase-5-mobile-shell.md`](015-phase-5-mobile-shell.md),
  [`../product-brief.md`](../product-brief.md)

## Context

Until now the app centred on *drafting* a plan: opening a trip always showed the two proposals and
their comparison, even after one was chosen. The owner wants the app to become, over time, a
manager and history of trips: once a plan is chosen, the work is adjusting that plan. Two further
requests: the map and the day list must show which stops are sights and which are places to eat,
and a trip must be deletable. This is a change of emphasis plus a delete control, not a new
provider or a new data source (CLAUDE.md rules 3 and 4 are not touched).

## Decision

1. **A trip with a chosen plan opens on that plan** (days list, with the map one tap away). A
   trip without a chosen plan, and a trip still to be planned, opens on the proposals as before.
   Past trips keep their existing screen. (Superseded in part on 2026-11-13: a past trip now opens
   on its map of visited places, ADR 006 amendment.)
2. **Choosing a plan opens it**, with the trips list underneath, so Back returns to the trips.
3. **Trip settings** (a button on the plan screen and on the proposals screen) holds two actions:
   - *Get new proposals*: runs the existing generation. The backend already keeps the selected
     plan and replaces only unselected proposals, so the current plan, with the places the user
     added, stays selected until a new one is chosen. The proposals screen shows the kept plan
     apart from the new pair. Not offered for a past trip.
   - *Delete trip*: after an inline confirmation, calls `DELETE /v1/trips/{id}` (trip, itineraries,
     days, items, transfers and archive rows). The app then drops the trip and its plans from the
     list, memory and the on-device cache.
4. **Sights and places to eat are distinguished by shape, colour and a word**, never colour alone:
   on the map a sight is a green circle and a restaurant or café an orange rounded square, with a
   legend and the kind in the stop details; in the day list each stop carries an "Attraction",
   "Restaurant" or "Café" tag, and a place to eat has an orange accent and square number. Screen
   readers hear the kind in each stop's description.

## Alternatives

| Alternative | Why not |
|---|---|
| Delete by long-press or swipe on the trips list | Hidden and easy to trigger by accident; the owner asked for it in the trip's settings. |
| Delete the old plan when new proposals are asked for | Loses the places the user added; the owner wants to choose again, not lose the current plan. |
| Different map icons (glyphs or images) | Needs an icon set or native assets; a shape and colour change is enough and stays within Expo defaults. |

## Consequences

- The proposals screen is now a step in a trip's life, reached from settings, not the front door.
- Deleting is permanent and cannot be undone; the confirmation says so. Price records no longer
  exist (ADR 017), so nothing else is affected.
- The wider direction (a history of past trips) is unchanged: ADR 006 governs it (built on
  2026-11-13, awaits acceptance).
