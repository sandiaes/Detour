"""Reference photos (ADR 022): ``geo.image``, ``geo.image_lookup`` and ``app.trip.cover_image_id``.

* ``geo.image``: one Wikimedia Commons file that is stored (resized) in Supabase Storage, with the
  author and licence the attribution needs. Images are independently licensed content, not ODbL
  data, so each row carries its own licence. ``color`` is the average colour, the placeholder shown
  while the photo loads. ``hidden`` removes a wrong photo from every screen.
* ``geo.image_lookup``: what was asked for a place or a city and what came of it, so that a
  negative answer is not asked again at once. ``ref_id`` is the place id (uuid) or the GeoNames id
  as text; it is an identifier, not a foreign key, because the two kinds live in different tables.
* ``app.trip.cover_image_id``: the chosen or automatic cover. No foreign key: it would cross the
  ``app`` and ``geo`` schemas; the API checks the identifier.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-14
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UPGRADE = """
CREATE TABLE geo.image (
    id            uuid PRIMARY KEY,           -- derived from the Commons file name: stable
    source        text NOT NULL CHECK (source IN ('wikimedia_commons')),
    commons_file  text NOT NULL UNIQUE,       -- the file name without the "File:" prefix
    source_url    text NOT NULL CHECK (source_url LIKE 'https://%'),
    wikidata_id   text CHECK (wikidata_id ~ '^Q[0-9]+$'),
    author        text NOT NULL CHECK (char_length(author) BETWEEN 1 AND 300),
    licence       text NOT NULL CHECK (char_length(licence) BETWEEN 1 AND 60),
    licence_url   text CHECK (licence_url LIKE 'https://%' OR licence_url LIKE 'http://%'),
    width         integer NOT NULL CHECK (width > 0),     -- of the stored file
    height        integer NOT NULL CHECK (height > 0),
    bytes         integer NOT NULL CHECK (bytes > 0),
    color         text NOT NULL CHECK (color ~ '^#[0-9a-f]{6}$'),
    storage_key   text NOT NULL,
    fetched_date  date NOT NULL,
    hidden        boolean NOT NULL DEFAULT false
);

CREATE TABLE geo.image_lookup (
    kind          text NOT NULL CHECK (kind IN ('place', 'city')),
    ref_id        text NOT NULL,
    status        text NOT NULL CHECK (status IN ('found', 'none', 'rejected')),
    reason        text,                       -- why none or rejected, in a fixed vocabulary
    image_id      uuid REFERENCES geo.image (id) ON DELETE CASCADE,
    checked_date  date NOT NULL,
    PRIMARY KEY (kind, ref_id),
    CONSTRAINT image_lookup_found_has_image CHECK ((status = 'found') = (image_id IS NOT NULL))
);
CREATE INDEX image_lookup_image_idx ON geo.image_lookup (image_id) WHERE image_id IS NOT NULL;

COMMENT ON TABLE geo.image IS
    'Wikimedia Commons photos stored in Supabase Storage, each with author and licence (ADR 022).';
COMMENT ON TABLE geo.image_lookup IS
    'Result of the last photo lookup for a place or a city; none and rejected are retried after 90 days.';

ALTER TABLE app.trip ADD COLUMN cover_image_id uuid;   -- identifier into geo.image; no foreign key
COMMENT ON COLUMN app.trip.cover_image_id IS
    'The trip cover, chosen by the user or found automatically; no foreign key across schemas.';
"""

DOWNGRADE = """
ALTER TABLE app.trip DROP COLUMN cover_image_id;
DROP TABLE geo.image_lookup;
DROP TABLE geo.image;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
