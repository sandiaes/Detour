"""Photos for areas: ``geo.admin_area.wikidata_id`` and the lookup kind ``area``.

ADR 022 amendment (2026-11-14), decision d. A country or region destination gets its photo through
its Wikidata item, which the import now keeps from the boundary's ``wikidata`` tag. Areas imported
before this migration have none until the region is imported again ("Import region" workflow);
OpenStreetMap's tags cannot be asked for anywhere else (Overpass is not allowed).

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-14
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE geo.admin_area ADD COLUMN wikidata_id text CHECK (wikidata_id ~ '^Q[0-9]+$')"
    )
    op.execute("ALTER TABLE geo.image_lookup DROP CONSTRAINT image_lookup_kind_check")
    op.execute(
        "ALTER TABLE geo.image_lookup ADD CONSTRAINT image_lookup_kind_check"
        " CHECK (kind IN ('place', 'city', 'area'))"
    )


def downgrade() -> None:
    op.execute("DELETE FROM geo.image_lookup WHERE kind = 'area'")
    op.execute("ALTER TABLE geo.image_lookup DROP CONSTRAINT image_lookup_kind_check")
    op.execute(
        "ALTER TABLE geo.image_lookup ADD CONSTRAINT image_lookup_kind_check"
        " CHECK (kind IN ('place', 'city'))"
    )
    op.execute("ALTER TABLE geo.admin_area DROP COLUMN wikidata_id")
