# ADR 012 — Phase 2 choices: data, import and search

- **Status:** Implemented in Phase 2 on 2026-11-12. Items marked **owner decision** differ from
  the literal wording of the Phase 2 brief or of `data-model.md` and need a yes or a change.
- **Date:** 2026-11-12
- **Related:** [`002-api-strategy.md`](002-api-strategy.md), [`005-free-managed-hosting.md`](005-free-managed-hosting.md),
  [`006-past-trips-archive.md`](006-past-trips-archive.md), [`009-region-readiness-thresholds.md`](009-region-readiness-thresholds.md),
  [`011-attraction-selection-rule-v2.md`](011-attraction-selection-rule-v2.md), [`../data-model.md`](../data-model.md)

## Context

Phase 2 builds the persistence layer, the region import, the data quality report with the ADR 009
gates, the gazetteer, destination and place search with Photon as the only external fallback, a
seed trip, and CRUD for trips, user places and itinerary items. CLAUDE.md rule 4 asks that an
external provider is adopted only with an ADR that cites its terms and the date they were read.

## Sources and terms read

Verification marks as in `api-evaluation.md`: ✅ read on 2026-11-12; ◐ partly; ✗ not read.

| Source | Status | What was read, and what was not |
|---|---|---|
| Photon public instance (`photon.komoot.io`) | ✅ terms, ◐ API | Terms on the home page: "You can use the API for your project, but please be fair - extensive usage will be throttled. We do not guarantee for the availability and usage might be subject of change in the future." Repository README: "as long as the number of requests stay in a reasonable limit. Extensive usage will be throttled or completely banned. We do not give guarantees for availability and reserve the right to implement changes without notice." API parameters (`q`, `limit`, `lang`, `lat`, `lon`, `layer`, `countrycode`, `bbox`) from `docs/api-v1.md`. **No numeric limit is published**, so the daily budget (300 calls) is our own. A live call to `/api` timed out from the development environment, so the contract fixture follows the documented response format and is not a recording. |
| GeoNames | ✅ terms, ✗ dump readme | `geonames.org/export/`: data is free, CC BY 4.0, credit with a link, commercial use allowed, "as is". The dump readme and files are on `download.geonames.org`, which the development environment could not reach, so the **file layouts are not verified**. The importer reads `countryInfo.txt` columns by the names in its own header line and stops with a line number if any other file has an unexpected column count. File names (`countryInfo.txt`, `admin1CodesASCII.txt`, `admin2Codes.txt`, `cities1000.zip`) are recalled from the standard readme and a search-result mirror of it. |
| Geofabrik | ◐ owner-reported | The assistant could not read the host (not reachable from the development environment). On 2026-11-12 the owner copied the download-server text: free download of daily-updated OSM excerpts; "All OpenStreetMap derived data on the download server is licensed under the Open Database License 1.0. You may use the data for any purpose, but you have to acknowledge OpenStreetMap as the data source. Derived databases have to retain the same license." The owner found no limit or request about automated downloads. The workflow sends an identifying User-Agent, downloads one extract and one `.poly` file per manual run and keeps nothing. Both downloads worked in the first real run (Austria, 2026-11-12), so the `.poly` URL pattern is confirmed. Re-check the page before scheduling imports or raising volume. |
| Wikidata | not used | Not fetched in Phase 2. `geo.place_signal.wikidata_id` is the OSM tag; `sitelink_count` is null (unknown). |

## Decisions

1. **Enumerations are `text` columns with CHECK constraints**, not PostgreSQL enum types: adding
   a value is a constraint change, not a type migration.
2. **No foreign keys between `app` and `geo`.** `geo` is rebuilt by imports (ADR 005) and a plan
   must survive that (ADR 006). Columns that name a geo row are checked for shape in the
   database and for existence by the API when written; items keep a name and point snapshot. All
   foreign keys inside each schema are real. A test fails if a constraint crosses the schemas.
   **Owner decision:** `data-model.md` drew these as foreign keys.
3. **Place identifiers are stable** (a deterministic UUID, RFC 9562 version 8, of the region and the
   OSM reference). **Amended 2026-11-12 after the second Austria import:** this decision first said
   that places are never deleted and only deactivated. That kept the roughly 19,000 places a rules
   change had removed, and rewriting every row on each import left a dead copy of each, so Austria
   measured 87 MB where about 40 MB was expected. Now: a place missing from the latest extract is
   deleted (with its source, signal and profile rows) unless an itinerary item or price record
   still names it, in which case it stays with `is_active = false` until nothing names it; rows that
   did not change are not written; the tables are vacuumed after the commit and rewritten after a
   large clean-up. Migration 0004 renames `last_seen_import_run_id` to
   `last_changed_import_run_id`, because it no longer records every run that saw a row.
