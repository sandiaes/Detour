"""Past trips are read-only and can be reopened (ADR 006, amendment of 2026-11-17).

``app.trip.reopened_at`` marks a trip the user took out of the past on purpose, so that the
two-day rule does not make it past again the next time the trips are read.

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE app.trip ADD COLUMN reopened_at timestamptz")


def downgrade() -> None:
    op.execute("ALTER TABLE app.trip DROP COLUMN reopened_at")
