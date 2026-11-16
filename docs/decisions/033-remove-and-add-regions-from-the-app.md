# ADR 033 — Remove and add regions from the app

- **Status:** **Proposed** (owner request of 2026-11-17: "delete a region but keep past trips
  intact, and add a region through the app"). **Step 2 (removal) is built**, awaiting acceptance;
  checked by tests only, not tried on a device, not run against production. Step 3 (adding a region
  from the app) is **not built**.
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

## Not decided yet (step 3: add a region from the app)

The import needs a download of hundreds of MB to GB and `osm2pgsql`; it cannot run on Render's free
service. The proposal is that the backend dispatches the existing "Import region" workflow through
GitHub's API with a fine-grained token kept as a Render secret (a new provider call: this ADR will
cite GitHub's terms and the date they were read), a catalog of importable regions including smaller
extracts (Greater London rather than all of Great Britain), progress written to a `geo.import_job`
table, and the same owner gate. It will be written and built as step 3.

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
