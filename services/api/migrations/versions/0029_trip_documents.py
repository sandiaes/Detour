"""Shared trip documents (ADR 034, step 6).

A document uploaded to a trip is a file of kind ``document`` in ``app.trip_file`` (the private
``trip-files`` bucket) plus its description here, under the same id: deleting the file row deletes
the description, and the bucket object is removed after the change commits (``trip_file_orphan``).
The phone chooses the id (a UUID), so an upload that is sent twice is stored once. Documents kept
only on a phone never reach this table (ADR 023 still holds for them).

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
CREATE TABLE app.trip_document (
    id          uuid PRIMARY KEY REFERENCES app.trip_file (id) ON DELETE CASCADE,
    trip_id     uuid NOT NULL REFERENCES app.trip (id) ON DELETE CASCADE,
    title       text NOT NULL CHECK (char_length(title) BETWEEN 1 AND 120),
    category    text NOT NULL CHECK (category IN ('ticket', 'booking', 'transport', 'other')),
    link        jsonb NOT NULL,
    doc_date    date,
    notes       text CHECK (char_length(notes) <= 500),
    file_name   text NOT NULL CHECK (char_length(file_name) BETWEEN 1 AND 200),
    updated_by  uuid REFERENCES app.person (id) ON DELETE SET NULL,
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX trip_document_trip_idx ON app.trip_document (trip_id);
COMMENT ON TABLE app.trip_document IS
    'A document shared with everyone on a trip; its file is the trip_file of the same id (ADR 034).';
"""
    )


def downgrade() -> None:
    op.execute(
        """
DELETE FROM app.trip_file WHERE kind = 'document';
DROP TABLE app.trip_document;
"""
    )
