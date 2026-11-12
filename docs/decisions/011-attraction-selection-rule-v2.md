# ADR 011 — Attraction selection rule, version 2

- **Status:** **Proposed**, implemented in Phase 2 (rules version `2026-11-12.4`). The first
  real import (Austria, 2026-11-12) has been read; the owner decided on three more excluded
  classes (see "Update after the first real import"). The rest of the rule is not yet confirmed.
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
| `historic=tree_shrine`, `historic=heritage`, `historic=heritage_building` | **Excluded** (owner decision, 2026-11-12, after the Austria import). Matched on the cleaned value (lower case, other characters as `_`), so `Heritage Building` is caught too | `adr003_excluded_class` |
| Any `tourism` attraction class or allow-listed `historic` value **without a name** | **Excluded** (owner decision, 2026-11-12: "only cities and tourist spots mostly"). An unnamed "viewpoint" cannot be shown in an itinerary | `attraction_without_name` |
| `historic=*` values **not on the tourist allow-list** | **Excluded and counted by class**. The allow-list (`TOURIST_HISTORIC`): castle, fort, fortress, palace, ruins, archaeological_site, monument, manor, monastery, abbey, church, chapel, temple, city_gate, tower, aqueduct, viaduct, bridge, battlefield, fountain, statue, technical_monument, place_of_worship, cemetery. Examples dropped: milestone, cannon, gallows, mine, quarry, locomotive, hollow_way, military, wayside_chapel, pillory, `railway` (track segments) | `historic_class_not_tourist` |
| `historic=citywalls` | Kept only with a name and a notability tag (walls are mapped in many short pieces); joins the reviewed generic classes | `generic_class_without_name_and_notability` |
| `historic=memorial` | **Kept only with `wikidata` and a name, and not of a small-object subtype** (`memorial` = `plaque`, `blue_plaque`, `stolperstein`, `ghost_bike`, `bench`, `grave`, `war_grave`, `cross`, `stone`) | `memorial_without_wikidata`, `memorial_without_name`, `memorial_excluded_subtype` |
| `historic=yes|building|stone|tomb|citywalls` | **Kept only with a name and at least one notability tag** (`wikidata`, `wikipedia` or `heritage`) | `generic_class_without_name_and_notability` |
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

## Update after the first real import

Austria was imported on 2026-11-12 (OSM snapshot 2026-11-11). What the report and the review
sample showed:

- **The rule reproduces the spike.** The ADR 003 classes, restaurants and `tourism=attraction` match
  S2 count for count (17,129 shrines, 15,338 crosses, 9,942 boundary stones, 8,096 bomb craters,
  7,822 memorials without Wikidata). The new rules removed 3,780 more objects: 3,331 from the five
  generic classes and 449 from the stricter memorial test.
- **All six gates passed** (named attractions 12,265, 66.1 %; restaurants 26,504).
- **Owner decision:** remove `tree_shrine` (198 kept), `heritage` (486) and `heritage_building`
  (115). The categories come from the report; the raw tags behind `heritage` and
  `heritage_building` were not in the review sample (only the six reviewed classes are sampled), so
  the matching is on the cleaned value. 799 places leave the data at the next import.
- **Reading the sample, the two-signal test works as intended** for `historic=building`, `tomb`,
  `stone` and `railway`: kept objects are named and documented (Neutor, Villa Bader, Mausoleum
  Dreher, Tauernbahn), excluded ones are mostly unnamed footprints, railway segments called
  "Landstraße" and the like. A few named objects without a documentation tag are dropped (a
  building called "Burgpalast", a stone called "Opferstein"); that is the price of the rule.
- **Memorial subtypes: one point for the owner.** The subtype exclusion also removes memorials that
  have a name, a Wikidata item and often `heritage=2`, for example a "Kaiser Franz Josef Denkmal"
  (`memorial=stone`) and several named plaques. Whether to exempt memorials that carry `heritage`
  from the subtype test is open; it would be a small rule change (rules version bump).
- **Kept but unreviewed:** the other `historic=*` values (for example `pillory` 132, `citywalls`
  236, `cannon` 91, `milestone` 60) are kept by default and not sampled.
