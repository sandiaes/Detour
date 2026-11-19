# ADR 033 — Remove and add regions from the app

- **Status:** **Proposed** (owner request of 2026-11-17: "delete a region but keep past trips
  intact, and add a region through the app"). **Step 2 (removal) is built** (cities added 2026-11-19), awaiting acceptance;
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
5. **Cities (amended 2026-11-19, owner request):** the GeoNames cities of the region's countries are
   removed too. In production `geo.city` was 28 of the 43 MB of imported data (Denmark's places
   were about 10 MB), so leaving it made "Remove" free far less than it showed. A city **stays**
   when another region with active places covers the same country (a country's cities are shared
   between its regions), and when anything in `app` still names it: a trip's city destination, a
   stop (`trip_stop.city_id`), a day's base city, a past-trip city record, a display-name override,
   or a kept place's `city_id`. Their stored names and photo lookups go with them
   (`names.store.prune`, `image_lookup`). The next import loads the cities again under the same
   GeoNames ids (the workflow's gazetteer step, on by default; the app's Import sends it on); an
   import without it leaves places without a `city_id` and the loader says so. Countries, currencies
   and the travel-time cache are not touched, nor is any `app` row. The preview gains
   `cities_removed` and `cities_kept`, and its space estimate includes the cities.
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
3. **A catalog** (`importer/regions.py`) lists the regions that can be imported, with no size: the
   download's size (Geofabrik's file, hundreds of MB to GB) says nothing about what a region takes in
   the database, so none is shown before an import (owner decision of 2026-11-17). **Greater London** is added (`europe/great-britain/england/
   greater-london`, a 124 MB download listed on Geofabrik's England page on 2026-11-17; Geofabrik's England table lists no `.poly` link for it; if the file is missing the region's
   coverage polygon stays unknown and the importer warns, which was not checked) **Eighteen countries were added on 2026-11-17** (links read the same day on Geofabrik's europe page,
   each a single extract): Belgium, Croatia, Denmark, Finland, Greece, Iceland, Ireland, Luxembourg,
   Malta, Netherlands, Norway, Poland, Portugal, Slovakia, Slovenia, Spain, Sweden, Switzerland.
   France and Germany (about 4.5 GB each) are left out until a smaller country has been imported and
   measured. A country appears once, because its code decides where a destination is planned; the
   catalog test enforces it. The list shows regions with data first, then the rest by name. **Paris and Berlin** are added as city extracts (Geofabrik
   `france/ile-de-france`, 324 MB, and `germany/berlin`, 95 MB; the region pages link `.poly`
   files, read 2026-11-17). A city extract claims its country's code, so the destination match is
   now also geographic: when a region's coverage polygon is known, a destination must lie inside
   it (5 km of slack for simplified polygons), otherwise Manchester would count as inside Greater
   London and Lyon inside Paris (`geo.region_for_country`, the destination search). A region with no
   polygon is still matched by country, so before a first import, and if the polygon cannot be
   loaded, a city extract still claims its whole country. Multi-city bases are still matched by
   country only. **Bordeaux (Aquitaine)** is added (2026-11-19; Geofabrik `france/aquitaine`, 283 MB, `aquitaine.poly` linked on its page, read the same day; no extract for Bordeaux alone). It claims France's code like Paris, so a destination belongs to it only inside its polygon. **New York State** is added for the USA
   (`north-america/us/new-york`, 475 MB, a `.poly` linked on its page, read 2026-11-17); Geofabrik has no
   extract for New York City alone. Each region now has a **continent** (the Regions screen groups
   by it) and a **scope**: `country` (a whole country, the only region that claims its code) or
   `part` (a city or state that claims its country's code but is matched by its polygon, so several
   may share a code; a test enforces this). Great
   Britain (2.1 GB download) is deliberately not offered yet: it is far larger than a city and its
   share of the free database is unknown. The download is filtered on the GitHub runner, so its size
   is not the size the region takes in the database.
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
   After an import a region's row shows about how much database space it takes (its share of the
   place tables by rows; an estimate), and while importing a yellow badge. Before an import it says
   only "Not imported".
   Settings now shows the full installation id, which the owner pastes into
   `DETOUR_OWNER_INSTALLATION_IDS`.
7. The workflow still runs by hand from the Actions tab (its inputs are now a text field and an
   optional `job_id`). An unknown region fails at the first import command.

8. **The workflow tests the network and tries again (2026-11-19).** GitHub's machines sometimes
   cannot reach Geofabrik (`[Errno 101] Network is unreachable` for five minutes on two Paris runs,
   on machines whose package downloads were slow too). The workflow installs the importer first,
   then checks `download.geofabrik.de` for about a minute **before** the slow package install; the
   download itself retries five times (5, 10, 20, 40 s) and, when all fail, the importer exits with
   code 75. On either failure a `retry` job starts the workflow again on another machine with the
   same inputs and `attempt` + 1 (a run cannot be re-run while it is running, so it is a new
   `workflow_dispatch`, which the workflow's own token may start with `actions: write`), at most
   three attempts. While a retry is pending the job stays `running` with the message "GitHub
   couldn't reach Geofabrik. Trying again on another machine (attempt 2 of 3)."; after the third
   it is `failed` with "GitHub couldn't reach Geofabrik, try again." Other failures are not
   repeated. If the retry cannot be started, the job is shown as stalled after 45 minutes. Not
   yet run on GitHub.

Not built: offering "Import sights for London" on the new-trip screen when a destination has no
sight data; a removal's photo files; importing a region larger than the free database allows
(the import's own size gate decides, and the screen shows the usage).

## Alternatives

- Delete everything of the region, trips included: breaks photos and names on trips that exist.
- Copy a stop's category, default length and photo into the item first: more migration and a
  second source of truth; keeping the rows is cheaper and reuses an existing rule.
- Open to any installation: anyone with the APK could empty the shared data.

## Consequences

- Removing a region frees most of its space but not all: places and cities that trips use stay, and
  so do photo files. Cities of a country another region still covers stay too, so removing Paris
  frees no French cities while another French region holds data. A region used by many trips frees less.
- An upcoming trip to a removed region keeps its stops but cannot get suggestions, and its stops
  are no longer found as sights (they remain as stops). A past trip is read-only anyway.
