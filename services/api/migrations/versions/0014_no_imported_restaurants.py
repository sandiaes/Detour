"""ADR 026, data step: restaurants and cafes leave the imported data; no cuisine or meal types.

Restaurants and cafes are added by the user (through Photon or by hand) and live in
``app.user_place``. This migration:

* turns every itinerary stop that points at an imported restaurant into a place of the same
  installation (``app.user_place``, kind ``restaurant`` or ``cafe``, name and point from the
  imported place), so no stored plan loses a stop or its times;
* deletes the imported restaurants and cafes and everything in ``geo`` that hangs on them
  (profile, source rows, signal, names, name lookups, photo lookups);
* drops ``geo.restaurant_profile`` and narrows ``geo.place.kind``;
* ``app.user_place``: new kind ``cafe``; the ``cuisines`` and ``meal_types`` columns are dropped;
* ``app.itinerary_item.meal_type`` is dropped (a stop of type ``meal`` is a restaurant or cafe stop);
* ``app.change_set``: ``add_restaurant`` rows are deleted, the action is no longer allowed, and
  the slot columns ``slot_meal`` and ``after_item_id`` are dropped (``slot_day`` stays: the one
  day an add-place preview was restricted to).

The downgrade restores the structure only: the deleted data comes back by importing the region
again with the earlier importer.

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-14
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UPGRADE = """
ALTER TABLE app.user_place DROP CONSTRAINT user_place_kind_check;
ALTER TABLE app.user_place ADD CONSTRAINT user_place_kind_check
    CHECK (kind IN ('city', 'location', 'restaurant', 'cafe'));

-- Stops on imported restaurants become the installation's own places.
CREATE TEMP TABLE moved_restaurant ON COMMIT DROP AS
SELECT gen_random_uuid() AS user_place_id, t.installation_id, p.id AS place_id,
       CASE WHEN p.category = 'cafe' THEN 'cafe' ELSE 'restaurant' END AS kind,
       left(COALESCE(min(i.display_name), p.name, 'Restaurant'), 200) AS name,
       p.geom AS geom
FROM app.itinerary_item i
JOIN app.itinerary_day d ON d.id = i.day_id
JOIN app.itinerary it ON it.id = d.itinerary_id
JOIN app.trip t ON t.id = it.trip_id
JOIN geo.place p ON p.id = i.place_id
WHERE p.kind = 'restaurant'
GROUP BY t.installation_id, p.id, p.category, p.name, p.geom;

INSERT INTO app.user_place (id, installation_id, kind, name, geom, source)
SELECT user_place_id, installation_id, kind, name, geom, 'manual_pin' FROM moved_restaurant;

UPDATE app.itinerary_item i
SET user_place_id = m.user_place_id, place_id = NULL
FROM moved_restaurant m, app.itinerary_day d, app.itinerary it, app.trip t
WHERE i.place_id = m.place_id AND d.id = i.day_id AND it.id = d.itinerary_id
  AND t.id = it.trip_id AND t.installation_id = m.installation_id;

-- Change sets that add a restaurant, and the slot columns.
DELETE FROM app.change_set WHERE action = 'add_restaurant';
ALTER TABLE app.change_set DROP CONSTRAINT change_set_slot;
ALTER TABLE app.change_set DROP COLUMN slot_meal, DROP COLUMN after_item_id;
ALTER TABLE app.change_set DROP CONSTRAINT change_set_action_check;
ALTER TABLE app.change_set ADD CONSTRAINT change_set_action_check
    CHECK (action IN ('add_place', 'remove_place', 'edit_stops'));

-- Cuisine, meal types and the meal type of a stop.
ALTER TABLE app.user_place DROP COLUMN cuisines, DROP COLUMN meal_types;
ALTER TABLE app.itinerary_item DROP COLUMN meal_type;

-- The imported restaurants and what hangs on them.
DELETE FROM geo.place_name WHERE entity_kind = 'place'
    AND entity_ref IN (SELECT id::text FROM geo.place WHERE kind = 'restaurant');
DELETE FROM geo.place_name_lookup WHERE entity_kind = 'place'
    AND entity_ref IN (SELECT id::text FROM geo.place WHERE kind = 'restaurant');
DELETE FROM geo.image_lookup WHERE kind = 'place'
    AND ref_id IN (SELECT id::text FROM geo.place WHERE kind = 'restaurant');
DELETE FROM app.place_name_override WHERE entity_kind = 'place'
    AND entity_ref IN (SELECT id::text FROM geo.place WHERE kind = 'restaurant');
DELETE FROM geo.place WHERE kind = 'restaurant';   -- profile, sources and signal cascade
DROP TABLE geo.restaurant_profile;
ALTER TABLE geo.place DROP CONSTRAINT place_kind_check;
ALTER TABLE geo.place ADD CONSTRAINT place_kind_check
    CHECK (kind IN ('attraction', 'transport_hub', 'other'));
"""

DOWNGRADE = """
ALTER TABLE geo.place DROP CONSTRAINT place_kind_check;
ALTER TABLE geo.place ADD CONSTRAINT place_kind_check
    CHECK (kind IN ('attraction', 'restaurant', 'transport_hub', 'other'));
CREATE TABLE geo.restaurant_profile (
    place_id              uuid PRIMARY KEY REFERENCES geo.place (id) ON DELETE CASCADE,
    cuisines              text[],
    venue_type            text NOT NULL
                          CHECK (venue_type IN ('restaurant', 'cafe', 'fast_food', 'bar', 'pub',
                                                'food_court', 'other')),
    meal_types            text[],
    diet_flags            text[],
    provider_price_level  smallint CHECK (provider_price_level BETWEEN 1 AND 4),
    provider_price_source text,
    CHECK ((provider_price_level IS NULL) = (provider_price_source IS NULL))
);

ALTER TABLE app.itinerary_item ADD COLUMN meal_type text
    CHECK (meal_type IN ('breakfast', 'lunch', 'dinner', 'snack'));
UPDATE app.itinerary_item SET meal_type = 'lunch' WHERE type = 'meal';
ALTER TABLE app.itinerary_item ADD CONSTRAINT item_meal_type
    CHECK ((type = 'meal') = (meal_type IS NOT NULL));

ALTER TABLE app.user_place ADD COLUMN cuisines text[], ADD COLUMN meal_types text[];
UPDATE app.user_place SET kind = 'restaurant' WHERE kind = 'cafe';
ALTER TABLE app.user_place ADD CONSTRAINT user_place_cuisine_kind
    CHECK (kind = 'restaurant' OR (cuisines IS NULL AND meal_types IS NULL));
ALTER TABLE app.user_place DROP CONSTRAINT user_place_kind_check;
ALTER TABLE app.user_place ADD CONSTRAINT user_place_kind_check
    CHECK (kind IN ('city', 'location', 'restaurant'));

ALTER TABLE app.change_set DROP CONSTRAINT change_set_action_check;
ALTER TABLE app.change_set ADD CONSTRAINT change_set_action_check
    CHECK (action IN ('add_place', 'remove_place', 'add_restaurant', 'edit_stops'));
ALTER TABLE app.change_set
    ADD COLUMN slot_meal text CHECK (slot_meal IN ('breakfast', 'lunch', 'snack', 'dinner')),
    ADD COLUMN after_item_id uuid,
    ADD CONSTRAINT change_set_slot CHECK (
        (action = 'add_restaurant') = (slot_day IS NOT NULL AND slot_meal IS NOT NULL)
        AND (action = 'add_restaurant' OR after_item_id IS NULL)
    );
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
