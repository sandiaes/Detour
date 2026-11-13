"""Phase 6 (ADR 016) and the removal of budgets, currencies and prices (ADR 017).

ADR 017 (owner decision, 2026-11-13): the app has no currencies, meal budgets, price bands or
prices for now. So:

* ``app.trip`` loses ``currency_code``, ``meal_budget_per_person`` and ``price_band_thresholds``,
  and ``app.installation`` loses ``home_currency_code``. Their values are discarded (the owner
  asked for this); a downgrade restores the columns, not the values.
* ``app.price_record`` (never written: its endpoints were Phase 8) and ``geo.fx_rate`` (never
  filled) are dropped. The migration refuses to run if either holds rows, so it cannot discard a
  recorded price.

ADR 016 (meals and area destinations):

* ``app.itinerary_item.meal_type`` also allows ``snack`` (an afternoon café stop).
* ``app.itinerary_day`` gains ``base_city_name`` (a snapshot, like an item's display name) and the
  inter-city leg that starts the first day at a new base city: ``arrival_mode``,
  ``arrival_seconds``, ``arrival_meters`` and ``arrival_confidence``, all null or all set.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UPGRADE = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM app.price_record) THEN
        RAISE EXCEPTION 'app.price_record holds rows; refusing to drop it (ADR 017)';
    END IF;
    IF EXISTS (SELECT 1 FROM geo.fx_rate) THEN
        RAISE EXCEPTION 'geo.fx_rate holds rows; refusing to drop it (ADR 017)';
    END IF;
END $$;

DROP TABLE app.price_record;
DROP TABLE geo.fx_rate;
ALTER TABLE app.trip
    DROP COLUMN currency_code,
    DROP COLUMN meal_budget_per_person,
    DROP COLUMN price_band_thresholds;
ALTER TABLE app.installation DROP COLUMN home_currency_code;

ALTER TABLE app.itinerary_item DROP CONSTRAINT itinerary_item_meal_type_check;
ALTER TABLE app.itinerary_item ADD CONSTRAINT itinerary_item_meal_type_check
    CHECK (meal_type IN ('breakfast', 'lunch', 'dinner', 'snack'));

ALTER TABLE app.itinerary_day
    ADD COLUMN base_city_name     text,
    ADD COLUMN arrival_mode       text CHECK (arrival_mode IN ('walk', 'drive')),
    ADD COLUMN arrival_seconds    integer CHECK (arrival_seconds >= 0),
    ADD COLUMN arrival_meters     integer CHECK (arrival_meters >= 0),
    ADD COLUMN arrival_confidence text CHECK (arrival_confidence IN ('routed', 'estimated')),
    ADD CONSTRAINT itinerary_day_arrival_complete CHECK (
        (arrival_mode IS NULL) = (arrival_seconds IS NULL)
        AND (arrival_mode IS NULL) = (arrival_meters IS NULL)
        AND (arrival_mode IS NULL) = (arrival_confidence IS NULL));
"""

DOWNGRADE = """
ALTER TABLE app.itinerary_day
    DROP CONSTRAINT itinerary_day_arrival_complete,
    DROP COLUMN arrival_confidence,
    DROP COLUMN arrival_meters,
    DROP COLUMN arrival_seconds,
    DROP COLUMN arrival_mode,
    DROP COLUMN base_city_name;

DELETE FROM app.itinerary_item WHERE meal_type = 'snack';
ALTER TABLE app.itinerary_item DROP CONSTRAINT itinerary_item_meal_type_check;
ALTER TABLE app.itinerary_item ADD CONSTRAINT itinerary_item_meal_type_check
    CHECK (meal_type IN ('breakfast', 'lunch', 'dinner'));

ALTER TABLE app.installation
    ADD COLUMN home_currency_code text CHECK (home_currency_code ~ '^[A-Z]{3}$');
-- The values are gone: 'XXX' is the ISO 4217 code for "no currency".
ALTER TABLE app.trip
    ADD COLUMN currency_code text NOT NULL DEFAULT 'XXX' CHECK (currency_code ~ '^[A-Z]{3}$'),
    ADD COLUMN meal_budget_per_person numeric(12, 2) CHECK (meal_budget_per_person >= 0),
    ADD COLUMN price_band_thresholds jsonb;
ALTER TABLE app.trip ALTER COLUMN currency_code DROP DEFAULT;

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

CREATE TABLE app.price_record (
    id                uuid PRIMARY KEY,
    installation_id   uuid NOT NULL REFERENCES app.installation (id) ON DELETE CASCADE,
    place_id          uuid,
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
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