4. **The import is one transaction per region** into `geo`, preceded by a committed
   `geo.import_run` row so a failed run is recorded. The report is built from counters while
   streaming and checked against the database before the commit; a mismatch aborts the import.
   It needs a session-mode connection (the CLI refuses port 6543).
5. **Gate 6 is judged on the size after the vacuum** (amended 2026-11-12): inside the import
   transaction the files still hold the dead row versions the import is about to free, and the
   third Austria report showed 87 MB there against 33 MB after the vacuum. The other five gates
   are decided in the transaction; after the vacuum gate 6 is recomputed, and the stored report
   and the region status are updated if the outcome moves.
   **Gates are computed on exact ratios**, not on rounded display values (a test caught 89.98 %
   rounding to 90.0). A region becomes `available` only if all six gates pass, otherwise
   `disabled`; there is no manual override. **Gate 5 uses the Latin-letter share** because no
   display rule exists yet (`DISPLAY_RULE_IMPLEMENTED = False`), so Japan fails it as ADR 009
   expects. The gate 6 size is the whole `geo` schema (all regions), in decimal megabytes.
6. **`default_visit_minutes` stays null.** The category rule table is Phase 4 work and any number
   now would be a guess. Consequence: adding an item to an itinerary needs an explicit duration
   unless the place has one.
7. **`geo.place_source.tags` holds the tags the importer reads**, unmodified, but not
   `name:*` and `addr:*` (they are in `names_i18n` and `address`) and never `opening_hours`
   (ADR 003). The Lua style copies a fixed allow-list of keys.
8. **Provider cache and call counters live in `app`** (`app.provider_cache`,
   `app.provider_usage`): they are not rebuilt by an import. Cached rows hold the provider's
   answer, never an installation identifier. The position sent to Photon is rounded to 0.1°.
9. **Photon is called only when asked and only when nothing local matches** (`include_external`),
   through `PhotonClient`: identifying User-Agent, 4 s timeout, 7-day cache, atomic daily budget
   of 300 calls (our figure), a 60 s pause after a failure and 5 min after HTTP 429. Every failure
   becomes a status in the response; local results always come back. In the `test` environment it
   is off unless a stub transport is injected, so tests cannot reach the network.
10. **Search endpoints need an installation token** (they can spend the Photon budget); `GET
    /v1/regions` and `GET /v1/attributions` do not.
11. **Installations get a row lazily**, on the first authenticated call that touches the
    database. Registration stays stateless (ADR 010).
12. **Trips refuse destinations whose region is not `available`** (409 `region_not_available`).
    Search still lists them, with `planning_available = false`.
13. **Two additions that are not in `data-model.md`:** an *empty manual itinerary* endpoint
    (the only way to have a day to put items in before the Phase 4 engine exists; profile
    `manual`), and trip fields `destination_name` and `destination_point` (the snapshot ADR 006
    says the archive keeps). **Owner decision:** both are small and can be removed.
14. **Seed data is built from the imported data**, never typed in: the city with the most
    attractions, its best-scoring named attractions, one restaurant. Durations are flat
    placeholders (60 minutes), the only invented numbers, and every item carries the reason
    `SEED_DATA`. The seed trip belongs to a fixed seed installation and is invisible to others.
15. **Past trips are archived on request**; the automatic archive "after the last day" (ADR 006)
    is not built (it needs a scheduled job).
16. **`app.price_record` exists with its constraints, but has no endpoints** (Phase 8).

## Alternatives considered

| Alternative | Why not |
|---|---|
| Cross-schema foreign keys | A re-import would be blocked by, or delete, user data |
| Python parsing of OSM instead of osm2pgsql | Geometry assembly (multipolygons, areas) is what PostGIS and osm2pgsql already do and S2 used it |
| Selection rule in Lua | Not unit-testable without the tool, and exclusions could not be counted per class |
| Wikidata fetch at import | Another provider, another rate rule, no evidence yet that it improves selection |
| Photon on every keystroke | "Extensive usage will be throttled"; the endpoint is for a submitted search |

## Consequences

- The first real import is the first time the pipeline meets a real extract. Run Austria first
  (smallest S2 footprint), read the report and the review sample, then the others.
- Planner behaviour of the trigram indexes at the size of a real country is unmeasured: the
  tests prove the indexes can serve the queries, not that the planner picks them.
- Supabase specifics unverified from here: PostGIS in the `extensions` schema (all connections
  put `public, extensions` on the search path), and the session pooler allowing temporary tables
  and advisory locks as the loader needs.
