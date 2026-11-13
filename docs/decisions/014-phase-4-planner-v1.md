# ADR 014 — Phase 4: planner v1 (attractions and days)

- **Status:** **Proposed** on 2026-11-12. The code is built and tested
  (`services/api/src/detour_api/planner/`); the owner confirms or changes the decisions below,
  especially the weights, which have only been tried on synthetic fixtures.
- **Date:** 2026-11-12
- **Related:** [`003-scope-opening-hours-and-attractions.md`](003-scope-opening-hours-and-attractions.md),
  [`004-fossgis-valhalla-demo-server.md`](004-fossgis-valhalla-demo-server.md),
  [`006-past-trips-archive.md`](006-past-trips-archive.md),
  [`011-attraction-selection-rule-v2.md`](011-attraction-selection-rule-v2.md),
  [`013-phase-3-travel-time-service.md`](013-phase-3-travel-time-service.md),
  [`../spikes/s5-sequencing-findings.md`](../spikes/s5-sequencing-findings.md) (D7),
  [`../architecture.md`](../architecture.md) section 5, [`../kpis.md`](../kpis.md)

## Context

Phase 4 (`docs/app-plan.md`, build prompt 5) asks for the deterministic planning engine for
attractions and days: two meaningfully different itineraries for a **city** from two strategy
profiles of one engine, a diversity check, the baseline sequencer behind the `Sequencer`
interface, visit durations from a category table, transfers from the travel-time service with
their label, an independent validator, reason codes through fixed templates, and the engine,
configuration and data versions on every itinerary. Inputs are the trip's city, its length, an
optional start date and the currency; nothing else is a user input in the MVP (build prompts,
section 4). Out of scope: restaurants, recalculation after edits, areas, public transport,
weather, opening hours.

## Decision

### 1. Shape

`engine.generate(request, candidates, travel_source, config)` is a pure function: no database, no
clock, no randomness. `repo/planning.py` reads the inputs before it and writes the result after
it; `planner/service.py` runs the three steps (read in one transaction, plan outside any
transaction because it may wait on the routing provider, write in one transaction) and logs the
timing of each (the KPI source).

### 2. Candidates

Active, named attractions of the destination's region (`geo.place`, `kind = 'attraction'`) within
the widest profile radius (15 km) of the trip's destination point, with their `geo.place_signal`
flags. Only places of the one region, so the plan has one data version (`import_run_id`).

### 3. Scoring (`planner/scoring.py`, `planner/config.py`)

All integer arithmetic (floor division), so a value is identical on every machine.

    base  = 10 + notability + category points
    value = base x 10 x distance factor x repeat-category factor

- **Notability** comes from what the import has: the OSM `wikidata` tag (30), `wikipedia` (20),
  `heritage` (20), `tourism=attraction` (10). The Wikidata **sitelink count** adds 10/20/30 at
  5/20/50 sitelinks when known, but **the import does not fetch it yet** (data model section 2.8),
  so today notability rests on tags only. There are no ratings.
- **Category points:** museum, castle, palace 30; archaeological site 25; attraction, gallery,
  zoo, aquarium, viewpoint, fortress, monastery, abbey, temple 20; theme park, fort, ruins,
  church, city gate, tower, aqueduct 15; monument 10; chapel, statue, fountain, memorial 5; any
  other 10.
- **Distance factor:** 100 % at the destination point, falling linearly to the profile's
  `edge_value_pct` at its radius; nothing beyond.
- **Repeat category:** the n-th best place of a category keeps a share of its value (below).

### 4. Two strategy profiles

| | Essentials | Wider |
|---|---|---|
| Radius | 5 km | 15 km |
| Visits and transfers end by | 18:00 | 19:00 |
| Travel weight (value per minute) | 10 | 4 |
| Value kept at the radius edge | 50 % | 85 % |
| Same category, 1st/2nd/3rd/4th+ | 100/85/70/60 % | 100/60/40/30 % |
| Candidates planned with | 20 + 12 per day, at most 150 | same |

Days start at 09:00 at the first visit (no accommodation, product brief section 9). The day
window is 09:00–21:00; the profiles stop earlier because **no meal time is reserved yet**
(Phase 6), and a note says so.

### 5. Visit durations (`planner/durations.py`)

A category table of our own (no free source has visit durations), versioned
(`DURATIONS_VERSION`, part of the configuration version): for example museum 90, castle and
palace 75, church 30, viewpoint 20, statue 10, zoo 150, theme park 240 minutes; 30 for a category
not listed. Each generated item is stored with `duration_source = 'category_default'`; **the user
changes any item's duration** with `PATCH /v1/items/{id}` (it becomes `user`). The table is
engine configuration, not data: `geo.place.default_visit_minutes` stays null, so changing the
table needs no re-import. **Changed from Phase 2:** an imported attraction added by hand without a
duration now gets its category default instead of `422 duration_required` (restaurants and user
places still need one).

### 6. Sequencer

