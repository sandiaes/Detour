"""Create the geo schema: imported open data (docs/data-model.md, section 2).

Everything here can be rebuilt from its sources by the import commands. ``geo`` never refers to
``app``. Enumerations are ``text`` columns with CHECK constraints, which are easier to extend than
native enum types. Geometry columns use SRID 4326; every one has a GiST index.

PostGIS and pg_trgm are enabled with ``IF NOT EXISTS``: on Supabase the owner enables PostGIS in
the dashboard first (docs/deployment.md), and the statement is then a no-op.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UPGRADE = """
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Licences of the data held in geo. Source records point here (section 5 of data-model.md).
CREATE TABLE geo.licence (
    code        text PRIMARY KEY,
    name        text NOT NULL,
    url         text NOT NULL,
    attribution text NOT NULL,
    share_alike boolean NOT NULL
);
INSERT INTO geo.licence (code, name, url, attribution, share_alike) VALUES
    ('ODbL-1.0', 'Open Database License 1.0',
     'https://opendatacommons.org/licenses/odbl/1-0/', '© OpenStreetMap contributors', true),
    ('CC-BY-4.0', 'Creative Commons Attribution 4.0 International',
     'https://creativecommons.org/licenses/by/4.0/', 'GeoNames (https://www.geonames.org)', false),
    ('CC0-1.0', 'Creative Commons Zero 1.0',
     'https://creativecommons.org/publicdomain/zero/1.0/', 'Wikidata', false);

