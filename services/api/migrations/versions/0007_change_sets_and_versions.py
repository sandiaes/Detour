"""Phase 7 (ADR 018): itinerary versions and persisted change sets.

* ``app.itinerary_version`` keeps every version of an itinerary that was replaced: by an accepted
  change set or by a hand edit of an item. ``state`` holds the version's days, items and transfers
  as rows (names and points are the items' own snapshots; nothing is copied from ``geo``), with
  the summary and the engine, configuration and data versions it was made with. Restoring a
  version writes these rows back.
* ``app.change_set`` is one previewed change (add or remove a place): the plan it would write
  (``proposal``, cleared once decided), the diff the app showed, and what became of it.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UPGRADE = """
CREATE TABLE app.change_set (
    id               uuid PRIMARY KEY,
    itinerary_id     uuid NOT NULL REFERENCES app.itinerary (id) ON DELETE CASCADE,
    base_version     integer NOT NULL CHECK (base_version >= 1),
    action           text NOT NULL CHECK (action IN ('add_place', 'remove_place')),
    place_id         uuid,                  -- geo.place.id, checked by the API
    user_place_id    uuid,                  -- app.user_place.id when previewed
    item_id          uuid,                  -- remove_place: the item removed
    duration_minutes integer CHECK (duration_minutes BETWEEN 1 AND 1440),
    target_name      text NOT NULL,         -- snapshot
    status           text NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending', 'applied', 'discarded', 'expired')),
    restores_version integer CHECK (restores_version >= 1),
    proposal         jsonb,                 -- the plan to write; cleared once decided
    diff             jsonb NOT NULL,
    notes            jsonb NOT NULL DEFAULT '[]',
    result_version   integer CHECK (result_version >= 2),
    created_at       timestamptz NOT NULL DEFAULT now(),
    decided_at       timestamptz,
    CHECK ((status = 'pending') = (decided_at IS NULL)),
    CHECK (status <> 'pending' OR proposal IS NOT NULL),
    CHECK ((status = 'applied') = (result_version IS NOT NULL)),
    CHECK ((action = 'remove_place') = (item_id IS NOT NULL)),
    CHECK (action <> 'add_place' OR ((place_id IS NULL) <> (user_place_id IS NULL)))
);
CREATE INDEX change_set_itinerary_idx ON app.change_set (itinerary_id, created_at);

CREATE TABLE app.itinerary_version (
    itinerary_id   uuid NOT NULL REFERENCES app.itinerary (id) ON DELETE CASCADE,
    version        integer NOT NULL CHECK (version >= 1),
    state          jsonb NOT NULL,
    replaced_at    timestamptz NOT NULL DEFAULT now(),
    -- The accepted change set that replaced this version; null for a hand edit.
    change_set_id  uuid REFERENCES app.change_set (id) ON DELETE SET NULL,
    PRIMARY KEY (itinerary_id, version)
);
"""

DOWNGRADE = """
DROP TABLE IF EXISTS app.itinerary_version;
DROP TABLE IF EXISTS app.change_set;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
