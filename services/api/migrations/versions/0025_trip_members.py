"""Trips belong to people, with members (ADR 034, step 2).

Since migration 0024 every value in ``app.trip.installation_id``, ``app.user_place.installation_id``
and ``app.place_name_override.installation_id`` is a person's id (a person's id is the id of its
first installation, and joining moved a phone's rows to its person). This migration says so:

* ``app.trip.installation_id`` becomes ``owner_person_id`` (fk to ``app.person``): the person who
  created the trip, the only one who may delete it.
* ``app.trip_member`` lists who may see and change a trip: its owner (role ``owner``, exactly one per
  trip) and, from step 3, people it is shared with (role ``editor``). A trigger adds the owner when a
  trip is inserted, so every insert of a trip keeps working unchanged.
* ``app.user_place`` and ``app.place_name_override`` belong to a person (``person_id``).

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
-- Defensive: a row still naming a phone that joined another person moves to that person.
UPDATE app.trip t SET installation_id = i.person_id
  FROM app.installation i WHERE i.id = t.installation_id AND i.person_id <> t.installation_id;
UPDATE app.user_place u SET installation_id = i.person_id
  FROM app.installation i WHERE i.id = u.installation_id AND i.person_id <> u.installation_id;
DELETE FROM app.place_name_override o
  USING app.installation i WHERE i.id = o.installation_id AND i.person_id <> o.installation_id;

ALTER TABLE app.trip DROP CONSTRAINT trip_installation_id_fkey;
ALTER TABLE app.trip RENAME COLUMN installation_id TO owner_person_id;
ALTER TABLE app.trip ADD CONSTRAINT trip_owner_person_id_fkey
  FOREIGN KEY (owner_person_id) REFERENCES app.person (id) ON DELETE CASCADE;
ALTER INDEX app.trip_installation_idx RENAME TO trip_owner_idx;

ALTER TABLE app.user_place DROP CONSTRAINT user_place_installation_id_fkey;
ALTER TABLE app.user_place RENAME COLUMN installation_id TO person_id;
ALTER TABLE app.user_place ADD CONSTRAINT user_place_person_id_fkey
  FOREIGN KEY (person_id) REFERENCES app.person (id) ON DELETE CASCADE;
ALTER INDEX app.user_place_installation_idx RENAME TO user_place_person_idx;

ALTER TABLE app.place_name_override DROP CONSTRAINT place_name_override_installation_id_fkey;
ALTER TABLE app.place_name_override RENAME COLUMN installation_id TO person_id;
ALTER TABLE app.place_name_override ADD CONSTRAINT place_name_override_person_id_fkey
  FOREIGN KEY (person_id) REFERENCES app.person (id) ON DELETE CASCADE;
ALTER TABLE app.place_name_override
  RENAME CONSTRAINT place_name_override_installation_id_entity_kind_entity_ref_key
  TO place_name_override_person_entity_key;

CREATE TABLE app.trip_member (
    trip_id    uuid NOT NULL REFERENCES app.trip (id) ON DELETE CASCADE,
    person_id  uuid NOT NULL REFERENCES app.person (id) ON DELETE CASCADE,
    role       text NOT NULL CHECK (role IN ('owner', 'editor')),
    added_at   timestamptz NOT NULL DEFAULT now(),
    added_by   uuid REFERENCES app.person (id) ON DELETE SET NULL,
    PRIMARY KEY (trip_id, person_id)
);
CREATE INDEX trip_member_person_idx ON app.trip_member (person_id, trip_id);
CREATE UNIQUE INDEX trip_member_one_owner ON app.trip_member (trip_id) WHERE role = 'owner';
COMMENT ON TABLE app.trip_member IS
    'Who may see and change a trip: its owner and the people it is shared with (ADR 034).';

INSERT INTO app.trip_member (trip_id, person_id, role, added_at)
SELECT id, owner_person_id, 'owner', created_at FROM app.trip;

CREATE FUNCTION app.trip_add_owner() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO app.trip_member (trip_id, person_id, role, added_at)
    VALUES (NEW.id, NEW.owner_person_id, 'owner', NEW.created_at)
    ON CONFLICT (trip_id, person_id) DO NOTHING;
    RETURN NULL;
END
$$;
CREATE TRIGGER trip_add_owner AFTER INSERT ON app.trip
    FOR EACH ROW EXECUTE FUNCTION app.trip_add_owner();
"""
    )


def downgrade() -> None:
    op.execute(
        """
DROP TRIGGER trip_add_owner ON app.trip;
DROP FUNCTION app.trip_add_owner();
DROP TABLE app.trip_member;

ALTER TABLE app.place_name_override
  RENAME CONSTRAINT place_name_override_person_entity_key
  TO place_name_override_installation_id_entity_kind_entity_ref_key;
ALTER TABLE app.place_name_override DROP CONSTRAINT place_name_override_person_id_fkey;
ALTER TABLE app.place_name_override RENAME COLUMN person_id TO installation_id;
ALTER TABLE app.place_name_override ADD CONSTRAINT place_name_override_installation_id_fkey
  FOREIGN KEY (installation_id) REFERENCES app.installation (id) ON DELETE CASCADE;

ALTER INDEX app.user_place_person_idx RENAME TO user_place_installation_idx;
ALTER TABLE app.user_place DROP CONSTRAINT user_place_person_id_fkey;
ALTER TABLE app.user_place RENAME COLUMN person_id TO installation_id;
ALTER TABLE app.user_place ADD CONSTRAINT user_place_installation_id_fkey
  FOREIGN KEY (installation_id) REFERENCES app.installation (id) ON DELETE CASCADE;

ALTER INDEX app.trip_owner_idx RENAME TO trip_installation_idx;
ALTER TABLE app.trip DROP CONSTRAINT trip_owner_person_id_fkey;
ALTER TABLE app.trip RENAME COLUMN owner_person_id TO installation_id;
ALTER TABLE app.trip ADD CONSTRAINT trip_installation_id_fkey
  FOREIGN KEY (installation_id) REFERENCES app.installation (id) ON DELETE CASCADE;
"""
    )
