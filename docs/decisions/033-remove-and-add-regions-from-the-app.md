# ADR 033 — Remove and add regions from the app

- **Status:** **Proposed** (owner request of 2026-11-17: "delete a region but keep past trips
  intact, and add a region through the app"). **Step 2 (removal) is built**, awaiting acceptance;
  checked by tests only, not tried on a device, not run against production. **Step 3 (adding a
  region from the app) is built the same way**, awaiting acceptance and **not yet tried against
  GitHub** (migration `0023` and the workflow change must be on the default branch first).
- **Date:** 2026-11-17
- **Related:** [`006-past-trips-archive.md`](006-past-trips-archive.md) (past trips are read-only),
  [`009`](009-region-readiness-thresholds.md) (size gate 6), [`011`](011-attraction-selection-rule-v2.md),
  [`025`](025-multilingual-place-names.md), [`022`](022-destination-and-attraction-photos.md)

## Context

Imported regions fill the 500 MB Supabase Free database (gate 6 allows 250 MB for all regions) and
only the workflow on GitHub can import or replace them. The owner wants to remove a region from the
app, with trips untouched, and later to import one (for example London) without going back to GitHub.

A trip refers to `geo` rows by identifier only (no foreign key) and keeps a snapshot of each stop's
name and point. What it still reads from `geo` is the place's photo, its English or alternate names,
and the default length of a stop.

## Decision (step 2: removal, built)

1. `GET /v1/regions/{id}/removal-preview` and `DELETE /v1/regions/{id}`, **owner only**: the caller's
   installation must be listed in `DETOUR_OWNER_INSTALLATION_IDS` (comma separated); with none
   listed nobody may (403 `not_owner`). Removal changes data every installation shares, and the API
   has no accounts.
2. **Kept:** every `geo.place` that an itinerary item, a past-trip record (`trip_visit`) or a
   display-name override names; every administrative area that a trip's destination or a name
   override names. They stay with `is_active = false` (no longer found by search, never offered to
   the planner), with their source rows, stored names and photo link. This is the importer's own
   "still named" rule (`importer/loader.py`), applied to the whole region, so a trip shows what it
   showed before.
3. **Removed:** all other places of the region with their source and signal rows (cascade), the
   other administrative areas, the stored names and lookups of places that are gone
   (`names.store.prune`), and the photo lookups of those places. Stored photo files and `geo.image`
   rows are left (small; no storage call in a request).
4. **Region row** stays, `disabled`, without a current data version; a later import fills it again,
   and the kept places become active again by their deterministic identifiers. Creating a trip in
   it is then refused like any unavailable region (409 `region_not_available`).
5. **Not touched:** the GeoNames gazetteer (countries, cities), the travel-time cache and every
   `app` row.
6. 409 `import_running` while any region is `importing`. A removal of 1,000 rows or more is
   followed by `VACUUM (FULL, ANALYZE)` after the commit, as in the importer.
7. The preview lists the caller's trips that use the region and an estimate of the space freed,
   from row sizes.

## Decision (step 3: add a region from the app, built)

The import needs a download of 100 MB to 2 GB and `osm2pgsql`; it cannot run on Render's free
service. The backend therefore **asks GitHub to run the existing "Import region" workflow** and the
workflow reports back.

1. **Provider: the GitHub REST API**, one call: `POST /repos/{owner}/{repo}/actions/workflows/
   {workflow}/dispatches` (`adapters/github.py`, behind an adapter with a User-Agent, timeout,
   daily budget of 20 calls in `app.provider_usage`, and a fallback state instead of an exception).
   Terms and limits read on **2026-11-17**:
   - Terms of Service, Section H: "Abuse or excessively frequent requests to GitHub via the API may
     result in the temporary or permanent suspension of your Account's access to the API." and
     "You may not share API tokens to exceed GitHub's rate limitations." Nothing in Section H
     addresses starting one's own workflow; the general rules apply.
     <https://docs.github.com/en/site-policy/github-terms/github-terms-of-service>
   - Rate limit: "All of these requests count towards your personal rate limit of 5,000 requests
     per hour." and secondary limits (80 content-generating requests a minute, 500 an hour). One
     owner-triggered call per import is far below both.
     <https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api>
   - Endpoint: body `ref` (required) and `inputs` (at most 25 properties); the answer is 200 with
     the run's URLs. The page names the `repo` scope for classic tokens and **does not name a
     fine-grained permission**: the token is a fine-grained token limited to this repository with
     Actions: read and write, and the owner confirms when creating it that dispatch is accepted.
     <https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event>
   - A workflow can be dispatched only if its file is on the default branch.
2. **The token** is `DETOUR_GITHUB_TOKEN`, a Render secret, never in the repository, logs, the app
   or the database. A GitHub answer's body is never logged.
3. **A catalog** (`importer/regions.py`) lists the regions that can be imported, with the extract's
   size when it was read. **Greater London** is added (`europe/great-britain/england/
   greater-london`, 124 MB, listed on Geofabrik's England page on 2026-11-17; the page shows no
   `.poly` for it, so the region's coverage polygon stays unknown and the importer warns). Great
   Britain (2.1 GB) is deliberately not offered: it would exceed the free database.
4. **Jobs**: `geo.import_job` (migration `0023`). `POST /v1/regions/{id}/import` (owner only)
   records a job, asks GitHub, and answers 202 with the job; a refusal, an unreachable GitHub or an
   exhausted budget make the job `failed` and the call 502. The workflow takes `region`,
   `gazetteer` and `job_id` and reports `running`, then `succeeded` (with whether the gates passed)
   or `failed` through `python -m detour_api.importer job`, with a fixed message and GitHub's run
   URL only. A job not reported on for 45 minutes is shown as **stalled** and no longer blocks a
   new request. One import at a time, also against a region already `importing`.
5. **`GET /v1/regions/catalog`** gives every catalog region's state, place counts, latest job, the
   database size against the 250 MB limit (gate 6), whether the caller `can_manage` and whether the
   server can start imports.
6. **App**: **More, Regions**: the list, a sheet per region with Import (or Import again) and Remove
   (preview with what is kept, then confirm), refreshing every 15 s while an import is under way.
   Settings now shows the full installation id, which the owner pastes into
   `DETOUR_OWNER_INSTALLATION_IDS`.
7. The workflow still runs by hand from the Actions tab (its inputs are now a text field and an
   optional `job_id`). An unknown region fails at the first import command.

Not built: offering "Import sights for London" on the new-trip screen when a destination has no
sight data; a removal's photo files; importing a region larger than the free database allows
(the import's own size gate decides, and the screen shows the usage).

## Alternatives

- Delete everything of the region, trips included: breaks photos and names on trips that exist.
- Copy a stop's category, default length and photo into the item first: more migration and a
  second source of truth; keeping the rows is cheaper and reuses an existing rule.
- Open to any installation: anyone with the APK could empty the shared data.

## Consequences

- Removing a region frees most of its space but not all: places that trips use stay, and so do
  photo files. A region used by many trips frees less.
- An upcoming trip to a removed region keeps its stops but cannot get suggestions, and its stops
  are no longer found as sights (they remain as stops). A past trip is read-only anyway.