CREATE TABLE geo.region (
    id                    text PRIMARY KEY CHECK (id ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    name                  text NOT NULL,
    country_codes         text[] NOT NULL CHECK (cardinality(country_codes) > 0),
    geom                  geometry(MultiPolygon, 4326),
    status                text NOT NULL DEFAULT 'disabled'
                          CHECK (status IN ('available', 'importing', 'disabled')),
    current_import_run_id uuid
);

CREATE TABLE geo.import_run (
    id                uuid PRIMARY KEY,
    region_id         text NOT NULL REFERENCES geo.region (id),
    status            text NOT NULL DEFAULT 'running'
                      CHECK (status IN ('running', 'succeeded', 'failed')),
    importer_version  text NOT NULL,
    rules_version     text NOT NULL,
    source_url        text,
    source_sha256     text,
    source_bytes      bigint,
    osm_snapshot_date date,
    geonames_date     date,
    wikidata_date     date,
    counts            jsonb NOT NULL DEFAULT '{}',
    report            jsonb,
    started_at        timestamptz NOT NULL,
    finished_at       timestamptz,
    error             text
);
CREATE INDEX import_run_region_idx ON geo.import_run (region_id, started_at DESC);

ALTER TABLE geo.region
    ADD CONSTRAINT region_current_import_run_fk
    FOREIGN KEY (current_import_run_id) REFERENCES geo.import_run (id);
CREATE INDEX region_geom_gix ON geo.region USING gist (geom);

CREATE TABLE geo.currency (
    code        text PRIMARY KEY CHECK (code ~ '^[A-Z]{3}$'),
    name        text NOT NULL,
    symbol      text,
    minor_units smallint CHECK (minor_units BETWEEN 0 AND 4),
    licence_code text NOT NULL DEFAULT 'CC-BY-4.0' REFERENCES geo.licence (code)
);

CREATE TABLE geo.country (
    iso2                  text PRIMARY KEY CHECK (iso2 ~ '^[A-Z]{2}$'),
    iso3                  text NOT NULL CHECK (iso3 ~ '^[A-Z]{3}$'),
    name                  text NOT NULL,
    default_currency_code text REFERENCES geo.currency (code),
    geom                  geometry(MultiPolygon, 4326),
    licence_code          text NOT NULL DEFAULT 'CC-BY-4.0' REFERENCES geo.licence (code)
);
CREATE INDEX country_geom_gix ON geo.country USING gist (geom);

-- Names for the admin1 and admin2 codes of the cities (GeoNames admin1CodesASCII, admin2Codes).
CREATE TABLE geo.admin_code (
    code         text PRIMARY KEY,           -- for example AT.01 or AT.01.101
    level        smallint NOT NULL CHECK (level IN (1, 2)),
    country_iso2 text NOT NULL REFERENCES geo.country (iso2),
    name         text NOT NULL,
    ascii_name   text NOT NULL,
    geoname_id   bigint
);

CREATE TABLE geo.city (
    id            bigint PRIMARY KEY,        -- GeoNames identifier
    name          text NOT NULL,
    ascii_name    text NOT NULL,
    name_norm     text NOT NULL,             -- lower case, accents removed: what search matches
    alt_names     text[],
    alt_names_norm text,
    country_iso2  text NOT NULL REFERENCES geo.country (iso2),
    admin1_code   text,
    admin2_code   text,
    population    integer CHECK (population >= 0),   -- NULL when unknown (GeoNames uses 0)
    timezone      text,
    feature_code  text,
    geom          geometry(Point, 4326) NOT NULL,
    licence_code  text NOT NULL DEFAULT 'CC-BY-4.0' REFERENCES geo.licence (code),
    geonames_date date
);
CREATE INDEX city_geom_gix ON geo.city USING gist (geom);
CREATE INDEX city_name_trgm ON geo.city USING gin (name_norm gin_trgm_ops);
CREATE INDEX city_ascii_trgm ON geo.city USING gin (ascii_name gin_trgm_ops);
CREATE INDEX city_alt_trgm ON geo.city USING gin (alt_names_norm gin_trgm_ops);
CREATE INDEX city_country_pop_idx ON geo.city (country_iso2, population DESC NULLS LAST, id);

CREATE TABLE geo.admin_area (
    id                  uuid PRIMARY KEY,
    region_id           text NOT NULL REFERENCES geo.region (id),
    name                text NOT NULL,
    name_norm           text NOT NULL,
    level               smallint NOT NULL,   -- OSM admin_level as mapped (4 or 6 are imported)
    country_iso2        text REFERENCES geo.country (iso2),
    geom                geometry(MultiPolygon, 4326) NOT NULL,
    source              text NOT NULL DEFAULT 'osm' CHECK (source IN ('osm', 'overture')),
    source_ref          text NOT NULL,
    licence_code        text NOT NULL REFERENCES geo.licence (code),
    is_active           boolean NOT NULL DEFAULT true,
    last_seen_import_run_id uuid NOT NULL REFERENCES geo.import_run (id),
    UNIQUE (source, source_ref)
);
CREATE INDEX admin_area_geom_gix ON geo.admin_area USING gist (geom);
CREATE INDEX admin_area_name_trgm ON geo.admin_area USING gin (name_norm gin_trgm_ops);
CREATE INDEX admin_area_region_idx ON geo.admin_area (region_id, level);

CREATE TABLE geo.place (
    id                      uuid PRIMARY KEY,   -- derived from the source reference: stable
    region_id               text NOT NULL REFERENCES geo.region (id),
    kind                    text NOT NULL
                            CHECK (kind IN ('attraction', 'restaurant', 'transport_hub', 'other')),
    category                text NOT NULL,
    name                    text,               -- NULL = the source has no name
    name_norm               text,
    names_i18n              jsonb,
    geom                    geometry(Point, 4326) NOT NULL,
    address                 jsonb,
    city_id                 bigint REFERENCES geo.city (id) ON DELETE SET NULL,
    default_visit_minutes   integer CHECK (default_visit_minutes > 0),
    is_active               boolean NOT NULL DEFAULT true,
    first_import_run_id     uuid NOT NULL REFERENCES geo.import_run (id),
    last_seen_import_run_id uuid NOT NULL REFERENCES geo.import_run (id),
    CHECK ((name IS NULL) = (name_norm IS NULL))
);
CREATE INDEX place_geom_gix ON geo.place USING gist (geom);
CREATE INDEX place_name_trgm ON geo.place USING gin (name_norm gin_trgm_ops);
CREATE INDEX place_region_kind_idx ON geo.place (region_id, kind) WHERE is_active;
CREATE INDEX place_city_idx ON geo.place (city_id) WHERE city_id IS NOT NULL;

CREATE TABLE geo.place_source (
    place_id      uuid NOT NULL REFERENCES geo.place (id) ON DELETE CASCADE,
    source        text NOT NULL CHECK (source IN ('osm', 'wikidata', 'overture', 'fsq_os')),
    source_ref    text NOT NULL,               -- for example node/123
    licence_code  text NOT NULL REFERENCES geo.licence (code),
    tags          jsonb NOT NULL,              -- source attributes the importer reads, unmodified
    import_run_id uuid NOT NULL REFERENCES geo.import_run (id),
    PRIMARY KEY (place_id, source, source_ref)
);

CREATE TABLE geo.restaurant_profile (
    place_id              uuid PRIMARY KEY REFERENCES geo.place (id) ON DELETE CASCADE,
    cuisines              text[],              -- NULL = no cuisine tag
    venue_type            text NOT NULL
                          CHECK (venue_type IN ('restaurant', 'cafe', 'fast_food', 'bar', 'pub',
                                                'food_court', 'other')),
    meal_types            text[],              -- derived from the venue type by a fixed rule
    diet_flags            text[],              -- NULL = no diet:* tag
    provider_price_level  smallint CHECK (provider_price_level BETWEEN 1 AND 4),
    provider_price_source text,
    CHECK ((provider_price_level IS NULL) = (provider_price_source IS NULL))
);

CREATE TABLE geo.place_signal (
    place_id       uuid PRIMARY KEY REFERENCES geo.place (id) ON DELETE CASCADE,
    wikidata_id    text CHECK (wikidata_id ~ '^Q[0-9]+$'),
    sitelink_count integer CHECK (sitelink_count >= 0),   -- NULL: Wikidata is not fetched yet
    osm_signals    jsonb NOT NULL,
    score          numeric(8, 2) NOT NULL
);
CREATE INDEX place_signal_wikidata_idx ON geo.place_signal (wikidata_id)
    WHERE wikidata_id IS NOT NULL;

-- Filled by the travel-time service (Phase 3). The table exists so the schema is complete.
CREATE TABLE geo.travel_time (
    from_ref       text NOT NULL,
    to_ref         text NOT NULL,
    mode           text NOT NULL CHECK (mode IN ('walk', 'drive')),
    seconds        integer NOT NULL CHECK (seconds >= 0),
    meters         integer NOT NULL CHECK (meters >= 0),
    confidence     text NOT NULL CHECK (confidence IN ('routed', 'estimated')),
    engine_version text NOT NULL,
    import_run_id  uuid REFERENCES geo.import_run (id) ON DELETE SET NULL,
    created_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (from_ref, to_ref, mode, engine_version)
);

-- Filled by the daily FX job (Phase 8).
CREATE TABLE geo.fx_rate (
    rate_date  date NOT NULL,
    base_code  text NOT NULL REFERENCES geo.currency (code),
    quote_code text NOT NULL REFERENCES geo.currency (code),
    rate       numeric(24, 12) NOT NULL CHECK (rate > 0),
    provider   text NOT NULL,
    fetched_at timestamptz NOT NULL,
    PRIMARY KEY (rate_date, base_code, quote_code, provider),
    CHECK (base_code <> quote_code)
);
"""

DOWNGRADE = """
DROP TABLE IF EXISTS geo.fx_rate;
DROP TABLE IF EXISTS geo.travel_time;
DROP TABLE IF EXISTS geo.place_signal;
DROP TABLE IF EXISTS geo.restaurant_profile;
DROP TABLE IF EXISTS geo.place_source;
DROP TABLE IF EXISTS geo.place;
DROP TABLE IF EXISTS geo.admin_area;
DROP TABLE IF EXISTS geo.city;
DROP TABLE IF EXISTS geo.admin_code;
DROP TABLE IF EXISTS geo.country;
DROP TABLE IF EXISTS geo.currency;
ALTER TABLE geo.region DROP CONSTRAINT IF EXISTS region_current_import_run_fk;
DROP TABLE IF EXISTS geo.import_run;
DROP TABLE IF EXISTS geo.region;
DROP TABLE IF EXISTS geo.licence;
"""


def upgrade() -> None:
    # One statement per call: psycopg runs a multi-statement string as one simple query, which
    # is fine for DDL, so the whole script is sent at once.
    op.execute(UPGRADE)


def downgrade() -> None:
    # Extensions are left installed: other schemas or the hosting provider may rely on them.
    op.execute(DOWNGRADE)
