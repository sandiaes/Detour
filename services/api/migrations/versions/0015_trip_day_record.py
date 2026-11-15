"""ADR 026, history step: a past trip keeps its day-by-day record.

``app.trip_visit`` already holds one snapshot row per city and attraction. It now also holds the
restaurants and cafes of the plan and, for every stop, its order within the day, start time and
length, so a past trip can show what was done on which day. ``confirmed`` is the visited flag
(archiving sets it, the user can clear it). Rows archived before this migration keep their map
data and have no time or order (they cannot be reconstructed: their plans are gone).

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-14
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UPGRADE = """
ALTER TABLE app.trip_visit DROP CONSTRAINT trip_visit_kind_check;
ALTER TABLE app.trip_visit ADD CONSTRAINT trip_visit_kind_check
    CHECK (kind IN ('city', 'attraction', 'restaurant', 'cafe'));
ALTER TABLE app.trip_visit
    ADD COLUMN position         smallint CHECK (position >= 1),
    ADD COLUMN start_time       time,
    ADD COLUMN duration_minutes integer CHECK (duration_minutes > 0);
"""

DOWNGRADE = """
DELETE FROM app.trip_visit WHERE kind IN ('restaurant', 'cafe');
ALTER TABLE app.trip_visit
    DROP COLUMN position, DROP COLUMN start_time, DROP COLUMN duration_minutes;
ALTER TABLE app.trip_visit DROP CONSTRAINT trip_visit_kind_check;
ALTER TABLE app.trip_visit ADD CONSTRAINT trip_visit_kind_check
    CHECK (kind IN ('city', 'attraction'));
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