The heuristic of spike S5 is the only implementation of the `Sequencer` interface (D7): greedy
best-gain insertion (with each candidate's best insertion per day cached and recomputed only for
the day that changed), then 2-opt within a day, relocation within and between days, swapping a
planned visit for an unplanned one, and re-insertion, until nothing improves. It maximises
`sum of values - travel weight x travel minutes` with each day's visits plus transfers inside the
profile's day. Every move strictly improves the objective, so it terminates. Days are
interchangeable (no opening hours), so they are ordered fullest first; days left empty are last.

### 7. Travel times

- **Mode:** walk if the straight line is at most 2 km, else drive; a pair always has the same mode.
- **Planning** reads the cache only (`use_provider=False`) for a sparse cell set: each candidate
  against its 6 nearest others (ADR 013 asks for sparse sets). Any other pair is the labelled
  estimate. No provider call happens while plans are being searched.
- **Transfers:** once both plans exist, the travel-time service is asked for the legs they use
  (cache first, then FOSSGIS within its rules), with each leg's source's nearest others in the
  same mode as extra targets of the same one-source request: no extra request, and the cache warms
  for the next plan of the city. The whole generation may wait at most
  `DETOUR_PLANNER_PROVIDER_MAX_SECONDS` (3 s) on the provider; legs not reached stay estimates.
- **Fitting:** each day is scheduled with the transfers it got. If routed times no longer fit the
  day, the lowest-value visit is dropped until it does (note `VISITS_REMOVED_AFTER_ROUTING`). A leg
  joined by such a drop is asked for in up to two follow-up calls.
- **Labels:** every transfer is stored with its `routed` or `estimated` label, and the plan
  carries a note with the number of estimated transfers. The validator checks each transfer
  against what the source returned.

### 8. Diversity gate

Two plans are distinct when both have visits, the Jaccard similarity of their visit sets is at
most 0.6 (product brief section 5), and the second has at least half as many visits as the first.
If the gate fails, Wider is solved again with the visits Essentials has worth 50 %, then 20 %, then
0 % of their value. If it still fails, **one plan is returned** with the note `SINGLE_PLAN`, which
gives the number of sights and the overlap. For a city destination the "different allocation of
days to cities" alternative of the brief cannot apply (one city), so only the overlap counts. The
gate is checked again after routing (a dropped visit can change the overlap).

### 9. Validator (`planner/validator.py`)

Independent of the scheduling code. It fails the plan (a bug: `500 plan_invalid`, never shown) on:
wrong day count, order or dates; a visit that is not one of the given candidates, or with another
name, point or category; a place twice; a duration that is not the category default, or an end
that is not start plus duration; an item before 09:00 or after the profile's end; overlapping
items or a gap shorter than the transfer; a missing or extra transfer; a transfer whose mode
breaks the walking rule, whose minutes are not its seconds rounded up, or whose seconds, metres or
label differ from what the travel source returned; a visit without a reason, or a reason or note
without a template; statistics that do not match. For the generation: missing versions, a
duplicate profile, two plans that are not distinct, or a second plan that is too small.

### 10. Reason codes and notes (`planner/reasons.py`)

Fixed templates only. Item codes (stored in `app.itinerary_item.reasons`): `WIKIDATA_LINKED`,
`WIKIPEDIA_ARTICLE`, `WIKIDATA_SITELINKS`, `HERITAGE_LISTED`, `TAGGED_TOURIST_ATTRACTION`,
`HIGHLIGHT_CATEGORY`, `NEAR_CENTRE`, `NEAR_PREVIOUS_ITEM`, `ADDS_VARIETY`, and `NAMED_SIGHT` when
none applies. Plan notes (stored with their parameters in `app.itinerary.summary`) describe the
profile, the diversity result, empty days, estimated transfers, visits dropped after routing, and
four fixed statements: ranking from tags, durations are defaults, opening hours are not checked,
meals are not planned yet. Impossible requests use issue codes (`NO_CANDIDATES`,
`VISITS_LONGER_THAN_DAY`) in a `422 planning_impossible` body with an `issues` list. All are
rendered when read, so wording can change without a migration.

### 11. Determinism and versions

Candidates in place-id order, every tie broken by place id, integer arithmetic, no clock, no
randomness. Stored on every itinerary: `engine_version` (`planner-1.0.0`), `config_version`
(`2026-11-12.2+durations-2026-11-12.1`), `import_run_id`, and `seed` = 0 (no randomness is used;
the column is filled as the determinism rule asks). The one input that can differ between two
runs on the same data is what the travel source returns (a time that has since been cached, or a
provider that did not answer in time); each transfer records which it got. Golden files
(`tests/fixtures/planner/golden/`) pin the output byte for byte for five fixture trips.

### 12. API

