# Data model

Status: **implemented in Phase 2** (Alembic migrations `0002_geo_schema` and `0003_app_schema`);
`geo.travel_time` was rebuilt in Phase 3 (`0005_travel_time_cache`, ADR 013). Phase 4 (ADR 014)
fills the engine columns of `app.itinerary` and `app.transfer` without a schema change. Migration
`0006_meals_areas_no_budgets` (2026-11-13) adds the meal type `snack` and each day's base city
name and inter-city leg (ADR 016), and removes the trip's currency, meal budget and price bands,
`app.price_record` and `geo.fx_rate` (ADR 017). Migration `0007_change_sets_and_versions`
(Phase 7, ADR 018) adds `app.change_set` and `app.itinerary_version` (section 3.7).
Where the built schema differs from the earlier proposal, the difference is listed in section 9
and decided in [ADR 012](decisions/012-phase-2-data-and-search-choices.md). Photos (section 8) are
still reserved, not built.

## 1. Overview

Two PostgreSQL schemas with different owners and different licence positions:

| Schema | Contents | Origin | Rebuildable |
|---|---|---|---|
| `geo` | Regions, import runs, places and their sources, gazetteer, countries, currencies, travel times, licences | Imported open data | Yes, from sources |
| `app` | Installations, trips, itineraries, items, user places, past-trip archive, provider cache | Created by users, the planning engine and the backend | No |

`app` rows refer to `geo` rows by identifier and never copy their attributes, with the two
snapshots the design asks for: an itinerary item keeps a display name and point (so a re-import
cannot break an accepted plan), and an archived visit keeps a name and point (ADR 006).

**There are no foreign keys between the schemas** (section 6). Inside each schema they are real.

```
geo.region ──< geo.import_run          geo.licence ──< geo.place_source, geo.city, ...
geo.region ──< geo.place ──< geo.place_source
geo.place ──1 geo.restaurant_profile   geo.place ──1 geo.place_signal
geo.region ──< geo.admin_area          geo.country ──< geo.city      geo.country >── geo.currency
geo.travel_time (end points, mode)     geo.admin_code

app.installation ──< app.trip ──< app.itinerary ──< app.itinerary_day ──< app.itinerary_item
app.installation ──< app.user_place              app.itinerary_item ──< app.transfer (to the next item)
app.trip ──< app.trip_visit (past trips)
app.itinerary ──< app.change_set, app.itinerary_version (Phase 7)
app.provider_cache, app.provider_usage (external provider answers and daily call counters)
app.photo >── trip, day, city, item        (future phase)
```

Conventions: enumerations are `text` columns with CHECK constraints; unknown values are `NULL`
(never an empty string, a zero or a guess); every geometry column is SRID 4326 and has a GiST
index; text that is searched has a `*_norm` companion (section 2.9).

## 2. `geo` schema: imported reference data

### 2.1 `geo.licence`
Every data set in `geo` points to its licence. Seeded by the migration.

