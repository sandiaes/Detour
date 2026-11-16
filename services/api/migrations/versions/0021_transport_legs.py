"""Manual transport legs: an itinerary item of type ``transport`` (ADR 032).

A leg is entered by the user: mode, from and to (names with optional points), an optional start
and an optional length, a journey flag and a note, kept in ``transport`` (jsonb, validated by the
API). It has no place. Its length may be unknown (``duration_minutes`` null), and it may have a
start without an end: a length not entered, or a night train that arrives the next day.

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
ALTER TABLE app.itinerary_item ADD COLUMN transport jsonb;
ALTER TABLE app.itinerary_item DROP CONSTRAINT itinerary_item_type_check;
ALTER TABLE app.itinerary_item ADD CONSTRAINT itinerary_item_type_check
    CHECK (type IN ('visit', 'meal', 'free_time', 'transport'));
ALTER TABLE app.itinerary_item ADD CONSTRAINT item_transport
    CHECK ((type = 'transport') = (transport IS NOT NULL));
ALTER TABLE app.itinerary_item DROP CONSTRAINT item_place_xor;
ALTER TABLE app.itinerary_item ADD CONSTRAINT item_place_xor CHECK (
    CASE WHEN type IN ('free_time', 'transport')
         THEN place_id IS NULL AND user_place_id IS NULL
         ELSE (place_id IS NULL) <> (user_place_id IS NULL)
    END);
ALTER TABLE app.itinerary_item ALTER COLUMN duration_minutes DROP NOT NULL;
ALTER TABLE app.itinerary_item ADD CONSTRAINT item_duration_known
    CHECK (duration_minutes IS NOT NULL OR type = 'transport');
ALTER TABLE app.itinerary_item DROP CONSTRAINT item_times;
ALTER TABLE app.itinerary_item ADD CONSTRAINT item_times CHECK (
    (start_time IS NULL AND end_time IS NULL)
    OR (start_time IS NOT NULL AND end_time IS NOT NULL AND end_time > start_time)
    OR (type = 'transport' AND start_time IS NOT NULL AND end_time IS NULL));
"""
    )


def downgrade() -> None:
    op.execute(
        """
DELETE FROM app.itinerary_item WHERE type = 'transport';
ALTER TABLE app.itinerary_item DROP CONSTRAINT item_times;
ALTER TABLE app.itinerary_item ADD CONSTRAINT item_times CHECK (
    (start_time IS NULL) = (end_time IS NULL)
    AND (start_time IS NULL OR end_time > start_time));
ALTER TABLE app.itinerary_item DROP CONSTRAINT item_duration_known;
ALTER TABLE app.itinerary_item ALTER COLUMN duration_minutes SET NOT NULL;
ALTER TABLE app.itinerary_item DROP CONSTRAINT item_place_xor;
ALTER TABLE app.itinerary_item ADD CONSTRAINT item_place_xor CHECK (
    CASE WHEN type = 'free_time'
         THEN place_id IS NULL AND user_place_id IS NULL
         ELSE (place_id IS NULL) <> (user_place_id IS NULL)
    END);
ALTER TABLE app.itinerary_item DROP CONSTRAINT item_transport;
ALTER TABLE app.itinerary_item DROP CONSTRAINT itinerary_item_type_check;
ALTER TABLE app.itinerary_item ADD CONSTRAINT itinerary_item_type_check
    CHECK (type IN ('visit', 'meal', 'free_time'));
ALTER TABLE app.itinerary_item DROP COLUMN transport;
"""
    )
