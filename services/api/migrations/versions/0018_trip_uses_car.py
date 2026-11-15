"""A trip says whether the traveller has a car: without one, Optimize only considers walking.

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-15
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE app.trip ADD COLUMN uses_car boolean NOT NULL DEFAULT true")


def downgrade() -> None:
    op.execute("ALTER TABLE app.trip DROP COLUMN uses_car")
