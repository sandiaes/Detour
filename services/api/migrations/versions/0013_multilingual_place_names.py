"""Multilingual place names (ADR 025): ``geo.place_name``, ``geo.place_name_lookup``,
``app.place_name_override`` and ``geo.place.alias_norm``.

* ``geo.place_name``: names fetched for a place, a city or an area from Wikidata (labels, aliases,
  the English Wikipedia sitelink title), one row per (entity, language, source, normalised value).
  Only these strings and identifiers are stored, never a provider's answer. Rows expire unless
  something in ``app`` still names the entity. The names OpenStreetMap and GeoNames give stay where
  the import puts them (``geo.place.names_i18n``, ``geo.place_source.tags``, ``geo.city``): they are
  read from there, not copied.
* ``geo.place_name_lookup``: what was asked of Wikidata for an entity and when, including "no
  English name" (the negative cache), so the same question is not asked again for 90 days.
* ``app.place_name_override``: the display name a user approved for one place. User data, per
  installation, keyed by the entity's identifier, so similarly named places are not affected;
  deleting the row restores the resolved name. The original name is kept.
* ``geo.place.alias_norm``: the normalised search aliases OpenStreetMap gives (other languages,
  romanizations, ``int_name``, official and short names, ASCII spellings such as ``moenchsberg``),
  ``|``-joined; filled here for the places already imported, kept current by later imports.

No foreign key crosses the schemas: ``entity_ref`` is an identifier as text.

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from detour_api.names.search import place_alias_norm

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UPGRADE = """
CREATE TABLE geo.place_name (
    entity_kind   text NOT NULL CHECK (entity_kind IN ('place', 'city', 'area')),
    entity_ref    text NOT NULL CHECK (char_length(entity_ref) BETWEEN 1 AND 64),
    lang          text NOT NULL CHECK (lang ~ '^[A-Za-z]{2,8}(-[A-Za-z0-9]{1,8})*$'),
    script        text CHECK (script ~ '^[A-Z][a-z]{3}$'),
    name          text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 300),
    name_norm     text NOT NULL CHECK (char_length(name_norm) BETWEEN 1 AND 300),
    name_type     text NOT NULL CHECK (name_type IN ('original', 'official_english',
                    'established_english', 'localized_brand', 'official_romanization',
                    'automatic_transliteration', 'machine_translation', 'search_alias')),
    source        text NOT NULL CHECK (source IN ('wikidata', 'enwiki', 'provider')),
    step          text,                        -- the hierarchy step it can fill; null: alias only
    source_ref    text CHECK (char_length(source_ref) <= 330),
    licence_code  text NOT NULL REFERENCES geo.licence (code),
    confidence    numeric(3, 2) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    official      boolean NOT NULL DEFAULT false,
    is_preferred  boolean NOT NULL DEFAULT false,
    retrieved_at  timestamptz NOT NULL,
    expires_at    timestamptz,
    PRIMARY KEY (entity_kind, entity_ref, lang, source, name_norm)
);
CREATE INDEX place_name_norm_trgm ON geo.place_name USING gin (name_norm gin_trgm_ops);
CREATE INDEX place_name_expires ON geo.place_name (expires_at) WHERE expires_at IS NOT NULL;
COMMENT ON TABLE geo.place_name IS
    'Names fetched from Wikidata for places, cities and areas (ADR 025); no provider payloads.';

CREATE TABLE geo.place_name_lookup (
    entity_kind   text NOT NULL CHECK (entity_kind IN ('place', 'city', 'area')),
    entity_ref    text NOT NULL CHECK (char_length(entity_ref) BETWEEN 1 AND 64),
    source        text NOT NULL CHECK (source IN ('wikidata')),
    qid           text CHECK (qid ~ '^Q[0-9]+$'),
    status        text NOT NULL CHECK (status IN ('found', 'no_english', 'no_item')),
    reason        text CHECK (char_length(reason) <= 60),
    checked_at    timestamptz NOT NULL,
    retry_after   timestamptz NOT NULL,
    PRIMARY KEY (entity_kind, entity_ref, source)
);
COMMENT ON TABLE geo.place_name_lookup IS
    'Last name lookup per entity and source, including negative answers (ADR 025).';

CREATE TABLE app.place_name_override (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    installation_id  uuid NOT NULL REFERENCES app.installation (id) ON DELETE CASCADE,
    entity_kind      text NOT NULL CHECK (entity_kind IN ('place', 'city', 'area')),
    entity_ref       text NOT NULL CHECK (char_length(entity_ref) BETWEEN 1 AND 64),
    name             text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 120),
    name_norm        text NOT NULL,
    original_name    text CHECK (char_length(original_name) <= 300),
    approved_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (installation_id, entity_kind, entity_ref)
);
COMMENT ON TABLE app.place_name_override IS
    'A display name the user approved for one place (ADR 025); entity_ref has no foreign key.';

ALTER TABLE geo.place ADD COLUMN alias_norm text;
COMMENT ON COLUMN geo.place.alias_norm IS
    'Normalised search aliases from the source (other languages, romanizations, ASCII spellings), |-joined.';
"""

DOWNGRADE = """
DROP INDEX IF EXISTS geo.place_alias_trgm;
ALTER TABLE geo.place DROP COLUMN alias_norm;
DROP TABLE app.place_name_override;
DROP TABLE geo.place_name_lookup;
DROP TABLE geo.place_name;
"""


def upgrade() -> None:
    op.execute(UPGRADE)
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT p.id, p.name, p.names_i18n, p.name_en_norm, s.tags FROM geo.place p"
            " LEFT JOIN LATERAL (SELECT ps.tags FROM geo.place_source ps WHERE ps.place_id = p.id"
            "   AND ps.source = 'osm' ORDER BY ps.source_ref LIMIT 1) s ON true"
            " WHERE p.names_i18n IS NOT NULL OR p.name IS NOT NULL"
        )
    ).all()
    updates = []
    for row in rows:
        aliases = place_alias_norm(row.name, row.names_i18n, row.tags, row.name_en_norm)
        if aliases:
            updates.append({"i": row.id, "a": aliases})
    for start in range(0, len(updates), 5000):
        conn.execute(
            sa.text("UPDATE geo.place SET alias_norm = :a WHERE id = :i"),
            updates[start : start + 5000],
        )
    op.execute(
        "CREATE INDEX place_alias_trgm ON geo.place USING gin (alias_norm gin_trgm_ops)"
        " WHERE alias_norm IS NOT NULL"
    )


def downgrade() -> None:
    op.execute(DOWNGRADE)