- A bug was fixed on the way: excluded objects in `review-sample.json` were named `N/123` while
  kept ones were `node/123`; both now use `node/123`.

## Update: "only cities and tourist spots" (rules version 2026-11-12.3)

After reading the Austria import the owner asked for a leaner data set: tourist spots rather than
every small object. Decided and implemented: attractions need a name; `historic=*` is an allow-list
(`TOURIST_HISTORIC`), not a deny-list; `historic=railway` leaves; `citywalls` need a notability
tag. Applied to **every** region (one global rule; a "compact" mode per import was considered and
not built, see ADR 012). From the category table of the Austria database the new rules keep about
11,300 attractions (of 18,543 before the 2026-11-12.2 change), about 39 % fewer. Restaurants and
cafes are untouched by these rules and make up about 70 % of what is left, so this alone saves
roughly 16 % of Austria's places.

Because the allow-list was chosen from Austria's categories only, other countries will have
`historic=*` values it does not list. They are not lost silently: the import report counts every
class under `historic_class_not_tourist`, and a class can be added to the list. Places of worship
mapped only as `amenity=place_of_worship` (most Japanese temples and shrines, most Italian
churches) were never imported; that is a gap for Italy and Japan, not decided here.

Gate 4 (ADR 009) asks for 40 % of attractions to be named; with this rule it is always 100 %.
The count gate (5,000 named attractions) is the one that can now fail.

**Restaurants and cafes: kept only near attractions or towns (rules version 2026-11-12.4).**
Restaurants and cafes were 59 % of Austria's places. They are now kept only when within **500 m**
of an attraction the rules keep, or within **1,500 m** of the centre of a gazetteer town with at
least **5,000** inhabitants (`RESTAURANT_RADIUS_M`, `TOWN_RADIUS_M`, `TOWN_MIN_POPULATION` in
`importer/selection.py`; the check is `importer/proximity.py`, great-circle distance on a grid).
Cafes follow the same rule. Everything else is counted in the report as
`restaurant_not_near_attraction_or_town`, and the report states the rule and the number of
attractions and towns it used.

The radii come from a measurement on the Austria database (2026-11-12), counting the restaurants
and cafes that were then in it:

| Radius to an attraction | Restaurants kept (of 21,038) | Cafes kept (of 5,466) |
|---|---|---|
| 300 m | 9,298 (44 %) | 3,755 (69 %) |
| 500 m | 10,827 (51 %) | 4,093 (75 %) |
| 1,000 m | 13,580 (65 %) | 4,588 (84 %) |

(each figure includes the town rule). The town rule adds about 1,100 restaurants and 390 cafes to
what the attraction rule keeps at 500 m. Leaving viewpoints out as anchors changes the counts by
only 3 to 8 %, so they stay anchors. 500 m is about a six-minute walk, enough for the planner to
find several candidates near a sight; at 300 m the pool gets thin. Expected effect on Austria:
about 14,900 restaurants and cafes instead of 26,500, and about 26,200 places in all instead of
45,000 (an estimate of about 40 MB instead of 71 MB, to be confirmed by re-importing).

Consequences:

- **The import depends on the gazetteer.** Towns come from `geo.city`, so import the gazetteer
  first (the workflow does). Without it the rule uses attractions only, the report says so in its
  warnings, and the result differs from a run with the gazetteer; run the import again after
  loading it.
- **A remote restaurant is not in the data.** A user can still add it: search through Photon, or a
  manual pin, saved as a user place (`docs/data-model.md`). The planner (Phase 6) will propose meal
  stops only from the imported ones.
- **Gate 3 (5,000 restaurants) and gate 2 (30 % with a cuisine) are now measured after this rule.**

## What this does not prove

- **The rule was written without seeing a real extract** (the development environment could not
  reach Geofabrik). Austria has now been read (see the update above); Czechia, where memorials
  dominate, has not. The memorial subtype list is a list of plausible OSM values (`memorial=*`),
  not one checked against the Czech data. Read the Czechia sample before enabling it.
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
