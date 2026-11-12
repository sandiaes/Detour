"""Rebuild ``geo.travel_time`` as the Phase 3 travel-time cache (ADR 013).

The Phase 2 table was keyed by two text references and an ``engine_version`` and was never written
(nothing used it). The cache needs, per ADR 004, the provider, the response date and the request
shape, and it must be compact because every ``geo`` table counts toward gate 6 of ADR 009. So:

* a cell is identified by its two end points, as integers of 1e-5 degree (about 1.1 m), not by a
  place identifier: a place that moves in a later import cannot keep a stale time;
* ``request_shape`` is part of the key, so a change of request shape never mixes with old rows;
* a row is either ``routed`` (a time from the provider) or ``estimated``. An estimated row records
  only that the provider had **no route** for the cell; it stores no number, because the estimate
  is recomputed on every read from the current rules. It expires (``retry_after``).

The migration refuses to run if the old table holds rows, so it can never discard real data.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UPGRADE = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM geo.travel_time) THEN
        RAISE EXCEPTION 'geo.travel_time holds rows; refusing to rebuild it (ADR 013)';
    END IF;
END $$;

DROP TABLE geo.travel_time;

CREATE TABLE geo.travel_time (
    from_lat       integer NOT NULL CHECK (from_lat BETWEEN -9000000 AND 9000000),
    from_lon       integer NOT NULL CHECK (from_lon BETWEEN -18000000 AND 18000000),
    to_lat         integer NOT NULL CHECK (to_lat BETWEEN -9000000 AND 9000000),
    to_lon         integer NOT NULL CHECK (to_lon BETWEEN -18000000 AND 18000000),
    mode           text NOT NULL CHECK (mode IN ('walk', 'drive')),
    request_shape  text NOT NULL,
    provider       text NOT NULL,
    confidence     text NOT NULL CHECK (confidence IN ('routed', 'estimated')),
    seconds        integer CHECK (seconds >= 0),
    meters         integer CHECK (meters >= 0),
    algorithm      text,
    response_date  timestamptz NOT NULL,
    retry_after    timestamptz,
    PRIMARY KEY (from_lat, from_lon, to_lat, to_lon, mode, request_shape),
    CONSTRAINT travel_time_routed_has_numbers CHECK (
        (confidence = 'routed' AND seconds IS NOT NULL AND meters IS NOT NULL AND retry_after IS NULL)
        OR (confidence = 'estimated' AND seconds IS NULL AND meters IS NULL AND retry_after IS NOT NULL)
    )
);

COMMENT ON TABLE geo.travel_time IS
    'FOSSGIS Valhalla travel-time cache (ADR 004, ADR 013). Capped in rows; counts toward ADR 009 gate 6.';
COMMENT ON COLUMN geo.travel_time.algorithm IS
    'The matrix algorithm the provider named in its response; null for route requests.';
"""

DOWNGRADE = """
DROP TABLE IF EXISTS geo.travel_time;

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
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
