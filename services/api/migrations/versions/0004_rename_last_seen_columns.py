"""Rename ``last_seen_import_run_id`` to ``last_changed_import_run_id``.

The importer no longer rewrites rows that did not change (it skips them, which keeps the database
from doubling in size on every re-import), so the column no longer records the last run that saw
a row, only the last run that wrote it. Missing rows are found by comparing with the new extract.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE geo.place RENAME COLUMN last_seen_import_run_id TO last_changed_import_run_id"
    )
    op.execute(
        "ALTER TABLE geo.admin_area"
        " RENAME COLUMN last_seen_import_run_id TO last_changed_import_run_id"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE geo.place RENAME COLUMN last_changed_import_run_id TO last_seen_import_run_id"
    )
    op.execute(
        "ALTER TABLE geo.admin_area"
        " RENAME COLUMN last_changed_import_run_id TO last_seen_import_run_id"
    )
