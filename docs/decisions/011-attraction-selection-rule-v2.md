# ADR 011 — Attraction selection rule, version 2

- **Status:** **Proposed**, implemented in Phase 2 (rules version `2026-11-12.1`). The owner is
  asked to confirm it after reading the review sample of the first real import (see "How to
  review"). It was **not** reviewed against a sample of real data (see "What this does not
  prove").
- **Date:** 2026-11-12
- **Related:** [`003-scope-opening-hours-and-attractions.md`](003-scope-opening-hours-and-attractions.md)
  (the rule and its open questions), [`009-region-readiness-thresholds.md`](009-region-readiness-thresholds.md),
  [`../spikes/s2-data-findings.md`](../spikes/s2-data-findings.md)

## Context

ADR 003 removed wayside shrines and crosses, boundary stones, bomb craters and memorials without a
`wikidata` tag. Spike S2's rerun showed two things it left open:

1. In Czechia the `wikidata` tag is common on memorials, so about 22,800 memorials (roughly half
   of the country's attractions) survived. ADR 003's addendum asked for a stricter test, "for
   example also requiring a name and excluding Czech war-grave and local-memorial classes by a
   sample review".
2. `historic=yes` (759 to 9,158 per country), `historic=building` (Italy 25,110), `historic=railway`
   (Austria 1,608), `historic=stone` (Czechia 687) and `historic=tomb` were still imported, and
   the ADR asked for a decision "from a sample, not in advance".

The task for Phase 2 asked for both decisions to be made and recorded.

## Decision

The rule lives in one function, `detour_api/importer/selection.py::decide`, and its version is
stored on every import run.

| Class | Decision | Reason code when excluded |
|---|---|---|
| `amenity=restaurant`, `amenity=cafe` | Kept as restaurants | n/a |
| `tourism=attraction|museum|gallery|viewpoint|zoo|theme_park|aquarium` | Kept, named or not | n/a |
| `historic=wayside_shrine|wayside_cross|boundary_stone|bomb_crater` | Excluded (ADR 003) | `adr003_excluded_class` |
| `historic=memorial` | **Kept only with `wikidata` and a name, and not of a small-object subtype** (`memorial` = `plaque`, `blue_plaque`, `stolperstein`, `ghost_bike`, `bench`, `grave`, `war_grave`, `cross`, `stone`) | `memorial_without_wikidata`, `memorial_without_name`, `memorial_excluded_subtype` |
| `historic=yes|building|railway|stone|tomb` | **Kept only with a name and at least one notability tag** (`wikidata`, `wikipedia` or `heritage`) | `generic_class_without_name_and_notability` |
| Every other `historic=*` value (castle, ruins, archaeological site, monument, fort, ...) | Kept | n/a |

An object that has both `amenity=restaurant|cafe` and a `historic` tag is a restaurant (a cafe in
a castle is a cafe). An object that would be kept but has no usable geometry is excluded as
`no_geometry`. Unnamed kept attractions stay in the data with a null name (unknown, never filled).

Categories stored on `geo.place`: the `tourism` or `historic` value, except `historic=yes` ->
`historic` and the other four generic classes -> `historic_building`, `historic_railway`,
`historic_stone`, `historic_tomb`, so that a category never reads as just "yes".

**Why these tests.** The aim in ADR 003 is to keep notable sights and drop objects that are not
visits. A name is what a visitor sees; a `wikidata`, `wikipedia` or `heritage` tag is the cheap
signal that somebody documented the object elsewhere. The memorial subtype list removes the small
objects (plaques, grave markers, stumbling stones, benches) that stay numerous even among
Wikidata-linked memorials. The generic classes need both signals because their tag says almost
nothing about what the object is.

**Ranking input.** `geo.place_signal.score` is a small additive count of those signals
(Wikidata 3, Wikipedia 2, heritage 2, `tourism=attraction` 1, named 1; restaurants score the same
way). The weights only order places and are tuned in Phase 4. `sitelink_count` stays null:
Wikidata is not fetched in Phase 2.

## How to review

Every import writes, next to its report, `review-sample.json`: for each of the six reviewed
classes, up to ten kept and up to ten excluded objects per reason, chosen by a hash of the OSM
reference (so the same objects appear on every run), with their imported tags. The report lists
excluded counts per class and reason. To change a decision, edit `selection.py`, raise
`RULES_VERSION`, update this ADR and run the import again; the result is repeatable.

## What this does not prove

- **No real extract was inspected for this decision.** The development environment could not
  reach Geofabrik, so the rule rests on the S2 counts, the ADR 003 addendum's own suggestion and
  the reasoning above. The memorial subtype list in particular is a list of plausible OSM values
  (`memorial=*`), not a list checked against the Czech data. Treat the rule as a proposal until
  the review sample has been read.
- Whether the rule brings Czechia below the point where memorials dominate is a number the first
  real import will give; it is not known now.
- Region readiness gate 4 (ADR 009) was measured before this rule. The first real import
  reports the gate values under the new rule; they may differ from ADR 009's table.

## Alternatives

| Alternative | Why not |
|---|---|
| Keep memorials only when they carry `wikidata` (ADR 003 as written) | Leaves Czechia's memorial flood |
| Drop every `historic=memorial` | Loses notable memorials; the owner's addendum asked for a stricter test, not removal |
| Drop the five generic classes entirely | Loses named, documented buildings and tombs; the two-signal test keeps them |
| Rank down instead of excluding | Pollutes candidates and database size (ADR 003) |
| Fetch Wikidata sitelink counts now and keep memorials above a threshold | Adds an external provider call and a threshold with no evidence; a later phase may add it |

## Consequences

- `docs/data-model.md`, the import report and `geo.import_run.rules_version` carry the version.
- The excluded-per-class counts in the report are the evidence the owner needs to accept or
  change the rule.
- Places excluded here cannot be found by search; a user can still add them as user places.
