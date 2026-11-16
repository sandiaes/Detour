# Data model

Status: **implemented in Phase 2** (Alembic migrations `0002_geo_schema` and `0003_app_schema`);
`geo.travel_time` was rebuilt in Phase 3 (`0005_travel_time_cache`, ADR 013). Phase 4 (ADR 014)
fills the engine columns of `app.itinerary` and `app.transfer` without a schema change. Migration
`0006_meals_areas_no_budgets` (2026-11-13) adds the meal type `snack` and each day's base city
name and inter-city leg (ADR 016), and removes the trip's currency, meal budget and price bands,
`app.price_record` and `geo.fx_rate` (ADR 017). Migration `0007_change_sets_and_versions`
(Phase 7, ADR 018) adds `app.change_set` and `app.itinerary_version` (section 3.7);
`0008_add_restaurant_change_sets` (Phase 8, ADR 019) lets a change set add a restaurant to a meal
slot. The past-trips archive (section 3.5, ADR 006) needs no migration since `0003`; its automatic
rule and size report are described in section 5. Migration `0013_multilingual_place_names`
(ADR 025) adds `geo.place.alias_norm`, `geo.place_name`, `geo.place_name_lookup` and
`app.place_name_override` (sections 2.6, 2.11 and 3.8). Migration `0014_no_imported_restaurants`
(ADR 026, data step) deletes the imported restaurants and cafes, drops `geo.restaurant_profile`, the
cuisine and meal-type columns and `app.itinerary_item.meal_type`, adds the user-place kind `cafe` and
retires the `add_restaurant` change-set action with its slot columns. Later migrations: `0015` (the
past trip's day record), `0016` (place destinations, ADR 027), `0017` (Optimize change sets, ADR 029),
`0018` (`app.trip.uses_car`), `0019` (`app.trip_stay`, ADR 030) and `0020` (Phase 9: row level
security on `public.alembic_version`, so Supabase's Data API roles cannot read or change it). The
production database was at `0019` on 2026-11-15.
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
geo.place ──1 geo.place_signal
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
`last_changed_import_run_id`, `wikidata_id` (the `wikidata` tag, for the area's photo; migration
`0011`).

### 2.6 `geo.place`: one real-world place that can appear in an itinerary

| Field | Notes |
|---|---|
| `id` | uuid, derived from the region and the OSM reference: **stable across imports** |
| `region_id`, `kind` | `attraction` only (restaurants and cafes are no longer imported, ADR 026); `transport_hub` and `other` are reserved |
| `category` | Normalised: the `tourism` value, an allow-listed `historic` value (`historic_building` and the other generic classes carry the `historic_` prefix; `historic=yes` is `historic`), |
| `name`, `name_norm` | Null when the source has no name; both null or both set. Attractions without a name are not imported (ADR 011), so a null name does not occur in current imports |
| `names_i18n` | jsonb, language to name (`name:*` tags and `int_name` as `int`); null if none |
| `name_en_norm` | The normalised English name (`names_i18n.en`), set only when it differs from `name_norm`; search matches it as well (migration `0010`, ADR 021 decision 40) |
| `alias_norm` | The normalised search aliases the source gives, `\|`-joined: every other `name:*`, `int_name`, romanizations, `official_name`, `short_name`, `alt_name`, `old_name`, `brand` (and their `:en` forms), Detour's transliteration of the name, and German/Scandinavian ASCII spellings (`moenchsberg`); at most 60 forms or 4,000 characters; null if none. Search only, never shown (migration `0013`, ADR 025). Which name is **shown** is decided by the name resolver (section 2.11) |
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
| `tags` | jsonb: the tags the importer reads, unmodified. Not `name:*` and `addr:*` (own columns) and never `opening_hours`. Since ADR 025 the import also keeps `official_name`, `short_name`, `alt_name`, `old_name`, `brand`, `brand:wikidata` and the `official_name:*`, `short_name:*` and `brand:*` tags (places imported earlier have them after a re-import) |
| `import_run_id` | |

### 2.8 `geo.place_signal`

`geo.restaurant_profile` (cuisines, venue type, meal types, diet flags) **was dropped by migration `0014`**
(ADR 026, 2026-11-14): restaurants and cafes are not imported and nothing in `geo` describes a place to
eat.

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
  `alt_names_norm`, `geo.place.name_norm`, `geo.place.name_en_norm` (where set), `geo.admin_area.name_norm`.
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


### 2.11 `geo.place_name` and `geo.place_name_lookup`: names from Wikidata (ADR 025)

The names Wikidata gives for a place, a city or an area, fetched lazily (in the background after a
trip is created, generated or read, and by `python -m detour_api.importer names`). Names from
OpenStreetMap and GeoNames are **not** copied here: the resolver reads them from `geo.place` and
`geo.city`. Full description: [`multilingual-place-names.md`](multilingual-place-names.md).

| `place_name` | Notes |
|---|---|
| `entity_kind`, `entity_ref` | `place` (a `geo.place.id`), `city` (a GeoNames id) or `area`, as text; no foreign key (rows of a gone entity are pruned) |
| `lang`, `script` | BCP 47 tag (`en`, `ja`, `mul`); ISO 15924 script code, null if no letters |
| `name`, `name_norm` | The name as given; its normalised search form |
| `name_type` | `original` (a city's native label), `established_english`, `search_alias`, and the other types of section 1 of the names document (`user_override` lives in `app`) |
| `source`, `source_ref` | `wikidata` (QID) or `enwiki` (the sitelink title, read from Wikidata) |
| `step`, `confidence`, `official`, `is_preferred` | The hierarchy step it can fill (null for an alias), its configured confidence, whether the source marks it official, and whether it is the best stored display candidate |
| `licence_code` | `CC0-1.0` |
| `retrieved_at`, `expires_at` | Expires 90 days after retrieval unless the app still names the entity (section 5) |

Primary key `(entity_kind, entity_ref, lang, source, name_norm)`: the deduplication rule. Trigram
index on `name_norm` (search). Per entity: the English label, the English Wikipedia title (without a
trailing qualifier, the full title as an alias), the labels in `mul` and the local language, up to 5
aliases per language.

| `place_name_lookup` | Notes |
|---|---|
| `(entity_kind, entity_ref, source)` | pk; `source` is `wikidata` |
| `qid` | The item found (by QID, Wikipedia sitelink, GeoNames id or the coordinate fallback); null if none |
| `status`, `reason` | `found`, `no_english` (the negative cache: an item without an English label or article) or `no_item`, with a reason (`geonames_id`, `wikipedia_sitelink`, `coordinate_match`, `no_item_for_geonames_id`, `ambiguous_coordinate_match` …) |
| `checked_at`, `retry_after` | Asked again after `retry_after` (90 days). Network failures record nothing |

## 3. `app` schema: user data

### 3.1 `app.installation`
Anonymous identity (D5). The bearer token is an HMAC-signed string carrying the installation id
(ADR 010); the row is created lazily, on the first authenticated call that touches the database,
and `last_seen_at` is refreshed at most hourly. No token or hash is stored.

`id`, `is_seed` (true only for the seed installation), `created_at`,
`last_seen_at`; since ADR 034 (migration `0024`) also `person_id` (fk to `app.person`, `ON DELETE
CASCADE`, not null; a trigger fills it with a new person of the same id when an insert leaves it
out), `joined_at` (when the phone joined its person with a code; null for the phone that started
it) and `revoked_at` (removed under Your phones, or signed out by the recovery code: its token is
refused with 401 `device_removed`).

### 3.1a `app.person` and `app.link_code` (ADR 034, step 1, migration `0024`)

`app.person`: `id`, `recovery_hash` (unique, a keyed hash of the recovery code; null when there is
none), `recovery_created_at` (set exactly when the hash is), `created_at`. **A person's id is the id
of its first installation**, and every row that names an installation (`trip`, `user_place`,
`place_name_override`) names the person's id: the API reads and writes them under the caller's
person, so all of a person's phones see the same trips. A phone that joins a person brings its own
trips, places and overrides along (moved to the person's id; an override the person already has for
the same place wins), and its former person is deleted. Every installation that existed before
`0024` became a person of its own with the same id. Migration `0025` (step 2) renamed the columns:
`app.trip.owner_person_id`, `app.user_place.person_id`, `app.place_name_override.person_id`, each a
fk to `app.person` (`ON DELETE CASCADE`).

### 3.1b `app.trip_member` (ADR 034, step 2, migration `0025`)

Who may see and change a trip: `trip_id` (fk, cascade), `person_id` (fk to `app.person`, cascade),
`role` (`owner` or `editor`), `added_at`, `added_by` (fk to `app.person`, `ON DELETE SET NULL`);
primary key `(trip_id, person_id)`; exactly one `owner` per trip (a partial unique index), the same
person as `app.trip.owner_person_id`. A trigger adds the owner's row when a trip is inserted. **Every
trip read and change is authorised by membership** (the API joins `app.trip_member` on the caller's
person); only the owner may delete the trip (403 `not_trip_owner`). The 100-trip limit counts the
trips a person owns. An editor row is written by sharing (step 3): "Who's going" when the trip is
created, or Share in its settings, only with a linked person; it is removed when the member leaves
or the owner stops sharing. The owner cannot leave.

### 3.1e Album links and trip files (ADR 034, step 5, migration `0028`)

`app.trip_album`: `id`, `trip_id` (fk, cascade), `url` (https, at most 2000 characters, unique per
trip), `name` (1 to 80), `added_by` (fk to `app.person`, set null), `created_at`; at most 20 per
trip. `app.trip_file`: `id`, `trip_id` (fk, cascade), `kind` (`cover` now, `document` from step 6;
at most one cover per trip), `storage_key` (unique; `trips/<trip>/cover-<id>.jpg` in the private
`trip-files` bucket), `content_type`, `bytes`, `sha256`, `uploaded_by`, `created_at`.
`app.trip_file_orphan` lists the objects whose row was deleted (a trigger), so the API removes them
from the bucket after the change commits (a replaced cover, a deleted trip). The sum of `bytes` is
the storage budget's count. `Trip.own_cover` (id, bytes, upload time) is read with the trip.

### 3.1f Shared documents (ADR 034, step 6, migration `0029`)

`app.trip_document`: `id` (pk and fk to `app.trip_file`, cascade: the file row owns it), `trip_id`
(fk, cascade), `title` (1 to 120), `category` (`ticket`, `booking`, `transport`, `other`), `link`
(jsonb: `{kind: trip}`, `{kind: day, day}`, `{kind: place, key, name, day}` or `{kind: leg, day,
name}`, as ADR 023 keeps it on the phone), `doc_date`, `notes` (at most 500), `file_name`,
`updated_by` (fk to `app.person`, set null), `updated_at`. The file is the `app.trip_file` row of the
same id, kind `document`, key `trips/<trip>/document-<id>`, stored as uploaded.

### 3.1d Who changed it (ADR 034, step 4, migration `0027`)

`app.itinerary.changed_by` (fk to `app.person`, `ON DELETE SET NULL`) and `changed_at`, set by a
trigger whenever a plan is created or its `version` changes; `app.trip.updated_by`, set whenever
`updated_at` changes. Both come from the transaction setting `detour.person`, which the API sets to
the caller's person at the start of every transaction (`app.current_person()`); outside the API
(imports, scripts) they keep their value.

### 3.1c Names and links (ADR 034, step 3, migration `0026`)

`app.person.display_name` (1 to 40 characters, optional): shown to the people on your shared trips.
`app.person_link`: `person_a`, `person_b` (fks to `app.person`, cascade; stored once per pair with
`person_a < person_b`), `created_at`: two people who may share trips, made with an **invite code**
(`app.link_code.kind = 'invite'`; one use, 10 minutes, hashed with a purpose of its own so it can
never add a phone, and a phone's code can never link a person). At most 5 links per person.
Unlinking leaves trips already shared as they are. A phone that joins a person brings its links.

`app.link_code`: `code_hash` (pk, HMAC-SHA256 of the code keyed with `DETOUR_TOKEN_SECRET`; the code
itself is never stored), `person_id` (fk, cascade), `created_by` (the phone that showed it, fk,
cascade), `created_at`, `expires_at` (10 minutes later), `used_at` and `used_by` (set together). A
person has at most one unused code: making a new one deletes the old. Used and expired rows are
kept (a few bytes each) as a record of which phone joined when.

### 3.2 `app.trip`

| Field | Notes |
|---|---|
| `id`, `owner_person_id` | fk to `app.person`, `ON DELETE CASCADE` (`installation_id` before migration `0025`); who may read it is `app.trip_member` |
| `title` | 1 to 120 characters |
| `destination_kind`, `destination_ref` | `city` (a `geo.city.id`), `area` (a `geo.admin_area.id`) `route` (a multi-city trip, ADR 024: the first stop's city id) or `place` (ADR 027, migration `0016`: a place outside the imported regions, `destination_ref` is `photon:N123`, `geonames:123`, `area:<uuid>` or `manual` and nothing is checked against `geo`); existence and region availability of the other kinds are checked by the API |
| `destination_country` | ISO 3166-1 alpha-2, known for a place trip when the source gave it (migration `0016`); null otherwise |
| `stops_version` | Counts applied stop edits of a multi-city trip (migration `0012`); 0 otherwise |
| `uses_car` | false: Optimize only considers walking (migration `0018`); true by default |
| `destination_name`, `destination_point` | Snapshot taken at creation |
| `duration_days` | 1 to 30; cannot change once the trip has itineraries |
| `start_date` | Optional; when set or changed, itinerary day dates follow |
| `selected_itinerary_id` | fk, `ON DELETE SET NULL` |
| `status`, `archived_at` | `active`, `past`; a past trip has `archived_at` (check constraint) |
| `is_seed`, `created_at`, `updated_at` | |

### 3.2a `app.trip_stop`: the cities of a multi-city trip (ADR 024, migration `0012`)

`id`, `trip_id` (fk, `ON DELETE CASCADE`), `position` (1 to 6, unique per trip), `city_id` (a
`geo.city.id`, **no foreign key**), snapshots of `city_name`, `country_iso2` and `point` (GiST
index), `days` (at least 1). The stops' days add up to the trip's `duration_days`.
`app.itinerary.stops_version` records the trip's stop version a plan was made for (null for city and
area trips); a plan whose version is not the trip's cannot be chosen. An `itinerary_day` arrival leg
may be `unknown` (mode and confidence) with no seconds or metres: a leg into or out of a country
travelled by rail. `app.change_set.action` gains `edit_stops`, whose proposal also carries the trip's
new stops, name and length; applying it may add or delete day rows.

### 3.3 `app.itinerary`, `app.itinerary_day`, `app.itinerary_item`, `app.transfer`
A proposed or selected plan. Variants of one generation share a `generation_id`.

| `itinerary` | Notes |
|---|---|
| `profile` | `essentials`, `wider`, or `manual` (an empty plan filled by hand; the only kind before Phase 4) |
| `status` | `proposed`, `selected`, `superseded`; at most one `selected` per trip (kept by the API when the selection changes) |
| `version` | Starts at 1; incremented by every accepted item edit and every applied change set. The version it replaces is kept in `app.itinerary_version` (section 3.7) |
| `engine_version`, `config_version` | `manual` for manual itineraries; for engine itineraries for example `planner-1.0.0` and `2026-11-12.2+durations-2026-11-12.1`; after a recalculation (ADR 018, ADR 019) `planner-2.0.0+recalc-1.1.0` and `<config>+recalc-2026-11-13.2` (before ADR 019: `recalc-1.0.0` and `recalc-2026-11-13.1`) |
| `import_run_id` | The data version used; null for manual itineraries; not a foreign key |
| `seed`, `diversity_score`, `summary` | Engine itineraries (Phase 4, ADR 014): `seed` 0 (no randomness is used); `diversity_score` the Jaccard similarity of the generation's two variants (null with one); `summary` holds `stats` (visits, minutes, transfers by label, day utilisation and travel share in permille), `notes` (codes with parameters, rendered by fixed templates when read), `sequencer`, `estimate_version`, `jaccard_permille`; since ADR 016 the stats also hold `meals`, `meal_minutes` and `intercity_legs` (itineraries written before have a `currency_code` key, unused). `{}` for manual itineraries |

`itinerary_day`: `day_index` (1-based, unique per itinerary), `date` (null without a start date),
`base_city_id` (a `geo.city.id`, null), `base_city_name` (a snapshot of its name, null for manual
itineraries), and the inter-city leg that starts the first day at a new base city of an area
(ADR 016): `arrival_mode`, `arrival_seconds`, `arrival_meters`, `arrival_confidence`, all null or all
set (a CHECK enforces it). The leg always comes from the previous day's base city.
The API's `Day` adds the base city's position (`base_city_lat`, `base_city_lon`), read from
`geo.city` by `base_city_id` when the plan is read; it is not stored on the day (ADR 021).

| `itinerary_item` | Notes |
|---|---|
| `position` | Dense and 1-based within a day; unique per day (deferrable, so reorders are atomic) |
| `type` | `visit`, `meal`, `free_time`, `transport` (ADR 032, migration `0021`: a leg the user entered; no place, no point). A `meal` item is a restaurant or cafe stop (a place of kind `restaurant` or `cafe`); it has no meal type (`meal_type` was dropped by `0014`). A restaurant takes 75 minutes and a cafe 45 when no length is given (*proposed*, `planner/durations.py`; `duration_source = 'category_default'`); the read endpoints add the kind of the user place by identifier, never copied. Stops of plans made before ADR 026 keep their times and became the installation's own places (`0014`) |
| `place_id`, `user_place_id` | Exactly one for a visit or meal, neither for free time. A meal needs a user place of kind `restaurant` or `cafe`; a visit must not be one. `user_place_id` is `ON DELETE RESTRICT` |
| `display_name`, `display_point` | Snapshot at creation (name or, for an unnamed place, its category); user-place renames are propagated |
| `start_time`, `end_time` | Local time at the destination; both null or both set, `end > start`, same day. Unscheduled is allowed. Timed items of a day may touch but not overlap. A transport leg may have a start and no end: its length is unknown (it counts as a point for the overlap check) or it arrives after midnight (it takes the rest of its day) |
| `transport` | jsonb, set iff `type = 'transport'` (ADR 032): `mode` (`train`, `bus`, `metro_tram`, `ferry`, `taxi`, `walk`, `other`), `from_name`, `to_name` (1 to 120 characters), optional `from_lat/lon`, `to_lat/lon` (only when the end was picked from the trip), `is_journey` (it covers the day's computed arrival; the API's `Arrival.covered_by_item_id` names it) and an optional `note` (up to 500). Validated by the API (`TransportInfo`); no price, operator or booking. A leg is always `locked` and `origin = user`; `display_name` is "Train to Florence" |
| `duration_minutes`, `duration_source` | 1 to 1440; `user` or `category_default`. Null only for a transport leg whose length the user did not enter (unknown; never estimated). Engine items and imported attractions added without a duration take the category default (ADR 014); a meal or a user place needs a duration |
| `origin`, `locked`, `reasons` | `engine` or `user`; a locked item keeps its day, start and end in every recalculation and is never removed by one; an item with origin `user` (added by hand or through a change set, a restaurant added through an `add_restaurant` change set included: a meal with `origin = user` keeps its day and times, ADR 019) is mandatory: never left out (ADR 018); reason codes from the fixed template table (`planner/reasons.py`; `SEED_DATA` on seed items) |

A transport leg is the travel of its stretch: no transfer is written from the stop before it or to
the stop after it, Optimize never moves it or a stop across it, and Add a place's recalculation names
its day (`TRANSPORT_LEG_DAY`) instead of planning around it (ADR 032).

`transfer`: `from_item_id` (unique: one outgoing transfer per item), `to_item_id`, `mode`,
`seconds`, `meters`, `confidence` (`routed`, `estimated`), `geometry`. Written by the planner for
every pair of consecutive visits (Phase 4), with the values and label the travel-time service
returned; `geometry` stays null (route lines are fetched for the selected itinerary only, ADR 013).
A hand edit deletes the transfers that no longer join an item to the next one; they are not
recomputed. A recalculation (ADR 018) writes the transfers of the days it changes.

### 3.4 `app.user_place`

A place the user added that is not in `geo.place`: `kind` (`city`, `location`, `restaurant`, `cafe`),
`name`, `geom`, `source` (`manual_pin`, `search_result`), and `search_provider` (`photon`, or `geonames`
for a town from destination search saved to add it to a plan, ADR 018) with `search_ref` (for example
`N123`, an OSM node, or a GeoNames id) **iff** the source is a search result. A restaurant or cafe is
only a name, a point and a kind (Photon's `amenity` value or the user's choice): `cuisines` and
`meal_types` were dropped by `0014` because Photon cannot supply them (ADR 026). Belongs to a person (`person_id`; ADR 034); a place on a shared trip is shown to every member of that trip, but only its creator's list holds it. At most 500 per
installation.

### 3.5 `app.trip_visit`: the past-trip archive (ADR 006)

> **Amendment of 2026-11-16: no longer written.** A past trip keeps its plan (ADR 006). The rows
> below exist only for trips that became past before that date, whose plans were deleted.

> **ADR 026, history step (built, migration `0015`): the archive is also the day-by-day record.**
> `trip_visit` holds one row per base city (once each) and one per stop of the selected itinerary,
> restaurants and cafés the user added included; free time is not a stop (it is read from the times).
> "Restaurants and meals are not archived" no longer holds.
One row per base city or stop of the selected itinerary of a past trip: `kind` (`city`,
`attraction`, `restaurant`, `cafe`), `name` and `point` (snapshots), `geo_place_ref` (a `geo.place`
id for imported places, null for user places and cities; may no longer exist), `day_number`,
`position` (order within the day), `start_time` and `duration_minutes` (all three null for a city
row and for rows archived before `0015`: their plans were already gone), `confirmed` (the visited
flag: set when archived; the user can clear it). A town the user added that is also a base city is
not listed twice. Notes (ADR 021) are not built, so there is no note column.
Restaurants and meals are not archived (until step 5 of ADR 026). Each city is listed once, however many days are spent there.
The archive stores no city for an attraction: the app groups attractions under the nearest city row.
`GET /v1/trips/{id}/archive` reports the counts and `size_bytes`, the stored row data of the trip
row and its visit rows (`pg_column_size`; no indexes or page overhead).

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
| `action` | `add_place` (with `place_id` **or** `user_place_id`, and `duration_minutes` if given), `remove_place` (with `item_id`) `edit_stops` (ADR 024) or `optimize` (ADR 029, migration `0017`; names no place, like `edit_stops`; with `restores_version` set it is an undo). `add_restaurant` (Phase 8, ADR 019) is gone: its rows were deleted by `0014` |
| `slot_day` | The one day an add-place preview was restricted to (ADR 021, step 4); null otherwise. `slot_meal` and `after_item_id` were dropped by `0014` |
| `target_name` | Snapshot of the place's name |
| `status` | `pending` (previewed), `applied`, `discarded`, `expired` (the itinerary changed, or a newer preview replaced it); `decided_at` iff not pending; `result_version` iff applied |
| `restores_version` | Set when applying restores that stored version exactly (removing the place the latest change added, or undoing an Optimize) |
| `proposal` | The plan rows to write (same shape as a version's `state`); **cleared once decided** |
| `diff`, `notes` | What the preview showed, kept after the decision |

| `itinerary_version` | Notes |
|---|---|
| `(itinerary_id, version)` | pk; the itinerary fk cascades |
| `state` | The version's days, items and transfers as rows, with its summary and engine, configuration and data versions. Items keep only their own name and point snapshots; venue types and cuisines stay in `geo` |
| `replaced_at`, `change_set_id` | When it was replaced, and by which change set (null: a hand edit) |

Every replaced version is kept, up to 30 per itinerary (the oldest are removed first).

### 3.8 `app.place_name_override` (ADR 025)

"Edit display name": `id`, `person_id` (fk to `app.person`, `ON DELETE CASCADE`; `installation_id` before `0025`), `entity_kind` and
`entity_ref` (a `geo.place` id as text; no foreign key), `name` (1 to 120 characters) and `name_norm`,
`original_name` (the local name when it was approved), `approved_at`. Unique per installation and
entity: it applies to that place only, for that installation only, and is removed by
`DELETE /v1/places/{id}/display-name`. Setting or removing it rewrites the installation's item
snapshots (`display_name`) and archived visit names of that place; a later generation applies it too.

## 4. Restaurant prices

**Removed** (ADR 017, owner decision of 2026-11-13). `app.price_record`, the trip's currency, meal
budget and price-band thresholds, and `geo.fx_rate` were dropped by migration `0006`. Places to eat
carry no cuisine, meal type or price (ADR 026). Bringing prices back needs a new ADR.

## 5. Lifecycle and deletion rules

| Event | What happens |
|---|---|
| **Import of a region** | Upsert by deterministic id inside one transaction; **a row that did not change is not written** (a rewrite leaves a dead copy and would double the database on every re-import). Places missing from the new extract are **deleted with their source, signal and profile rows**, unless an itinerary item in `app` still names them: those stay with `is_active = false` and are cleared by a later import once nothing names them. Administrative areas missing from the extract are deleted (a trip keeps its own destination snapshot). After the commit the tables are vacuumed; after a clean-up of 1,000 rows or more they are rewritten (`VACUUM FULL`) so the file shrinks. A failed import changes no data and leaves a `failed` import run |
| **Gazetteer import** | Upserts countries, currencies, codes and cities; cities of the imported countries that are gone from the file are deleted (`place.city_id` becomes null); places get their nearest city |
| **Import a region from the app** (`POST /v1/regions/{id}/import`, ADR 033, owner only) | Inserts a `geo.import_job` (`requested`) and asks GitHub to run the "Import region" workflow, which sets it `running`, then `succeeded` or `failed`. Not reported on for 45 minutes: shown as stalled. No `app` row is written; `requested_by` is an identifier only |
| **Remove a region** (`DELETE /v1/regions/{id}`, ADR 033, owner only) | Deletes the region's places (with source and signal rows) and administrative areas **except** those an itinerary item, a past-trip record, a trip destination or a display-name override still names: those become `is_active = false` and keep their names and photo link. Deletes the stored names, name lookups and photo lookups of the places that are gone. The region becomes `disabled` with no current data version; the gazetteer, travel times and `app` rows are untouched. A later import of the region reactivates the kept places |
| **Region status** | Set by each import from gates 4 to 6 (ADR 009; gates 1 to 3 were retired by ADR 026): `available` or `disabled`. There is no manual override |
| **First API call of an installation** | Creates its `app.installation` row |
| **Delete a trip** | Cascades to its itineraries, days, items, transfers and archive rows. User places stay |
| **Delete an itinerary** | Cascades to days, items and transfers; clears the trip's selection if it was selected |
| **Delete an item** | Later items of the day move up; the itinerary version increases (the replaced version is kept) |
| **Preview a change** (ADR 018) | Stores a `pending` change set; expires the itinerary's other pending one; the itinerary is not touched |
| **Apply a change** | Keeps the current version in `itinerary_version`, writes the proposal, increments the version, clears the proposal |
| **Discard a change** | The change set becomes `discarded` and loses its proposal |
| **Delete a user place** | Refused (409) while an item uses it |
| **Name lookup** (ADR 025) | Writes the entity's `geo.place_name` rows (replacing its earlier Wikidata rows) and its lookup row. `prune` (the `names` command) deletes expired names of entities nothing in `app` names (items, past-trip visits, overrides, a trip's cities and area), and the names and lookups of entities gone from `geo`; named entities keep theirs and are refreshed when due |
| **Archive a trip** (`POST /v1/trips/{id}/archive`, ADR 006, amended 2026-11-16) | Sets `status = past` and `archived_at`; **nothing is deleted** except itinerary versions beyond the newest five of each plan. The plan, routes, stays and chosen plan stay; no `trip_visit` rows are written. **Since 2026-11-17 a past trip is read-only** (409 `trip_past` on every change to its plan, stays, cities, dates, name and cover) until `POST /v1/trips/{id}/reopen` makes it `active` again and sets `reopened_at` (migration `0022`), which the two-day rule respects. (Before the amendment it wrote one `trip_visit` per base city (once each) and per stop (visit or meal item) of the *selected* itinerary with its day, order, start and length (or the destination city if there is none and the destination is a city); then **every** itinerary of the trip is deleted (days, items, transfers, route geometry, versions and change sets go with them; user places stay); the trip becomes `past`. One-way (the status).) |
| **A trip's last day passes** (ADR 006, amendment of 2026-11-13) | Reading the trips (`GET /v1/trips`, `GET /v1/trips/{id}`) first archives the caller's active, non-seed trips that have a start date and whose last day ended two days ago or more (the same step as above). No scheduled job. A trip without a start date never becomes past by itself |
| **Delete an installation** (no endpoint; operator action) | Cascades to everything it owns. Tokens are stateless, so the app would register a new installation |
| **Limits** | 100 trips per installation, 5 itineraries per trip, 40 items per day, 500 user places, 30 kept versions per itinerary, one pending change set per itinerary |

Not built: a backup of `app` (ADR 005: Supabase Free has none).

## 6. Provider-data ownership and licence handling

- **`geo` holds data derived from OpenStreetMap under ODbL, and GeoNames data under CC BY 4.0.**
  Each set carries its licence: `geo.place_source.licence_code` for every place, and
  `licence_code` on cities, countries, currencies and admin areas. `GET /v1/attributions` lists
  the credits the app must show.
- **OSM data is stored as ODbL source records.** A place is the real-world entity; its OSM object
  is one `geo.place_source` row (source `osm`, the reference, the licence, the tags). A different
  source (Overture, Foursquare OS Places, Wikidata) would be another row for the same place with
  its own licence, never merged into the OSM row (CLAUDE.md, architecture rules).
- **Derived values** (`category`, `score`) are computed from source
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
- **Names from Wikidata** (CC0) are stored as their own rows in `geo.place_name` with their licence,
  never merged into the OSM rows; OSM names are read where the import put them (ADR 025).
- **Photon results** (ODbL OSM data) are not stored in `geo`. They are cached for a week in
  `app.provider_cache` and reach `geo`-independent storage only when the user saves one as a user
  place (`search_provider`, `search_ref`).
- **Opening hours and prices from providers are not stored** (ADR 003; ADR 002 rejects the
  providers that have them).

## 7. The import report and the gates

Every import stores a report in `geo.import_run.report` (and writes `report.json`, `report.md`
and `review-sample.json` as workflow artifacts): source file and hash, places by kind with the
share named, with Wikidata and with Latin letters in the name, administrative
areas, **excluded objects per class and reason**, the largest categories, the size of the `geo`
schema (measured after the vacuum that follows the commit, which is the size gate 6 uses), and
gates 4 to 6 of [ADR 009](decisions/009-region-readiness-thresholds.md) with their values (gates 1 to 3 concerned restaurants and were retired by ADR 026). A region is `available` only if every gate passes; an unknown value never passes.

## 8. Photos

**Reference photos (destinations and attractions)** are a separate thing from the user's photos
below. Accepted in [ADR 022](decisions/022-destination-and-attraction-photos.md); the tables are built
(migration `0009`), nothing fills them until the "Resolve images" workflow runs:
`geo.image` (a Commons file with author, licence, size, average colour and the Supabase Storage key),
`geo.image_lookup` (what was found or not found for a place or city, and when) and a nullable
`app.trip.cover_image_id` with no foreign key (migration `0009`). They carry their own licence and
sit outside the ODbL data. Migration `0011` (ADR 022 amendment): `geo.admin_area.wikidata_id` (the
boundary's `wikidata` tag, kept by the import; areas imported earlier have none until their region is
imported again), the lookup kind `area`, and `geo.cover_preview` (`id`, `commons_file`,
`storage_key` under `previews/`, `created_date`): the 500 px previews of "Change photo", deleted after
a week. The background resolver and the candidates write these tables from the API itself.

**The user's own photos:**

`app.photo`: `id`, `installation_id`, `trip_id` (always), `day_id`, `city_id`, `itinerary_item_id`
(the most specific association, nullable), `local_uri`, `storage_key` (nullable), `taken_at`,
`geom` (only with the user's consent to keep location), `checksum`, `width`, `height`, `bytes`.
In the first photo phase the files and this table live on the device only (D9). **Not built:** the
first photo step (ADR 031) keeps only album links and a cover picture, on the phone (section 8a).

## 8a. On the device: trip documents (ADR 023)

Not in either schema: trip documents (tickets, bookings, transport, insurance) live only on the
phone. The app's SQLite database (`detour-cache.db`) has a `trip_document` table (`id`, `trip_id`,
`json`, `created_at`) beside the read cache; each row holds the title, kind, link (whole trip, day
number, a place key with its name and day as linked, or a journey's day and town), file name, type,
size and the location of the copy in the app's private storage. Deleting a trip deletes its rows and
files on the phone. The backend stores nothing about documents.

**Album links and the phone cover (ADR 031):** a `trip_extra` table in the same database
(`trip_id` primary key, `json`): `albums` (each `id`, `name`, `url` (https only), `createdAt`; up to
20) and `cover` (`uri` of the copy under the app's `covers/` folder, the picked `fileName`, `setAt`)
or null. Deleting a trip deletes its row and the cover copy. The backend stores nothing about them.

## 8b. The trip file (ADR 028)

Not a table: the format of what leaves the app. A `.detour` file is a zip holding `trip.json` and,
when documents are included, `documents.json` and `documents/<n>.<ext>` (generated names).
`trip.json` is `{format: "detour-trip", format_version: 2, exported_at, trips: [...]}` (version 2
since 2026-11-16, ADR 032; version 1 files still import). Each trip
has `title`, `destination` (`kind`, `ref` only when it is a provider reference such as
`geonames:123`, `photon:N123`, `area:<uuid>` or `manual`, `name`, `lat`, `lon`, `country_iso2`),
`duration_days`, `start_date`, `status` and `archived_at`, `stops` (the cities of a multi-city trip,
for reference), `days` (the chosen plan: day number, base city name and the stops with position,
kind `sight`, `city`, `place`, `restaurant`, `cafe` or (version 2) `transport`, name, point (none for
a leg), start time, length (none for a leg of unknown length), whether the user set the length,
locked, and for a leg its `transport` details), version 2's `stays` (name, point, first and last day)
and `uses_car`, and, for a past trip, `visits` (the archive rows with their visited
mark). It holds no installation, trip, plan or place identifier, no `geo` identifier, no travel
time and no cover photo. `documents.json` lists each document with its trip's position, title,
kind, a link by name and day, date, note, file name and type. `albums.json` (ADR 031, written
whenever a trip has album links) is `{format: "detour-albums", format_version: 1, albums:
[{trip_index, name, url}]}`; the cover picture from the phone is not in the file. Import (`repo/exchange.py`) writes
every trip as a new `place` trip, a manual itinerary of the user's own places (`app.user_place`,
`source = manual_pin`) and, for a past trip, `app.trip_visit` rows with no `geo` reference.
A transport leg imports as a leg of the manual plan, in the file's order; stays are added after the
plan. A version 1 file imports with a car and no stays, as before. Version 1 keeps importing in later
versions.

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
