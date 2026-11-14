"""Multi-city trips: ``app.trip_stop``, the destination kind ``route``, stop versions and legs whose
time is not known (ADR 024).

* ``app.trip_stop``: the cities of a multi-city trip in the user's order, with their days. The city
  is a GeoNames id with a snapshot of its name, country and point; no foreign key crosses into
  ``geo`` (the schemas stay separate).
* ``app.trip.destination_kind`` gains ``route``; ``app.trip.stops_version`` counts applied stop
  edits, and ``app.itinerary.stops_version`` records the version a plan was made for (null for city
  and area trips).
* ``app.itinerary_day``: an arrival leg may be ``unknown`` (mode and confidence) with no seconds or
  metres, for legs into or out of a rail-dominant country, where no travel time is invented (rule
  5; public transport is Phase 10).

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-14
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE app.trip DROP CONSTRAINT trip_destination_kind_check")
    op.execute(
        "ALTER TABLE app.trip ADD CONSTRAINT trip_destination_kind_check"
        " CHECK (destination_kind IN ('city', 'area', 'route'))"
    )
    op.execute("ALTER TABLE app.change_set DROP CONSTRAINT change_set_action_check")
    op.execute(
        "ALTER TABLE app.change_set ADD CONSTRAINT change_set_action_check"
        " CHECK (action IN ('add_place', 'remove_place', 'add_restaurant', 'edit_stops'))"
    )
    # A stop edit names no place (its target is the trip's new name).
    op.execute("ALTER TABLE app.change_set DROP CONSTRAINT change_set_place_xor")
    op.execute(
        "ALTER TABLE app.change_set ADD CONSTRAINT change_set_place_xor CHECK (action IN"
        " ('remove_place', 'edit_stops') OR ((place_id IS NULL) <> (user_place_id IS NULL)))"
    )
    op.execute("ALTER TABLE app.trip ADD COLUMN stops_version integer NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE app.itinerary ADD COLUMN stops_version integer")
    op.execute(
        """
        CREATE TABLE app.trip_stop (
            id            uuid PRIMARY KEY,
            trip_id       uuid NOT NULL REFERENCES app.trip (id) ON DELETE CASCADE,
            position      smallint NOT NULL CHECK (position BETWEEN 1 AND 6),
            city_id       bigint NOT NULL,  -- geo.city.id, checked by the API; no foreign key
            city_name     text NOT NULL CHECK (char_length(city_name) BETWEEN 1 AND 200),
            country_iso2  text CHECK (country_iso2 ~ '^[A-Z]{2}$'),
            point         geometry(Point, 4326) NOT NULL,
            days          smallint NOT NULL CHECK (days BETWEEN 1 AND 30),
            UNIQUE (trip_id, position)
        )
        """
    )
    op.execute("CREATE INDEX trip_stop_trip ON app.trip_stop (trip_id)")
    op.execute("CREATE INDEX trip_stop_point ON app.trip_stop USING gist (point)")
    for name, values in (
        ("arrival_mode", "'walk', 'drive', 'unknown'"),
        ("arrival_confidence", "'routed', 'estimated', 'unknown'"),
    ):
        op.execute(f"ALTER TABLE app.itinerary_day DROP CONSTRAINT itinerary_day_{name}_check")
        op.execute(
            f"ALTER TABLE app.itinerary_day ADD CONSTRAINT itinerary_day_{name}_check"
            f" CHECK ({name} IN ({values}))"
        )
    op.execute("ALTER TABLE app.itinerary_day DROP CONSTRAINT itinerary_day_arrival_complete")
    op.execute(
        """
        ALTER TABLE app.itinerary_day ADD CONSTRAINT itinerary_day_arrival_complete CHECK (
            (arrival_mode IS NULL) = (arrival_confidence IS NULL)
            AND (arrival_mode = 'unknown') = (arrival_confidence = 'unknown')
            -- a time and a distance exactly when the leg is known
            AND (arrival_mode IS NOT NULL AND arrival_mode <> 'unknown')
                = (arrival_seconds IS NOT NULL)
            AND (arrival_seconds IS NULL) = (arrival_meters IS NULL))
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM app.change_set WHERE action = 'edit_stops'")
    op.execute("ALTER TABLE app.change_set DROP CONSTRAINT change_set_place_xor")
    op.execute(
        "ALTER TABLE app.change_set ADD CONSTRAINT change_set_place_xor"
        " CHECK (action = 'remove_place' OR ((place_id IS NULL) <> (user_place_id IS NULL)))"
    )
    op.execute("ALTER TABLE app.change_set DROP CONSTRAINT change_set_action_check")
    op.execute(
        "ALTER TABLE app.change_set ADD CONSTRAINT change_set_action_check"
        " CHECK (action IN ('add_place', 'remove_place', 'add_restaurant'))"
    )
    op.execute("DELETE FROM app.trip WHERE destination_kind = 'route'")
    op.execute(
        "UPDATE app.itinerary_day SET arrival_mode = NULL, arrival_confidence = NULL"
        " WHERE arrival_mode = 'unknown'"
    )
    op.execute("ALTER TABLE app.itinerary_day DROP CONSTRAINT itinerary_day_arrival_complete")
    op.execute(
        """
        ALTER TABLE app.itinerary_day ADD CONSTRAINT itinerary_day_arrival_complete CHECK (
            (arrival_mode IS NULL) = (arrival_seconds IS NULL)
            AND (arrival_mode IS NULL) = (arrival_meters IS NULL)
            AND (arrival_mode IS NULL) = (arrival_confidence IS NULL))
        """
    )
    for name, values in (
        ("arrival_mode", "'walk', 'drive'"),
        ("arrival_confidence", "'routed', 'estimated'"),
    ):
        op.execute(f"ALTER TABLE app.itinerary_day DROP CONSTRAINT itinerary_day_{name}_check")
        op.execute(
            f"ALTER TABLE app.itinerary_day ADD CONSTRAINT itinerary_day_{name}_check"
            f" CHECK ({name} IN ({values}))"
        )
    op.execute("DROP TABLE app.trip_stop")
    op.execute("ALTER TABLE app.itinerary DROP COLUMN stops_version")
    op.execute("ALTER TABLE app.trip DROP COLUMN stops_version")
    op.execute("ALTER TABLE app.trip DROP CONSTRAINT trip_destination_kind_check")
    op.execute(
        "ALTER TABLE app.trip ADD CONSTRAINT trip_destination_kind_check"
        " CHECK (destination_kind IN ('city', 'area'))"
    )
