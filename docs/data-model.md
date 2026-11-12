# Data model

Status: **proposed**. This is a logical model for review, not a migration. Names and types are
indicative; the physical schema is written in Phase 2.

## 1. Overview

Two PostgreSQL schemas with different owners and different licence positions:

| Schema | Contents | Origin | Rebuildable |
|---|---|---|---|
| `geo` | Regions, places, gazetteer, countries, currencies, FX rates, travel times | Imported open data | Yes, from sources |
| `app` | Installations, trips, itineraries, items, price records, photos (future) | Created by users and by the planning engine | No |

`app` rows refer to `geo` rows by identifier and never copy their attributes. An itinerary item
keeps a small display snapshot (name, coordinates) so that a re-import cannot break an accepted
plan.

```
geo.region ──< geo.import_run
geo.country ──< geo.city            geo.currency ──< geo.fx_rate
geo.place ──< geo.place_source
geo.place ──1 geo.restaurant_profile
geo.place ──1 geo.place_signal
geo.travel_time (place pair, mode)

app.installation ──< app.trip ──< app.itinerary ──< app.itinerary_day ──< app.itinerary_item
app.itinerary_item >── geo.place | app.user_place
app.itinerary_item ──< app.transfer (to the next item)
app.price_record >── geo.place | app.user_place, optionally >── app.itinerary_item
app.photo >── trip, day, city, item        (future phase)
```

## 2. `geo` schema — imported reference data

### `geo.region`
A unit of import and of routing coverage.

| Field | Type | Notes |
|---|---|---|
| `id` | text | Slug, for example `es-andalucia` |
| `name` | text | |
| `geom` | multipolygon | Coverage boundary |
| `status` | enum | `available`, `importing`, `disabled` |
| `current_import_run_id` | fk | Data version in use |

### `geo.import_run`
One execution of the import pipeline. Itineraries record the run they were built on.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | |
| `region_id` | fk | |
| `osm_snapshot_date` | date | From the extract |
| `geonames_date`, `wikidata_date` | date | |
| `counts` | jsonb | Places by kind; share with cuisine, Wikidata link |
| `started_at`, `finished_at` | timestamptz | |

### `geo.country` and `geo.currency`

| Table | Fields |
|---|---|
| `country` | `iso2` (pk), `iso3`, `name`, `default_currency_code`, `geom` (optional) |
| `currency` | `code` (ISO 4217, pk), `name`, `symbol`, `minor_units` |

### `geo.city`
The destination gazetteer (from GeoNames).

| Field | Type | Notes |
|---|---|---|
| `id` | bigint | GeoNames identifier |
| `name`, `ascii_name` | text | Trigram-indexed for search |
| `alt_names` | text[] | |
| `country_iso2` | fk | |
| `admin1_code`, `admin2_code` | text | With a lookup table for names |
| `population` | integer | Ranking signal for search and base-city selection |
| `timezone` | text | IANA name; used for local meal times and day boundaries |
| `geom` | point | |

Administrative **areas** used as destinations (a province or region) are stored in
`geo.admin_area` (`id`, `name`, `level`, `country_iso2`, `geom` multipolygon, `source`), taken
from OSM boundaries in the extract or, later, Overture divisions.

### `geo.place`
One real-world place that can appear in an itinerary.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | Stable across imports when the source identifier is unchanged |
| `region_id` | fk | |
| `kind` | enum | `attraction`, `restaurant`, `transport_hub`, `other` |
| `category` | text | Our normalised category (for example `museum`, `viewpoint`, `cafe`) |
| `name` | text | Trigram-indexed |
| `names_i18n` | jsonb | Language → name |
| `geom` | point | Representative point; polygons reduced to a point on surface |
| `address` | jsonb | As available |
| `city_id` | fk, nullable | Nearest or containing gazetteer city |
| `default_visit_minutes` | integer, nullable | From the category rule table; null for restaurants |
| `is_active` | boolean | False when the place disappears from a later import |

### `geo.place_source`
Provenance. One row per source record that contributed to a place.

| Field | Type | Notes |
|---|---|---|
| `place_id` | fk | |
| `source` | enum | `osm`, `wikidata`, `overture`, `fsq_os` |
| `source_ref` | text | For example `node/123`, `Q9141` |
| `license` | text | For example `ODbL-1.0`, `CC0-1.0` |
| `tags` | jsonb | Raw source attributes, unmodified |
| `import_run_id` | fk | |

### `geo.restaurant_profile`

