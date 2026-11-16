"""Names, partner links and invite codes (ADR 034, step 3).

* ``app.person.display_name``: what the other person sees ("Ana changed day 2"), optional.
* ``app.person_link``: two people who may share trips with each other, made once with an invite
  code. Stored once per pair, the smaller id first.
* ``app.link_code.kind``: ``device`` (a code that adds one of your phones, step 1) or ``invite``
  (a code that links another person to you). Both work once and for 10 minutes.

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
ALTER TABLE app.person ADD COLUMN display_name text
    CHECK (char_length(display_name) BETWEEN 1 AND 40);

ALTER TABLE app.link_code ADD COLUMN kind text NOT NULL DEFAULT 'device'
    CHECK (kind IN ('device', 'invite'));

CREATE TABLE app.person_link (
    person_a    uuid NOT NULL REFERENCES app.person (id) ON DELETE CASCADE,
    person_b    uuid NOT NULL REFERENCES app.person (id) ON DELETE CASCADE,
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (person_a, person_b),
    CHECK (person_a < person_b)
);
CREATE INDEX person_link_b_idx ON app.person_link (person_b);
COMMENT ON TABLE app.person_link IS
    'Two people who may share trips with each other, linked with an invite code (ADR 034).';
"""
    )


def downgrade() -> None:
    op.execute(
        """
DROP TABLE app.person_link;
DELETE FROM app.link_code WHERE kind = 'invite';
ALTER TABLE app.link_code DROP COLUMN kind;
ALTER TABLE app.person DROP COLUMN display_name;
"""
    )
