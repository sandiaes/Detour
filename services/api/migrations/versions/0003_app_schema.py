"""Create the app schema: user data (docs/data-model.md, sections 3 and 4).

``app`` refers to ``geo`` by identifier only, with **no foreign key across the schemas**: ``geo``
is rebuilt by imports (ADR 005) and an accepted plan must survive that (ADR 006, data-model.md
section 5). Columns that name a geo row (``place_id``, ``destination_ref``, ``geo_place_ref``,
``import_run_id``, currency codes) are checked for shape here and for existence by the API when
the row is written. Foreign keys inside ``app`` are real and spell out what happens on deletion.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UPGRADE = """
CREATE TABLE app.installation (
    id                 uuid PRIMARY KEY,
    home_currency_code text CHECK (home_currency_code ~ '^[A-Z]{3}$'),
    is_seed            boolean NOT NULL DEFAULT false,   -- the illustrative seed trip's owner
    created_at         timestamptz NOT NULL DEFAULT now(),
    last_seen_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE app.user_place (
    id              uuid PRIMARY KEY,
    installation_id uuid NOT NULL REFERENCES app.installation (id) ON DELETE CASCADE,
    kind            text NOT NULL CHECK (kind IN ('city', 'location', 'restaurant')),
    name            text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 200),
    geom            geometry(Point, 4326) NOT NULL,
    cuisines        text[],
    meal_types      text[],
    source          text NOT NULL CHECK (source IN ('manual_pin', 'search_result')),
    search_provider text,
    search_ref      text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    CHECK ((source = 'search_result') = (search_provider IS NOT NULL AND search_ref IS NOT NULL)),
    CHECK (kind = 'restaurant' OR (cuisines IS NULL AND meal_types IS NULL))
);
CREATE INDEX user_place_installation_idx ON app.user_place (installation_id, created_at);
CREATE INDEX user_place_geom_gix ON app.user_place USING gist (geom);

CREATE TABLE app.trip (
    id                     uuid PRIMARY KEY,
    installation_id        uuid NOT NULL REFERENCES app.installation (id) ON DELETE CASCADE,
    title                  text NOT NULL CHECK (char_length(title) BETWEEN 1 AND 120),
    destination_kind       text NOT NULL CHECK (destination_kind IN ('city', 'area')),
    destination_ref        text NOT NULL,   -- geo.city.id or geo.admin_area.id, checked by the API
    destination_name       text NOT NULL,   -- snapshot, so the trip survives a re-import (ADR 006)
    destination_point      geometry(Point, 4326) NOT NULL,
    duration_days          smallint NOT NULL CHECK (duration_days BETWEEN 1 AND 30),
    start_date             date,
    currency_code          text NOT NULL CHECK (currency_code ~ '^[A-Z]{3}$'),
    meal_budget_per_person numeric(12, 2) CHECK (meal_budget_per_person >= 0),
    price_band_thresholds  jsonb,           -- NULL until the user or Phase 8 sets the bands
    selected_itinerary_id  uuid,            -- foreign key added below
    status                 text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'past')),
    archived_at            timestamptz,
    is_seed                boolean NOT NULL DEFAULT false,
    created_at             timestamptz NOT NULL DEFAULT now(),
    updated_at             timestamptz NOT NULL DEFAULT now(),
    CHECK ((status = 'past') = (archived_at IS NOT NULL))
);
CREATE INDEX trip_installation_idx ON app.trip (installation_id, status, created_at DESC);
CREATE INDEX trip_destination_gix ON app.trip USING gist (destination_point);

