"""Phase 8 (ADR 019): change sets can add a restaurant to a meal slot.

* ``app.change_set.action`` also allows ``add_restaurant`` (an imported place to eat by
  ``place_id``, or a restaurant of the user's by ``user_place_id``), with the slot it was
  previewed for: ``slot_day``, ``slot_meal`` and ``after_item_id`` (the visit or fixed meal the
  new meal follows; null: first of the day).
* No other table changes: the meal is an ``app.itinerary_item`` of type ``meal`` with origin
  ``user``, written by the same change-set apply as every other change.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UPGRADE = """
ALTER TABLE app.change_set DROP CONSTRAINT change_set_action_check;
ALTER TABLE app.change_set ADD CONSTRAINT change_set_action_check
    CHECK (action IN ('add_place', 'remove_place', 'add_restaurant'));

ALTER TABLE app.change_set DROP CONSTRAINT change_set_check4;
ALTER TABLE app.change_set ADD CONSTRAINT change_set_place_xor
    CHECK (action = 'remove_place' OR ((place_id IS NULL) <> (user_place_id IS NULL)));

ALTER TABLE app.change_set
    ADD COLUMN slot_day      smallint CHECK (slot_day >= 1),
    ADD COLUMN slot_meal     text CHECK (slot_meal IN ('breakfast', 'lunch', 'snack', 'dinner')),
    ADD COLUMN after_item_id uuid,          -- the item the new meal follows; null: first of the day
    ADD CONSTRAINT change_set_slot CHECK (
        (action = 'add_restaurant') = (slot_day IS NOT NULL AND slot_meal IS NOT NULL)
        AND (action = 'add_restaurant' OR after_item_id IS NULL)
    );
"""

DOWNGRADE = """
DELETE FROM app.change_set WHERE action = 'add_restaurant';
ALTER TABLE app.change_set
    DROP CONSTRAINT change_set_slot,
    DROP COLUMN after_item_id,
    DROP COLUMN slot_meal,
    DROP COLUMN slot_day;
ALTER TABLE app.change_set DROP CONSTRAINT change_set_place_xor;
ALTER TABLE app.change_set ADD CONSTRAINT change_set_check4
    CHECK (action <> 'add_place' OR ((place_id IS NULL) <> (user_place_id IS NULL)));
ALTER TABLE app.change_set DROP CONSTRAINT change_set_action_check;
ALTER TABLE app.change_set ADD CONSTRAINT change_set_action_check
    CHECK (action IN ('add_place', 'remove_place'));
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