| Field | Type | Notes |
|---|---|---|
| `place_id` | pk, fk | |
| `cuisines` | text[] | Normalised from the semicolon-separated `cuisine` tag |
| `venue_type` | enum | `restaurant`, `cafe`, `fast_food`, `bar`, `pub`, `food_court`, `other` |
| `meal_types` | text[] | `breakfast`, `lunch`, `dinner`, `snack`; derived from venue type |
| `diet_flags` | text[] | From `diet:*` tags where present |
| `provider_price_level` | smallint, nullable | 1–4. **Null in the MVP**: no licensed source |
| `provider_price_source` | text, nullable | |

### `geo.place_signal`
Ranking inputs, kept apart from descriptive data.

| Field | Type | Notes |
|---|---|---|
| `place_id` | pk, fk | |
| `wikidata_id` | text, nullable | |
| `sitelink_count` | integer, nullable | Notability proxy |
| `osm_signals` | jsonb | Flags such as heritage, tourism=attraction, has wikipedia tag |
| `score` | numeric | Deterministic score computed at import |

### `geo.travel_time`
Cache of travel times between places.

| Field | Type | Notes |
|---|---|---|
| `from_ref`, `to_ref` | text | Place identifier or a rounded coordinate key |
| `mode` | enum | `walk`, `drive` (later `transit`) |
| `seconds`, `meters` | integer | |
| `confidence` | enum | `routed`, `estimated` |
| `engine_version`, `import_run_id` | | Invalidation keys |

### `geo.fx_rate`

| Field | Type | Notes |
|---|---|---|
| `rate_date` | date | |
| `base_code`, `quote_code` | fk | |
| `rate` | numeric | Reference rate |
| `provider` | text | For example `frankfurter`, `ecb` |
| `fetched_at` | timestamptz | |

## 3. `app` schema — user data

### `app.installation`
Anonymous identity for the MVP (D5). In Phase 1 the table does not exist: the `app` schema is empty and
the token check needs no row (ADR 010). Phase 4 creates it when trips first refer to it.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | |
| `token_hash` | text | **Dropped (ADR 010).** Tokens are HMAC-signed and carry the installation id, so no hash is stored |
| `home_currency_code` | fk | Default for budgets |
| `created_at`, `last_seen_at` | timestamptz | |

### `app.trip`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | |
| `installation_id` | fk | |
| `title` | text | |
| `destination_kind` | enum | `city`, `area` |
| `destination_ref` | text | `geo.city.id` or `geo.admin_area.id` |
| `duration_days` | smallint | |
| `start_date` | date, nullable | Optional; used for display and meal-day labels |
| `currency_code` | fk | Trip currency for budgets |
| `meal_budget_per_person` | numeric, nullable | |
| `price_band_thresholds` | jsonb | Upper bounds of the price bands, in trip currency |
| `selected_itinerary_id` | fk, nullable | |

### `app.itinerary`
A proposed or selected plan. Variants of one generation share a `generation_id`.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | |
| `trip_id` | fk | |
| `generation_id` | uuid | Groups the variants produced together |
| `profile` | enum | `essentials`, `wider` (extensible) |
| `status` | enum | `proposed`, `selected`, `superseded` |
| `version` | integer | Incremented by each accepted edit |
| `engine_version`, `config_version` | text | Reproducibility |
| `import_run_id` | fk | Data version used |
| `seed` | bigint | |
| `diversity_score` | numeric, nullable | Against the sibling variant |
| `summary` | jsonb | Totals: visits, travel time, cities |

### `app.itinerary_day`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | |
| `itinerary_id` | fk | |
| `day_index` | smallint | 1-based |
| `date` | date, nullable | |
| `base_city_id` | fk, nullable | |

### `app.itinerary_item`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | |
| `day_id` | fk | |
| `position` | smallint | Order within the day |
| `type` | enum | `visit`, `meal`, `free_time` |
| `meal_type` | enum, nullable | `breakfast`, `lunch`, `dinner` |
| `place_id` | fk to `geo.place`, nullable | |
| `user_place_id` | fk to `app.user_place`, nullable | Exactly one of the two for visits and meals |
| `display_name`, `display_point` | text, point | Snapshot |
| `start_time`, `end_time` | time | Local time of the destination |
| `duration_minutes` | integer | |
| `duration_source` | enum | `category_default`, `user` |
| `origin` | enum | `engine`, `user` |
| `locked` | boolean | Locked items are never moved by recalculation |
| `reasons` | text[] | Reason codes |

### `app.transfer`
The movement from one item to the next.

| Field | Type | Notes |
|---|---|---|
| `from_item_id`, `to_item_id` | fk | |
| `mode` | enum | `walk`, `drive` (later `transit`) |
| `seconds`, `meters` | integer | |
| `confidence` | enum | `routed`, `estimated` |
| `geometry` | linestring, nullable | For drawing on the map |

