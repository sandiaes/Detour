"""Create the empty geo and app schemas.

``geo`` holds imported open data (rebuildable, ODbL-derived); ``app`` holds user data. They stay
separate on purpose: the split is also a licence boundary (docs/data-model.md, section 5).
Tables arrive in later phases. PostGIS is enabled where it is first needed (Phase 2), because on
Supabase it is switched on in the dashboard (docs/deployment.md).

Revision ID: 0001
Revises:
Create Date: 2026-11-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS geo")
    op.execute("CREATE SCHEMA IF NOT EXISTS app")


def downgrade() -> None:
    # No CASCADE: refuses to drop a schema that has tables, so data is never lost silently.
    op.execute("DROP SCHEMA IF EXISTS app")
    op.execute("DROP SCHEMA IF EXISTS geo")
