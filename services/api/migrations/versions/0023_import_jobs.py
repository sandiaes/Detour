"""Import jobs: an import started from the app (ADR 033, step 3).

``geo.import_job`` records one request to import a region: who asked (an identifier, no foreign
key across schemas), when, and how the GitHub workflow that does the import got on. The workflow
updates it (``python -m detour_api.importer job``); the API reads it for the app.

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
CREATE TABLE geo.import_job (
    id            uuid PRIMARY KEY,
    region_id     text NOT NULL,
    status        text NOT NULL DEFAULT 'requested'
                  CHECK (status IN ('requested', 'running', 'succeeded', 'failed')),
    message       text CHECK (char_length(message) <= 500),
    run_url       text CHECK (run_url LIKE 'https://%'),
    requested_by  uuid,
    requested_at  timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX import_job_region_idx ON geo.import_job (region_id, requested_at DESC);
COMMENT ON TABLE geo.import_job IS
    'A region import started from the app and its progress, reported by the workflow (ADR 033).';
"""
    )


def downgrade() -> None:
    op.execute("DROP TABLE geo.import_job")
