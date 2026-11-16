"""People and their devices (ADR 034, step 1).

``app.person`` is someone who uses Detour; an installation (a phone) now belongs to a person.
Every existing installation becomes its own person, **with the same identifier**, so the rows that
name an installation (trips, your own places, display-name overrides) already name its person and
are not rewritten. A person's id is the id of its first installation ("home"); later phones join
the person with a one-time link code or the recovery code, and their data moves to the home id.

A trigger gives an installation inserted without a person (a new phone, the seed, tests) a person
of its own with the same id, so registration and every existing insert keep working unchanged.

``app.link_code`` holds the one-time codes that add a phone: only a keyed hash of the code, who
made it, when it expires and whether it was used. The recovery code's hash is on the person.

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
CREATE TABLE app.person (
    id                   uuid PRIMARY KEY,
    recovery_hash        bytea UNIQUE,
    recovery_created_at  timestamptz,
    created_at           timestamptz NOT NULL DEFAULT now(),
    CHECK ((recovery_hash IS NULL) = (recovery_created_at IS NULL))
);
COMMENT ON TABLE app.person IS
    'Someone who uses Detour; its id is the id of its first installation (ADR 034).';

INSERT INTO app.person (id, created_at) SELECT id, created_at FROM app.installation;

ALTER TABLE app.installation
    ADD COLUMN person_id  uuid REFERENCES app.person (id) ON DELETE CASCADE,
    ADD COLUMN joined_at  timestamptz,
    ADD COLUMN revoked_at timestamptz;
UPDATE app.installation SET person_id = id;
ALTER TABLE app.installation ALTER COLUMN person_id SET NOT NULL;
CREATE INDEX installation_person_idx ON app.installation (person_id);
COMMENT ON COLUMN app.installation.joined_at IS
    'When this phone joined its person with a code; null for the phone that started the person.';
COMMENT ON COLUMN app.installation.revoked_at IS
    'Removed from its person (Your devices, or the recovery code was used); its token is refused.';

CREATE FUNCTION app.installation_default_person() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.person_id IS NULL THEN
        INSERT INTO app.person (id) VALUES (NEW.id) ON CONFLICT (id) DO NOTHING;
        NEW.person_id := NEW.id;
    END IF;
    RETURN NEW;
END
$$;
CREATE TRIGGER installation_default_person
    BEFORE INSERT ON app.installation
    FOR EACH ROW EXECUTE FUNCTION app.installation_default_person();

CREATE TABLE app.link_code (
    code_hash   bytea PRIMARY KEY,
    person_id   uuid NOT NULL REFERENCES app.person (id) ON DELETE CASCADE,
    created_by  uuid NOT NULL REFERENCES app.installation (id) ON DELETE CASCADE,
    created_at  timestamptz NOT NULL DEFAULT now(),
    expires_at  timestamptz NOT NULL,
    used_at     timestamptz,
    used_by     uuid,
    CHECK (expires_at > created_at),
    CHECK ((used_at IS NULL) = (used_by IS NULL))
);
CREATE INDEX link_code_person_idx ON app.link_code (person_id, created_at DESC);
COMMENT ON TABLE app.link_code IS
    'One-time codes that add a phone to a person: a keyed hash only, 10 minutes, one use (ADR 034).';
"""
    )


def downgrade() -> None:
    op.execute(
        """
DROP TABLE app.link_code;
DROP TRIGGER installation_default_person ON app.installation;
DROP FUNCTION app.installation_default_person();
ALTER TABLE app.installation DROP COLUMN person_id, DROP COLUMN joined_at, DROP COLUMN revoked_at;
DROP TABLE app.person;
"""
    )