| Code | Name | Credit | Share-alike |
|---|---|---|---|
| `ODbL-1.0` | Open Database License 1.0 | © OpenStreetMap contributors | yes |
| `CC-BY-4.0` | Creative Commons Attribution 4.0 | GeoNames (https://www.geonames.org) | no |
| `CC0-1.0` | Creative Commons Zero 1.0 | Wikidata | no |

### 2.2 `geo.region` and `geo.import_run`
A region is a unit of import (one Geofabrik extract).

| `geo.region` | Type | Notes |
|---|---|---|
| `id` | text pk | Slug, for example `austria` or `czech-republic` (the Geofabrik name) |
| `name`, `country_codes` | text, text[] | Countries (ISO 3166-1 alpha-2) the region covers |
| `geom` | multipolygon, nullable | Coverage polygon from Geofabrik's `.poly` file; null if it could not be loaded |
| `status` | text | `available` (passed every ADR 009 gate), `importing`, `disabled` (the default) |
| `current_import_run_id` | fk | The data version in use |

| `geo.import_run` | Type | Notes |
|---|---|---|
| `id` | uuid pk | Itineraries record the run they were built on |
| `region_id` | fk | |
| `status` | text | `running`, `succeeded`, `failed` (with `error`) |
| `importer_version`, `rules_version` | text | `rules_version` is the selection rule version (ADR 011) |
| `source_url`, `source_sha256`, `source_bytes` | text, text, bigint | The extract that was read; the URL is null for a local file |
| `osm_snapshot_date` | date, nullable | Replication timestamp of the extract; null if the file has none |
| `geonames_date`, `wikidata_date` | date, nullable | Not filled in Phase 2: the GeoNames file date is on `geo.city.geonames_date`, and Wikidata is not fetched |
| `counts` | jsonb | Places by kind, total, excluded total, admin areas, deactivated places |
| `report` | jsonb | The full data quality report and the gates (section 7) |
| `started_at`, `finished_at` | timestamptz | |

### 2.3 `geo.country`, `geo.currency`, `geo.admin_code`
From the GeoNames `countryInfo.txt` and the admin code files (all countries and currencies are
loaded; codes only for the imported countries). The currency rows and
`country.default_currency_code` are GeoNames reference data that nothing uses since ADR 017.

| Table | Fields |
|---|---|
| `country` | `iso2` pk, `iso3`, `name`, `default_currency_code` (null if none), `geom` (unused), `licence_code` |
| `currency` | `code` pk (ISO 4217), `name`, `symbol` and `minor_units` (**null: not in the source**), `licence_code` |
| `admin_code` | `code` pk (`AT.01` or `AT.01.101`), `level` 1 or 2, `country_iso2`, `name`, `ascii_name`, `geoname_id`. Joined to a city by `country_iso2 || '.' || admin1_code` |

### 2.4 `geo.city`: the destination gazetteer (GeoNames, `cities1000`)

| Field | Notes |
|---|---|
| `id` | bigint, the GeoNames identifier |
| `name`, `ascii_name` | |
| `name_norm` | Lower case, accents removed from Latin letters, punctuation as spaces: what search matches |
| `alt_names`, `alt_names_norm` | Alternate names: distinct by normalised form, shortest first, **at most 40**. `alt_names_norm` joins the normalised names with `|` |
| `country_iso2`, `admin1_code`, `admin2_code` | |
| `population` | **Null when unknown** (GeoNames writes 0) |
| `timezone`, `feature_code` | IANA name; used for local meal times and day boundaries |
| `geom` | point |
| `licence_code`, `geonames_date` | `CC-BY-4.0`; the `Last-Modified` date of the downloaded file |

Indexes: GiST on `geom`; trigram on `name_norm`, `ascii_name`, `alt_names_norm`.

### 2.5 `geo.admin_area`: destination areas (OSM boundaries)
Administrative boundaries of OSM `admin_level` 4 and 6 from the extract, with a name. What the
levels mean differs by country; the level is stored as mapped. Geometry is simplified (tolerance
about 100 m): areas scope a destination, they are not for drawing borders.

`id` (deterministic uuid), `region_id`, `name`, `name_norm`, `level`, `country_iso2` (from the
`ISO3166-2` tag, or the region's only country; null if neither), `geom` (multipolygon), `source`
(`osm`), `source_ref` (`relation/123`), `licence_code` (`ODbL-1.0`), `is_active`,
`last_changed_import_run_id`.

### 2.6 `geo.place`: one real-world place that can appear in an itinerary

| Field | Notes |
|---|---|
| `id` | uuid, derived from the region and the OSM reference: **stable across imports** |
| `region_id`, `kind` | `attraction` or `restaurant` today (restaurants and cafes only near attractions or towns, ADR 011); `transport_hub` and `other` are reserved |
| `category` | Normalised: the `tourism` value, an allow-listed `historic` value (`historic_building` and the other generic classes carry the `historic_` prefix; `historic=yes` is `historic`), or `restaurant`/`cafe` |
| `name`, `name_norm` | Null when the source has no name; both null or both set. Attractions without a name are not imported (ADR 011), so a null name occurs only for restaurants and cafes |
| `names_i18n` | jsonb, language to name (`name:*` tags and `int_name` as `int`); null if none |
| `geom` | Representative point; areas are reduced to a point on their surface |
| `address` | jsonb from `addr:*` (street, housenumber, postcode, city, country); null if none |
| `city_id` | The nearest gazetteer city of the region's countries (planar distance picks five candidates, great-circle distance and then id decide); null until the gazetteer is loaded |
| `default_visit_minutes` | **Always null.** Visit durations come from the planner's category rule table (`planner/durations.py`, ADR 014), which is configuration, so changing it needs no re-import. A non-null value here would take precedence for hand-added items |
| `is_active` | False only for a place that is gone from the latest extract **but still named by an itinerary item** in `app`; any other missing place is deleted (section 5) |
| `first_import_run_id`, `last_changed_import_run_id` | The run that created the row; the run that last wrote it (rows that did not change are not rewritten, so this is not "last seen") |

Opening hours are not imported, parsed or stored (ADR 003): there is no hours column or table.

### 2.7 `geo.place_source`: provenance
One row per source record that contributed to a place; the primary key is
`(place_id, source, source_ref)`.

| Field | Notes |
|---|---|
| `source` | `osm` today (`wikidata`, `overture`, `fsq_os` are reserved) |
| `source_ref` | `node/123`, `way/9`, `relation/7` |
| `licence_code` | `ODbL-1.0` for OSM |
| `tags` | jsonb: the tags the importer reads, unmodified. Not `name:*` and `addr:*` (own columns) and never `opening_hours` |
| `import_run_id` | |

### 2.8 `geo.restaurant_profile` and `geo.place_signal`

| `restaurant_profile` | Notes |
|---|---|
| `place_id` | pk, fk |
| `cuisines` | text[] from the `cuisine` tag: split on `;`, lower case, spaces as `_`, sorted, distinct. **Null = no cuisine tag** |
| `venue_type` | `restaurant` or `cafe` today (`fast_food`, `bar`, `pub`, `food_court`, `other` reserved) |
| `meal_types` | Derived from the venue type by a fixed rule: restaurant → lunch, dinner; cafe → breakfast, snack |
| `diet_flags` | From `diet:*`: `yes` → `vegan`, `only` → `vegan_only`. **Null = no `diet:*` tag**; a `no` is not stored |
| `provider_price_level`, `provider_price_source` | **Always null**: no licensed source, and the app has no prices (ADR 017) |

| `place_signal` | Notes |
|---|---|
| `place_id` | pk, fk |
| `wikidata_id` | The OSM `wikidata` tag if it is a single `Q` number; else null |
| `sitelink_count` | **Null: Wikidata is not fetched in Phase 2** |
| `osm_signals` | jsonb flags: `has_wikidata`, `has_wikipedia`, `has_heritage`, `tourism_attraction`, `has_name`, `has_website`, and `heritage` (the value) |
| `score` | Additive count of those signals (weights in `importer/derive.py`); orders places only, tuned in Phase 4 |

### 2.9 Search columns and indexes

- Normalisation (`detour_api/textnorm.py`) is applied to the stored `name_norm` columns and to the
  query, so both sides agree. Accents are removed only from Latin letters; Japanese is untouched.
- GiST on every geometry column; trigram (GIN) on `geo.city.name_norm`, `ascii_name`,
  `alt_names_norm`, `geo.place.name_norm`, `geo.admin_area.name_norm`.
- `geo.place`: partial index `(region_id, kind) WHERE is_active`; `city_id`.

### 2.10 `geo.travel_time`

The Phase 3 cache (migration `0005`, ADR 013). (`geo.fx_rate` was dropped by migration `0006`,
ADR 017.)

| `travel_time` | Notes |
|---|---|
| `from_lat`, `from_lon`, `to_lat`, `to_lon` | The cell's end points as integers of 1e-5 degree (about 1.1 m); not place ids, so a moved place cannot keep a stale time |
| `mode` | `walk` or `drive` |
| `request_shape` | `matrix-v1` or `route-v1`: part of the key, so a change of shape never mixes with old rows |
| `provider`, `response_date` | `fossgis-valhalla`; the server's `Date` header, else our clock |
| `confidence` | `routed` (has `seconds` and `meters`) or `estimated` (a cell the provider had **no route** for: no numbers, `retry_after` set; the estimate is recomputed on read). A CHECK enforces both |
| `algorithm` | The matrix algorithm the response named; null for route requests and unknown |
| `retry_after` | Estimated rows only: the provider is asked again after this time |

Key `(from_lat, from_lon, to_lat, to_lon, mode, request_shape)`. Capped at 100,000 rows (oldest
`response_date` first), measured at 20.7 MB; it counts toward ADR 009 gate 6 because that gate sums
the whole `geo` schema. Estimates made because the provider was unavailable are not stored. It is
not rebuilt by an import.


## 3. `app` schema: user data

### 3.1 `app.installation`
Anonymous identity (D5). The bearer token is an HMAC-signed string carrying the installation id
(ADR 010); the row is created lazily, on the first authenticated call that touches the database,
and `last_seen_at` is refreshed at most hourly. No token or hash is stored.

`id`, `is_seed` (true only for the seed installation), `created_at`,
`last_seen_at`.

### 3.2 `app.trip`

| Field | Notes |
|---|---|
| `id`, `installation_id` | fk, `ON DELETE CASCADE` |
| `title` | 1 to 120 characters |
| `destination_kind`, `destination_ref` | `city` (a `geo.city.id`) or `area` (a `geo.admin_area.id`); existence and region availability are checked by the API |
| `destination_name`, `destination_point` | Snapshot taken at creation |
| `duration_days` | 1 to 30; cannot change once the trip has itineraries |
| `start_date` | Optional; when set or changed, itinerary day dates follow |
| `selected_itinerary_id` | fk, `ON DELETE SET NULL` |
| `status`, `archived_at` | `active`, `past`; a past trip has `archived_at` (check constraint) |
| `is_seed`, `created_at`, `updated_at` | |

### 3.3 `app.itinerary`, `app.itinerary_day`, `app.itinerary_item`, `app.transfer`
A proposed or selected plan. Variants of one generation share a `generation_id`.

| `itinerary` | Notes |
|---|---|
| `profile` | `essentials`, `wider`, or `manual` (an empty plan filled by hand; the only kind before Phase 4) |
| `status` | `proposed`, `selected`, `superseded`; at most one `selected` per trip (kept by the API when the selection changes) |
| `version` | Starts at 1; incremented by every accepted item edit and every applied change set. The version it replaces is kept in `app.itinerary_version` (section 3.7) |
| `engine_version`, `config_version` | `manual` for manual itineraries; for engine itineraries for example `planner-1.0.0` and `2026-11-12.2+durations-2026-11-12.1`; after a recalculation (ADR 018) `planner-2.0.0+recalc-1.0.0` and `<config>+recalc-2026-11-13.1` |
| `import_run_id` | The data version used; null for manual itineraries; not a foreign key |
| `seed`, `diversity_score`, `summary` | Engine itineraries (Phase 4, ADR 014): `seed` 0 (no randomness is used); `diversity_score` the Jaccard similarity of the generation's two variants (null with one); `summary` holds `stats` (visits, minutes, transfers by label, day utilisation and travel share in permille), `notes` (codes with parameters, rendered by fixed templates when read), `sequencer`, `estimate_version`, `jaccard_permille`; since ADR 016 the stats also hold `meals`, `meal_minutes` and `intercity_legs` (itineraries written before have a `currency_code` key, unused). `{}` for manual itineraries |

`itinerary_day`: `day_index` (1-based, unique per itinerary), `date` (null without a start date),
`base_city_id` (a `geo.city.id`, null), `base_city_name` (a snapshot of its name, null for manual
itineraries), and the inter-city leg that starts the first day at a new base city of an area
(ADR 016): `arrival_mode`, `arrival_seconds`, `arrival_meters`, `arrival_confidence`, all null or all
set (a CHECK enforces it). The leg always comes from the previous day's base city.

| `itinerary_item` | Notes |
|---|---|
| `position` | Dense and 1-based within a day; unique per day (deferrable, so reorders are atomic) |
| `type`, `meal_type` | `visit`, `meal`, `free_time`; `meal_type` (`breakfast`, `lunch`, `snack`, `dinner`) iff `type = meal`. Engine meals (ADR 016) take the length of the meal-length table with `duration_source = 'category_default'`; the read endpoints add the place's venue type and cuisines from `geo.restaurant_profile` (or the user place) by identifier, never copied |
| `place_id`, `user_place_id` | Exactly one for a visit or meal, neither for free time. A meal needs a restaurant; a visit must not be one. `user_place_id` is `ON DELETE RESTRICT` |
| `display_name`, `display_point` | Snapshot at creation (name or, for an unnamed place, its category); user-place renames are propagated |
| `start_time`, `end_time` | Local time at the destination; both null or both set, `end > start`, same day. Unscheduled is allowed. Timed items of a day may touch but not overlap |
| `duration_minutes`, `duration_source` | 1 to 1440; `user` or `category_default`. Engine items and imported attractions added without a duration take the category default (ADR 014); a meal or a user place needs a duration |
| `origin`, `locked`, `reasons` | `engine` or `user`; a locked item keeps its day, start and end in every recalculation and is never removed by one; an item with origin `user` (added by hand or through a change set) is mandatory: never left out (ADR 018); reason codes from the fixed template table (`planner/reasons.py`; `SEED_DATA` on seed items) |

`transfer`: `from_item_id` (unique: one outgoing transfer per item), `to_item_id`, `mode`,
`seconds`, `meters`, `confidence` (`routed`, `estimated`), `geometry`. Written by the planner for
every pair of consecutive visits (Phase 4), with the values and label the travel-time service
returned; `geometry` stays null (route lines are fetched for the selected itinerary only, ADR 013).
A hand edit deletes the transfers that no longer join an item to the next one; they are not
recomputed. A recalculation (ADR 018) writes the transfers of the days it changes.

### 3.4 `app.user_place`
A place the user added that is not in `geo.place`: `kind` (`city`, `location`, `restaurant`),
`name`, `geom`, `cuisines` and `meal_types` (restaurants only; meal types may include `snack`),
`source` (`manual_pin`, `search_result`), and `search_provider` (`photon`, or `geonames` for a
town from destination search saved to add it to a plan, ADR 018) with `search_ref` (for example
`N123`, an OSM node, or a GeoNames id) **iff** the source is a search result. At most 500 per
installation.

### 3.5 `app.trip_visit`: the past-trip archive (ADR 006)
One row per city or attraction of the selected itinerary of a past trip: `kind`, `name` and
`point` (snapshots), `geo_place_ref` (a `geo.place` id for imported places, null for user places
and cities; may no longer exist), `day_number`, `confirmed` (default true; the user can clear it).
Restaurants and meals are not archived.

### 3.6 `app.provider_cache` and `app.provider_usage`
Answers from the one external provider (Photon) and its daily call counter (architecture, section
6). They live in `app` because an import does not rebuild them. `provider_cache` holds
`cache_key` (a hash of the normalised question), the provider's `response`, and `expires_at`; it
never holds an installation identifier. `provider_usage` is `(provider, usage_date, calls)`.

### 3.7 `app.change_set` and `app.itinerary_version` (Phase 7, ADR 018)

| `change_set` | Notes |
|---|---|
| `itinerary_id` | fk, `ON DELETE CASCADE` |
| `base_version` | The itinerary version the preview was made from; apply refuses if it changed |
| `action` | `add_place` (with `place_id` **or** `user_place_id`, and `duration_minutes` if given) or `remove_place` (with `item_id`) |
| `target_name` | Snapshot of the place's name |
| `status` | `pending` (previewed), `applied`, `discarded`, `expired` (the itinerary changed, or a newer preview replaced it); `decided_at` iff not pending; `result_version` iff applied |
| `restores_version` | Set when applying restores that stored version exactly (removing the place the latest change added) |
| `proposal` | The plan rows to write (same shape as a version's `state`); **cleared once decided** |
| `diff`, `notes` | What the preview showed, kept after the decision |

| `itinerary_version` | Notes |
|---|---|
| `(itinerary_id, version)` | pk; the itinerary fk cascades |
| `state` | The version's days, items and transfers as rows, with its summary and engine, configuration and data versions. Items keep only their own name and point snapshots; venue types and cuisines stay in `geo` |
| `replaced_at`, `change_set_id` | When it was replaced, and by which change set (null: a hand edit) |

Every replaced version is kept, up to 30 per itinerary (the oldest are removed first).

## 4. Restaurant prices

**Removed** (ADR 017, owner decision of 2026-11-13). `app.price_record`, the trip's currency, meal
budget and price-band thresholds, and `geo.fx_rate` were dropped by migration `0006`. Places to eat
carry venue type, cuisines and meal types only. Bringing prices back needs a new ADR.

## 5. Lifecycle and deletion rules

| Event | What happens |
|---|---|
| **Import of a region** | Upsert by deterministic id inside one transaction; **a row that did not change is not written** (a rewrite leaves a dead copy and would double the database on every re-import). Places missing from the new extract are **deleted with their source, signal and profile rows**, unless an itinerary item in `app` still names them: those stay with `is_active = false` and are cleared by a later import once nothing names them. Administrative areas missing from the extract are deleted (a trip keeps its own destination snapshot). After the commit the tables are vacuumed; after a clean-up of 1,000 rows or more they are rewritten (`VACUUM FULL`) so the file shrinks. A failed import changes no data and leaves a `failed` import run |
| **Gazetteer import** | Upserts countries, currencies, codes and cities; cities of the imported countries that are gone from the file are deleted (`place.city_id` becomes null); places get their nearest city |
| **Region status** | Set by each import from the six gates: `available` or `disabled`. There is no manual override |
| **First API call of an installation** | Creates its `app.installation` row |
| **Delete a trip** | Cascades to its itineraries, days, items, transfers and archive rows. User places stay |
| **Delete an itinerary** | Cascades to days, items and transfers; clears the trip's selection if it was selected |
| **Delete an item** | Later items of the day move up; the itinerary version increases (the replaced version is kept) |
| **Preview a change** (ADR 018) | Stores a `pending` change set; expires the itinerary's other pending one; the itinerary is not touched |
| **Apply a change** | Keeps the current version in `itinerary_version`, writes the proposal, increments the version, clears the proposal |
| **Discard a change** | The change set becomes `discarded` and loses its proposal |
| **Delete a user place** | Refused (409) while an item uses it |
| **Archive a trip** (`POST /v1/trips/{id}/archive`, ADR 006) | One `trip_visit` per city and visit item of the *selected* itinerary (or the destination city if there is none); then **every** itinerary of the trip is deleted (transfers, route geometry, versions, seeds go with them); the trip becomes `past`. One-way. A past trip is read-only except deletion and clearing visits |
| **Delete an installation** (no endpoint; operator action) | Cascades to everything it owns. Tokens are stateless, so the app would register a new installation |
| **Limits** | 100 trips per installation, 5 itineraries per trip, 40 items per day, 500 user places, 30 kept versions per itinerary, one pending change set per itinerary |

Not built: archiving a trip automatically after its last day (ADR 006 allows it; it needs a
scheduled job), and a backup of `app` (ADR 005: Supabase Free has none).

## 6. Provider-data ownership and licence handling

- **`geo` holds data derived from OpenStreetMap under ODbL, and GeoNames data under CC BY 4.0.**
  Each set carries its licence: `geo.place_source.licence_code` for every place, and
  `licence_code` on cities, countries, currencies and admin areas. `GET /v1/attributions` lists
  the credits the app must show.
- **OSM data is stored as ODbL source records.** A place is the real-world entity; its OSM object
  is one `geo.place_source` row (source `osm`, the reference, the licence, the tags). A different
  source (Overture, Foursquare OS Places, Wikidata) would be another row for the same place with
  its own licence, never merged into the OSM row (CLAUDE.md, architecture rules).
- **Derived values** (`category`, `cuisines`, `meal_types`, `score`) are computed from source
  tags by versioned rules (`rules_version` on the import run); they are part of the adapted OSM
  database.
- **If an adapted OSM database is used publicly, it must be offered under ODbL on request.**
  `geo` is that database. Its content is reproducible with the import workflow.
- **`app` is independent data** (trips, itineraries, user places). It links to `geo` by
  identifier only and copies only the name and point snapshots. Under OSMF's guidance this is a
  Collective Database, so share-alike does not extend to it. This reading must be confirmed by
  legal review before any public commercial release.
- **No foreign keys cross the schemas.** This keeps the licence boundary in the database as well:
  `geo` can be dropped and rebuilt, or handed over under ODbL, without touching `app`. A test
  fails if a constraint ever crosses.
- **Photon results** (ODbL OSM data) are not stored in `geo`. They are cached for a week in
  `app.provider_cache` and reach `geo`-independent storage only when the user saves one as a user
  place (`search_provider`, `search_ref`).
- **Opening hours and prices from providers are not stored** (ADR 003; ADR 002 rejects the
  providers that have them).

## 7. The import report and the gates

Every import stores a report in `geo.import_run.report` (and writes `report.json`, `report.md`
and `review-sample.json` as workflow artifacts): source file and hash, places by kind with the
share named, with a cuisine, with Wikidata and with Latin letters in the name, administrative
areas, **excluded objects per class and reason**, the largest categories, the size of the `geo`
schema (measured after the vacuum that follows the commit, which is the size gate 6 uses), and
the six gates of [ADR 009](decisions/009-region-readiness-thresholds.md) with their values. A region is `available` only if every gate passes; an unknown value never passes.

## 8. Future: photos

Reserved so later work needs no restructuring. Not built.

`app.photo`: `id`, `installation_id`, `trip_id` (always), `day_id`, `city_id`, `itinerary_item_id`
(the most specific association, nullable), `local_uri`, `storage_key` (nullable), `taken_at`,
`geom` (only with the user's consent to keep location), `checksum`, `width`, `height`, `bytes`.
In the first photo phase the files and this table live on the device only (D9).

## 9. Differences from the earlier proposal

| Earlier proposal | Built | Why |
|---|---|---|
| Foreign keys from `app` to `geo` | Identifiers checked by the API, snapshots on items | ADR 012, decision 2 |
| Native enum types | `text` with CHECK | ADR 012, decision 1 |
| `app.installation.token_hash` | No token column | ADR 010 |
| `geo.region.status` set by the operator | Set by the gates | ADR 009 |
| `default_visit_minutes` from a category rule table | Always null; the table is planner configuration | ADR 014: changing a duration needs no re-import |
| `geo.place_signal.sitelink_count` from Wikidata | Always null | Wikidata not fetched |
| Region `geom` from the extract | From Geofabrik's `.poly` file, nullable | |
| (new) `geo.licence`, `geo.admin_code`, `geo.import_run.report`, place `*_norm` columns, `first/last_changed_import_run_id` | | Licence handling, names for codes, report, search, deactivation |
| `geo.travel_time` keyed by two text references, `engine_version`, `import_run_id` | Keyed by end-point coordinates, `request_shape`, `provider`, `response_date`; no `import_run_id` | ADR 013: a provider's answer does not belong to our import; compact; shape and provider recorded |
| (new) `app.trip.destination_name/point`, `app.installation.is_seed`, `app.trip.is_seed`, `profile = manual`, `app.provider_*` | | ADR 006 snapshot, seed data, manual itineraries, provider rules |