CREATE TABLE app.itinerary (
    id              uuid PRIMARY KEY,
    trip_id         uuid NOT NULL REFERENCES app.trip (id) ON DELETE CASCADE,
    generation_id   uuid NOT NULL,
    profile         text NOT NULL CHECK (profile IN ('essentials', 'wider', 'manual')),
    status          text NOT NULL DEFAULT 'proposed'
                    CHECK (status IN ('proposed', 'selected', 'superseded')),
    version         integer NOT NULL DEFAULT 1 CHECK (version >= 1),
    engine_version  text NOT NULL,
    config_version  text NOT NULL,
    import_run_id   uuid,                   -- geo.import_run the plan was built on (NULL: manual)
    seed            bigint,
    diversity_score numeric,
    summary         jsonb NOT NULL DEFAULT '{}',
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX itinerary_trip_idx ON app.itinerary (trip_id, created_at);

ALTER TABLE app.trip
    ADD CONSTRAINT trip_selected_itinerary_fk
    FOREIGN KEY (selected_itinerary_id) REFERENCES app.itinerary (id) ON DELETE SET NULL;

CREATE TABLE app.itinerary_day (
    id            uuid PRIMARY KEY,
    itinerary_id  uuid NOT NULL REFERENCES app.itinerary (id) ON DELETE CASCADE,
    day_index     smallint NOT NULL CHECK (day_index >= 1),
    date          date,
    base_city_id  bigint,                   -- geo.city.id, checked by the API
    UNIQUE (itinerary_id, day_index)
);

CREATE TABLE app.itinerary_item (
    id              uuid PRIMARY KEY,
    day_id          uuid NOT NULL REFERENCES app.itinerary_day (id) ON DELETE CASCADE,
    position        smallint NOT NULL CHECK (position >= 1),
    type            text NOT NULL CHECK (type IN ('visit', 'meal', 'free_time')),
    meal_type       text CHECK (meal_type IN ('breakfast', 'lunch', 'dinner')),
    place_id        uuid,                   -- geo.place.id, checked by the API
    user_place_id   uuid REFERENCES app.user_place (id) ON DELETE RESTRICT,
    display_name    text NOT NULL,          -- snapshot
    display_point   geometry(Point, 4326),  -- snapshot
    start_time      time,
    end_time        time,
    duration_minutes integer NOT NULL CHECK (duration_minutes BETWEEN 1 AND 1440),
    duration_source text NOT NULL CHECK (duration_source IN ('category_default', 'user')),
    origin          text NOT NULL CHECK (origin IN ('engine', 'user')),
    locked          boolean NOT NULL DEFAULT false,
    reasons         text[] NOT NULL DEFAULT '{}',
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT item_position_uq UNIQUE (day_id, position) DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT item_place_xor CHECK (
        CASE WHEN type = 'free_time'
             THEN place_id IS NULL AND user_place_id IS NULL
             ELSE (place_id IS NULL) <> (user_place_id IS NULL)
        END),
    CONSTRAINT item_meal_type CHECK ((type = 'meal') = (meal_type IS NOT NULL)),
    CONSTRAINT item_times CHECK (
        (start_time IS NULL) = (end_time IS NULL)
        AND (start_time IS NULL OR end_time > start_time))
);
CREATE INDEX item_point_gix ON app.itinerary_item USING gist (display_point);
CREATE INDEX item_user_place_idx ON app.itinerary_item (user_place_id)
    WHERE user_place_id IS NOT NULL;
CREATE INDEX item_place_idx ON app.itinerary_item (place_id) WHERE place_id IS NOT NULL;

CREATE TABLE app.transfer (
    id           uuid PRIMARY KEY,
    from_item_id uuid NOT NULL REFERENCES app.itinerary_item (id) ON DELETE CASCADE,
    to_item_id   uuid NOT NULL REFERENCES app.itinerary_item (id) ON DELETE CASCADE,
    mode         text NOT NULL CHECK (mode IN ('walk', 'drive')),
    seconds      integer NOT NULL CHECK (seconds >= 0),
    meters       integer NOT NULL CHECK (meters >= 0),
    confidence   text NOT NULL CHECK (confidence IN ('routed', 'estimated')),
    geometry     geometry(LineString, 4326),
    UNIQUE (from_item_id),
    CHECK (from_item_id <> to_item_id)
);
CREATE INDEX transfer_to_idx ON app.transfer (to_item_id);
CREATE INDEX transfer_geometry_gix ON app.transfer USING gist (geometry);

CREATE TABLE app.price_record (
    id                uuid PRIMARY KEY,
    installation_id   uuid NOT NULL REFERENCES app.installation (id) ON DELETE CASCADE,
    place_id          uuid,                 -- geo.place.id, checked by the API
    user_place_id     uuid REFERENCES app.user_place (id) ON DELETE CASCADE,
    itinerary_item_id uuid REFERENCES app.itinerary_item (id) ON DELETE SET NULL,
    kind              text NOT NULL CHECK (kind IN ('user_expected', 'user_actual', 'provider_level')),
    amount            numeric(14, 2) CHECK (amount >= 0),
    level             smallint CHECK (level BETWEEN 1 AND 4),
    currency_code     text NOT NULL CHECK (currency_code ~ '^[A-Z]{3}$'),
    basis             text NOT NULL CHECK (basis IN ('per_person', 'total')),
    party_size        smallint CHECK (party_size >= 1),
    source            text NOT NULL,
    confidence        text NOT NULL CHECK (confidence IN ('high', 'medium', 'low')),
    recorded_at       timestamptz NOT NULL DEFAULT now(),
    note              text,
    CHECK ((place_id IS NULL) <> (user_place_id IS NULL)),
    CHECK (amount IS NOT NULL OR level IS NOT NULL),
    CHECK (basis <> 'total' OR party_size IS NOT NULL),
    CHECK (kind = 'provider_level' OR (amount IS NOT NULL AND level IS NULL)),
    CHECK (kind <> 'provider_level' OR (level IS NOT NULL AND amount IS NULL)),
    CHECK (confidence = CASE kind WHEN 'user_actual' THEN 'high'
                                  WHEN 'user_expected' THEN 'medium'
                                  ELSE 'low' END)
);
CREATE INDEX price_record_installation_idx ON app.price_record (installation_id, recorded_at DESC);

-- Past-trip archive (ADR 006): one row per city or attraction of the selected itinerary.
CREATE TABLE app.trip_visit (
    id            uuid PRIMARY KEY,
    trip_id       uuid NOT NULL REFERENCES app.trip (id) ON DELETE CASCADE,
    kind          text NOT NULL CHECK (kind IN ('city', 'attraction')),
    name          text NOT NULL,            -- snapshot
    point         geometry(Point, 4326) NOT NULL,   -- snapshot
    geo_place_ref text,                     -- the geo identifier it came from; may be gone
    day_number    smallint NOT NULL CHECK (day_number >= 1),
    confirmed     boolean NOT NULL DEFAULT true
);
CREATE INDEX trip_visit_trip_idx ON app.trip_visit (trip_id, day_number);
CREATE INDEX trip_visit_point_gix ON app.trip_visit USING gist (point);

-- Cache of answers from external providers and their daily call counters (architecture,
-- section 6). It lives in app, not geo, because it is not rebuilt from an import; it holds search
-- text but never an installation identifier.
CREATE TABLE app.provider_cache (
    cache_key  text PRIMARY KEY,
    provider   text NOT NULL,
    response   jsonb NOT NULL,
    fetched_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL
);
CREATE INDEX provider_cache_expiry_idx ON app.provider_cache (expires_at);

CREATE TABLE app.provider_usage (
    provider   text NOT NULL,
    usage_date date NOT NULL,
    calls      integer NOT NULL DEFAULT 0 CHECK (calls >= 0),
    PRIMARY KEY (provider, usage_date)
);
"""

DOWNGRADE = """
DROP TABLE IF EXISTS app.provider_usage;
DROP TABLE IF EXISTS app.provider_cache;
DROP TABLE IF EXISTS app.trip_visit;
DROP TABLE IF EXISTS app.price_record;
DROP TABLE IF EXISTS app.transfer;
DROP TABLE IF EXISTS app.itinerary_item;
DROP TABLE IF EXISTS app.itinerary_day;
ALTER TABLE app.trip DROP CONSTRAINT IF EXISTS trip_selected_itinerary_fk;
DROP TABLE IF EXISTS app.itinerary;
DROP TABLE IF EXISTS app.trip;
DROP TABLE IF EXISTS app.user_place;
DROP TABLE IF EXISTS app.installation;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
