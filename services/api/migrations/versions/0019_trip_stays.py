"""Where the traveller sleeps: stays of a trip, each for a range of days (ADR 030).

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-15
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE app.trip_stay (
            id uuid PRIMARY KEY,
            trip_id uuid NOT NULL REFERENCES app.trip (id) ON DELETE CASCADE,
            name text NOT NULL CHECK (length(name) BETWEEN 1 AND 200),
            lat double precision NOT NULL CHECK (lat BETWEEN -90 AND 90),
            lon double precision NOT NULL CHECK (lon BETWEEN -180 AND 180),
            first_day integer NOT NULL CHECK (first_day >= 1),
            last_day integer NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CHECK (last_day >= first_day)
        )
        """
    )
    op.execute("CREATE INDEX trip_stay_trip_idx ON app.trip_stay (trip_id, first_day)")


def downgrade() -> None:
    op.execute("DROP TABLE app.trip_stay")
