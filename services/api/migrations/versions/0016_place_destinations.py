"""ADR 027: trips to places outside the imported regions.

``app.trip.destination_kind`` gains ``place``: the destination is a snapshot (name, point, country)
with a provider-prefixed reference (``photon:N123``, ``geonames:2761369``, ``area:<uuid>`` or
``manual``) and needs no ``geo`` row. ``destination_country`` holds the country code when known.

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-14
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE app.trip DROP CONSTRAINT trip_destination_kind_check")
    op.execute(
        "ALTER TABLE app.trip ADD CONSTRAINT trip_destination_kind_check"
        " CHECK (destination_kind IN ('city', 'area', 'route', 'place'))"
    )
    op.execute("ALTER TABLE app.trip ADD COLUMN destination_country text")


def downgrade() -> None:
    op.execute("DELETE FROM app.trip WHERE destination_kind = 'place'")
    op.execute("ALTER TABLE app.trip DROP COLUMN destination_country")
    op.execute("ALTER TABLE app.trip DROP CONSTRAINT trip_destination_kind_check")
    op.execute(
        "ALTER TABLE app.trip ADD CONSTRAINT trip_destination_kind_check"
        " CHECK (destination_kind IN ('city', 'area', 'route'))"
    )