### `app.trip_visit` (archive, ADR 006)
One row per city or attraction of a past trip's selected itinerary. Written when a trip becomes
past; transfers, route geometry and other itineraries are deleted at the same time.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | |
| `trip_id` | fk | |
| `kind` | enum | `city`, `attraction` |
| `name` | text | Snapshot |
| `point` | point | Snapshot |
| `geo_place_ref` | text, nullable | The `geo` identifier it came from; may no longer exist |
| `day_number` | smallint | |
| `confirmed` | boolean | Default true; the user can clear it for skipped visits |

`app.trip` gains `status` (`active`, `past`) and `archived_at` (timestamptz, nullable).

### `app.user_place`
A place the user added that is not in `geo.place`.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | |
| `installation_id` | fk | |
| `kind` | enum | `city`, `location`, `restaurant` |
| `name` | text | |
| `geom` | point | |
| `cuisines`, `meal_types` | text[] | For restaurants |
| `source` | enum | `manual_pin`, `search_result` |
| `search_provider`, `search_ref` | text, nullable | Provenance of a search result |

## 4. Restaurant prices

### `app.price_record`
Every price the app shows comes from one of these rows. There is no hidden or inferred price.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | |
| `installation_id` | fk | |
| `place_id` / `user_place_id` | fk | The restaurant |
| `itinerary_item_id` | fk, nullable | The meal it belongs to, if any |
| `kind` | enum | `user_expected`, `user_actual`, `provider_level` |
| `amount` | numeric, nullable | Null for a level-only provider record |
| `level` | smallint, nullable | 1–4, provider records only |
| `currency_code` | fk | |
| `basis` | enum | `per_person`, `total` |
| `party_size` | smallint, nullable | Required when `basis = total` |
| `source` | text | `user`, or the provider name |
| `confidence` | enum | `high`, `medium`, `low` |
| `recorded_at` | timestamptz | |
| `note` | text, nullable | |

**Derived values (computed, not stored):**

- `per_person_amount` = `amount` when per person; `amount / party_size` when total.
- **Effective price** for a restaurant = the most recent `user_actual`; else the most recent
  `user_expected`; else a `provider_level`; else none.
- **Price band** = the band of `per_person_amount` under the trip's `price_band_thresholds`,
  after conversion to the trip currency when needed.
- **Budget fit** = `per_person_amount` against `trip.meal_budget_per_person`.

**Confidence rules:**

| Kind | Confidence |
|---|---|
| `user_actual` | high |
| `user_expected` | medium |
| `provider_level` | low |
| Any record converted between currencies | Unchanged, but flagged `approximate` and shown with the rate date |

When a conversion is displayed, the rate date and provider from `geo.fx_rate` are returned with
it, so the figure can be explained.

## 5. Licence boundary

- `geo` holds data derived from OpenStreetMap under ODbL. If such a database is adapted and
  used publicly, the adapted database must be available under ODbL on request.
- Data from other sources is stored as separate `geo.place_source` rows with their own licence,
  not merged into OSM-derived rows.
- `app` holds independent data: trips, itineraries, user places, prices, photos. It links to
  `geo` by identifier only. Under OSMF's guidance this is a Collective Database, so share-alike
  does not extend to it.
- This reading must be confirmed by legal review before any public commercial release.

## 6. Future: photos

Reserved now so later work needs no restructuring. Not built in the MVP.

### `app.photo`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | |
| `installation_id` | fk | |
| `trip_id` | fk | Always set |
| `day_id`, `city_id`, `itinerary_item_id` | fk, nullable | The most specific association available |
| `local_uri` | text | File in app storage on the device |
| `storage_key` | text, nullable | Object key when cloud backup exists |
| `taken_at` | timestamptz, nullable | |
| `geom` | point, nullable | Only with the user's consent to keep location |
| `checksum` | text | Deduplication and integrity |
| `width`, `height`, `bytes` | integer | |

In the first photo phase the files and this table live on the device only. Server-side storage
of files is a later decision (D9).

## 7. Indexes and constraints worth fixing early

- GiST indexes on every geometry column; trigram indexes on `geo.city.name` and `geo.place.name`.
- `app.itinerary_item`: unique `(day_id, position)`; check that exactly one of `place_id` and
  `user_place_id` is set for visits and meals.
- `app.price_record`: check `amount is not null or level is not null`; check `party_size` when
  `basis = total`.
- `geo.fx_rate`: unique `(rate_date, base_code, quote_code, provider)`.
