# ADR 003 — Remove opening hours from scope; attraction selection rule

- **Status:** Accepted on 2026-11-12 (owner instruction).
- **Date:** 2026-11-12
- **Related:** [`../product-brief.md`](../product-brief.md), [`../data-model.md`](../data-model.md),
  [`../spikes/s2-data-findings.md`](../spikes/s2-data-findings.md),
  [`002-api-strategy.md`](002-api-strategy.md)

## Context

Spike S2 imported the five pilot countries from Geofabrik extracts and measured them (see the
findings note).

1. **Opening hours are thin.** Restaurants carry `opening_hours` in 45–49% of cases in Austria,
   Czechia and Hungary, 17% in Italy and 13% in Japan. Attractions carry it in 1–4%. The owner
   does not need opening hours in the product.
2. **Most "attractions" are not sightseeing.** The first S2 query counted every `historic=*`
   object. The subclass breakdown shows the large classes are wayside shrines, wayside crosses,
   boundary stones, bomb craters and memorials, for example 17,129 wayside shrines, 15,338
   wayside crosses, 9,942 boundary stones and 8,096 bomb craters in Austria, and 34,969 wayside
   crosses and 24,030 boundary stones in Czechia. Real sightseeing candidates
   (`tourism=attraction`, viewpoints, museums, castles, ruins, archaeological sites) are one to
   two orders of magnitude fewer.

## Decision

### 1. Opening hours are out of scope

- The backend does not import, parse, store, evaluate or display opening hours.
- There is no opening-hours service, no three-state result, no user override of hours, no
  closed-place check in the validator, and no `OPEN_AT_SLOT` or `HOURS_UNKNOWN` reason code.
- Spike S4 (opening-hours parser) is removed. Phase 6 becomes "Restaurants in itineraries".
- The product therefore **cannot warn that a place is closed**, and an itinerary may include a
  place that is closed at the planned time. The product brief states this plainly.
- Meal timing uses fixed meal windows and venue type only.

### 2. Attraction selection rule (proposed values, tuned in Phase 2)

Do not import these as places:

- `historic=wayside_shrine`, `historic=wayside_cross`
- `historic=boundary_stone`
- `historic=bomb_crater`
- `historic=memorial`, **unless** the object also carries a `wikidata` tag (the proxy for
  "most memorials are excluded; notable ones are kept")

Kept by default: `tourism=attraction|museum|gallery|viewpoint|zoo|theme_park|aquarium` and the
other `historic=*` values. Open question for Phase 2: whether `historic=yes` and
`historic=building` (up to 25,110 in Italy) pass the rule; decide from a sample, not in advance.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Keep hours as an optional soft signal | The owner does not need it; it carries a parser dependency, a spike and a data table for data that is mostly missing. |
| Keep every `historic=*` object and rank them down | Pollutes candidates and database size with objects that are not visits. |
| Drop all `historic=memorial` | Loses notable memorials; the `wikidata` tag is a cheap, measurable signal. |

## Consequences

- Documents changed in the same commit: product brief, KPIs, app plan, architecture, data
  model, ADR 001 and 002, API evaluation.
- Removed from the data model: `geo.place_hours`, `hours_status`, `hours_note`.
- Removed KPIs: opening-hours coverage and parse rate.
- If opening hours are wanted later, a new ADR must reintroduce the table, the parser and the
  validator rule together.
- The Phase 2 import report counts excluded objects per class so the rule can be reviewed.
