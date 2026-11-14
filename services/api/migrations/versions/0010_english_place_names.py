"""English place names in search: ``geo.place.name_en_norm``.

The import already keeps every ``name:*`` tag of an OpenStreetMap object in ``geo.place.names_i18n``.
Search matched only ``name_norm`` (the local name), so a traveller typing "Hohensalzburg Fortress"
did not find "Festung Hohensalzburg". ``name_en_norm`` is the normalised English name, set only when
it exists and differs from the local name; search matches it as well as ``name_norm``.

Existing rows are filled here with the same ``normalize_text`` function the importer uses, so both
sides agree; later imports keep the column current.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from detour_api.textnorm import normalize_text

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE geo.place ADD COLUMN name_en_norm text;
        COMMENT ON COLUMN geo.place.name_en_norm IS
            'Normalised English name (names_i18n->en) when it differs from name_norm; search matches it too.';
        """
    )
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, name_norm, names_i18n->>'en' AS en FROM geo.place"
            " WHERE names_i18n ? 'en' AND names_i18n->>'en' <> ''"
        )
    ).all()
    updates = []
    for row in rows:
        norm = normalize_text(row.en)
        if norm and norm != row.name_norm:
            updates.append({"i": row.id, "n": norm})
    if updates:
        conn.execute(sa.text("UPDATE geo.place SET name_en_norm = :n WHERE id = :i"), updates)
    op.execute(
        "CREATE INDEX place_name_en_trgm ON geo.place USING gin (name_en_norm gin_trgm_ops)"
        " WHERE name_en_norm IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX geo.place_name_en_trgm")
    op.execute("ALTER TABLE geo.place DROP COLUMN name_en_norm")
