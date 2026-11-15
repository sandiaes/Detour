"""Close the migration bookkeeping table to Supabase's Data API (Phase 9, docs/security.md).

Supabase exposes the ``public`` schema through its REST API and grants its ``anon`` and
``authenticated`` roles access to tables there; ``public.alembic_version`` is the only table Detour
keeps in ``public``. Supabase's security advisor reported it (RLS disabled in public, 2026-11-15).
Row level security with no policy shuts those roles out; the API and the migrations connect as the
table's owner, which RLS does not restrict. The grants are revoked as well where the roles exist
(they exist on Supabase, not on a plain PostgreSQL).

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-15
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE public.alembic_version ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        DO $$
        DECLARE r text;
        BEGIN
            FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
                    EXECUTE format('REVOKE ALL ON public.alembic_version FROM %I', r);
                END IF;
            END LOOP;
        END
        $$
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE public.alembic_version DISABLE ROW LEVEL SECURITY")