- `POST /v1/trips/{id}/itineraries/generate` → `201` with the generation (`distinct`,
  `jaccard_permille`, notes) and its one or two itineraries. **A new generation deletes the
  trip's earlier engine proposals that were not selected**; a selected itinerary and manual ones
  stay, within the limit of 5 per trip. `409` for a past trip, a region that is not available or
  the limit; `422 area_not_supported` for an area; `422 planning_impossible` with the exact reason.
- Reads (`GET /v1/itineraries/{id}`, `GET /v1/trips/{id}/itineraries`) now include the
  generation id, seed, diversity score, notes and statistics, and per item the rendered reasons and
  the transfer to the next item.
- **Hand edits do not recompute transfers** (recalculation is Phase 7): a transfer that no longer
  joins an item to the next one is deleted, so a stale time is never shown.

## Measured (2026-11-12, Claude Code cloud container, 4 CPUs, synthetic fixtures)

| Trip | Engine, both profiles | Visits E / W | Day utilisation E / W | Travel share E / W | Jaccard |
|---|---:|---:|---:|---:|---:|
| 3 days, 180 sights | 54 ms | 32 / 38 | 74.0 / 82.3 % | 10.6 / 15.0 % | 0.59 |
| 7 days, 180 sights | 176 ms | 77 / 86 | 74.0 / 81.8 % | 10.6 / 13.1 % | 0.51 |
| 14 days, 180 sights | 610 ms | 140 / 109 | 63.2 / 52.0 % | 11.0 / 11.0 % | 0.46 |
| 1 day, 8 sights (incomplete data) | 2 ms | 7 / 5 | 66.3 / 55.8 % | 8.9 / 6.7 % | 0.50 |
| 3 days, 8 sights | 1 ms | 8 / — | 22.4 % | 7.0 % | one plan |

A dense set of 2,000 synthetic sights took 0.07 s (3 days), 0.27 s (7 days) and 0.48 s (14 days).
Through the API with the database, a 7-day trip over about 190 sights took 0.37 s, without the
routing provider (it is off in tests). Against the KPIs: every plan passed the validator; the
diversity target holds on every fixture with two plans; travel share is far under 25 %; day
utilisation is inside 60–90 % for the 3- and 7-day trips, not for 14 days in one city (Wider runs
out of sights Essentials does not already have) nor for the 8-sight town.

**Not measured:** real imported data; Render's free tier; the provider share of the 5 s budget
(capped at 3 s by configuration, which leaves the engine and the database about 2 s).

## Alternatives

| Alternative | Why not chosen |
|---|---|
| OR-Tools | D7 (spike S5): slower, not repeatable at its limits, and can return no plan |
| Cluster candidates into days first (k-means or similar), then sequence each day | An extra tuning surface; insertion already seeds each day with a top sight and grows it with near ones |
| Ask the provider for the whole sparse set before planning | About one request per candidate (ADR 013): 60 to 150 requests at 1 per second, far beyond the 5 s budget |
| Fill `geo.place.default_visit_minutes` at import | Every duration change would need a re-import of every region |
| Refuse a new generation when 5 itineraries exist | Proposals are disposable until one is selected; replacing them keeps the trip within its limit |
| Reserve meal blocks now | Restaurants and meal windows are Phase 6; the earlier day end leaves the time free |

## Consequences and open items (owner)

1. **Tune the weights on real data** (app plan, Phase 4 risk): once Austria is imported, generate
   plans for two or three Austrian cities and review them. Changing a number means a new
   `CONFIG_VERSION` and new golden files.
2. **Visits per day are many** (10 to 13 on the fixtures) because the durations are short for
   statues, chapels and monuments. Confirm or change the duration table.
3. **Notability rests on OSM tags** until Wikidata sitelink counts are imported (a Phase 2
   carry-over). The code uses them as soon as they exist.
4. **First plans of a city are mostly estimated**: with an empty cache, 3 s buys about 10 to 13
   provider requests (burst of 10, then 1 per second). The routed share (KPI ≥ 95 %) can only be
   met once the cache has warmed. The walking estimate is 1.8 x the straight line (ADR 013).
5. **Long trips in one city** run out of distinct sights; the area destinations of Phase 6 address
   this.
6. Confirm that a new generation may delete unselected proposals, and that hand-added attractions
   take their category's default duration.

## Addendum (2026-11-13): Phase 6

[ADR 016](016-phase-6-meals-and-area-destinations.md) amends this ADR: the profiles' day ends move
to 20:30 (Essentials) and 21:00 (Wider) because meals are now planned; each profile keeps time for
its meals and some unplanned time; the diversity gate also accepts plans whose base cities differ;
`422 area_not_supported` is gone (areas are planned; areas in Japan get `422 area_single_city_only`);
`NO_MEALS_YET` and `VISITS_REMOVED_AFTER_ROUTING` are replaced by `MEALS_FROM_MAP_DATA` and
`VISITS_REMOVED_TO_FIT` (the old templates stay so stored plans still render); the engine is
`planner-2.0.0`. The trip currency is no longer an input ([ADR 017](017-no-budgets-currencies-or-prices.md)).
