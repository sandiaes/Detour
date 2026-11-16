"""Album links and trip files on the server (ADR 034, step 5).

* ``app.trip_album``: links to the travellers' own photo albums (ADR 031), now shared by everyone on
  the trip instead of kept on one phone. Detour never reads the album; the link opens it.
* ``app.trip_file``: a file of a trip kept in the private Storage bucket ``trip-files`` and served
  only through the API to the trip's members. Kind ``cover`` (a picture chosen from a phone, at most
  one per trip) now; kind ``document`` comes with step 6. The bytes are stored once, under
  ``storage_key``; the row is what the API lists and what the storage budget counts.

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
CREATE TABLE app.trip_album (
    id          uuid PRIMARY KEY,
    trip_id     uuid NOT NULL REFERENCES app.trip (id) ON DELETE CASCADE,
    url         text NOT NULL CHECK (url LIKE 'https://%' AND char_length(url) <= 2000),
    name        text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 80),
    added_by    uuid REFERENCES app.person (id) ON DELETE SET NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (trip_id, url)
);
CREATE INDEX trip_album_trip_idx ON app.trip_album (trip_id, created_at);
COMMENT ON TABLE app.trip_album IS
    'Links to the travellers'' own photo albums, opened in their app, never read (ADR 031, 034).';

CREATE TABLE app.trip_file (
    id            uuid PRIMARY KEY,
    trip_id       uuid NOT NULL REFERENCES app.trip (id) ON DELETE CASCADE,
    kind          text NOT NULL CHECK (kind IN ('cover', 'document')),
    storage_key   text NOT NULL UNIQUE,
    content_type  text NOT NULL,
    bytes         integer NOT NULL CHECK (bytes > 0),
    sha256        bytea NOT NULL,
    uploaded_by   uuid REFERENCES app.person (id) ON DELETE SET NULL,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX trip_file_one_cover ON app.trip_file (trip_id) WHERE kind = 'cover';
CREATE INDEX trip_file_trip_idx ON app.trip_file (trip_id, kind);
COMMENT ON TABLE app.trip_file IS
    'A trip''s file in the private trip-files bucket, served only to its members (ADR 034).';

-- Objects of deleted trips or replaced covers, to remove from the bucket after the change
-- commits (a row cascades away with its trip; its object must not stay behind).
CREATE TABLE app.trip_file_orphan (
    storage_key  text PRIMARY KEY,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE FUNCTION app.trip_file_orphaned() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO app.trip_file_orphan (storage_key) VALUES (OLD.storage_key)
    ON CONFLICT DO NOTHING;
    RETURN OLD;
END
$$;
CREATE TRIGGER trip_file_orphaned AFTER DELETE ON app.trip_file
    FOR EACH ROW EXECUTE FUNCTION app.trip_file_orphaned();
"""
    )


def downgrade() -> None:
    op.execute(
        """
DROP TRIGGER trip_file_orphaned ON app.trip_file;
DROP FUNCTION app.trip_file_orphaned();
DROP TABLE app.trip_file_orphan;
DROP TABLE app.trip_file;
DROP TABLE app.trip_album;
"""
    )
