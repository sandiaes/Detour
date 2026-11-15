"""ADR 029: Optimize a hand-made trip is a change set with the action ``optimize``.

Like a stop edit it names no place, so the place check lets it through.

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-15
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE app.change_set DROP CONSTRAINT change_set_action_check")
    op.execute(
        "ALTER TABLE app.change_set ADD CONSTRAINT change_set_action_check"
        " CHECK (action IN ('add_place', 'remove_place', 'edit_stops', 'optimize'))"
    )
    op.execute("ALTER TABLE app.change_set DROP CONSTRAINT change_set_place_xor")
    op.execute(
        "ALTER TABLE app.change_set ADD CONSTRAINT change_set_place_xor CHECK (action IN"
        " ('remove_place', 'edit_stops', 'optimize')"
        " OR ((place_id IS NULL) <> (user_place_id IS NULL)))"
    )


def downgrade() -> None:
    op.execute("DELETE FROM app.change_set WHERE action = 'optimize'")
    op.execute("ALTER TABLE app.change_set DROP CONSTRAINT change_set_place_xor")
    op.execute(
        "ALTER TABLE app.change_set ADD CONSTRAINT change_set_place_xor CHECK (action IN"
        " ('remove_place', 'edit_stops') OR ((place_id IS NULL) <> (user_place_id IS NULL)))"
    )
    op.execute("ALTER TABLE app.change_set DROP CONSTRAINT change_set_action_check")
    op.execute(
        "ALTER TABLE app.change_set ADD CONSTRAINT change_set_action_check"
        " CHECK (action IN ('add_place', 'remove_place', 'edit_stops'))"
    )
