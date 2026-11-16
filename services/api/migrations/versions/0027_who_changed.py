"""Who changed a plan or a trip last (ADR 034, step 4).

The API sets ``detour.person`` (a transaction-local setting) to the caller's person at the start of
every transaction. Triggers copy it, with the time, onto a plan whose version changes (or that is
created) and onto a trip whose ``updated_at`` changes, so every path that writes a plan or a trip
records who did it without each having to remember.

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
ALTER TABLE app.itinerary
    ADD COLUMN changed_by uuid REFERENCES app.person (id) ON DELETE SET NULL,
    ADD COLUMN changed_at timestamptz;
ALTER TABLE app.trip
    ADD COLUMN updated_by uuid REFERENCES app.person (id) ON DELETE SET NULL;

CREATE FUNCTION app.current_person() RETURNS uuid
LANGUAGE sql STABLE AS $$
    SELECT nullif(current_setting('detour.person', true), '')::uuid
$$;

CREATE FUNCTION app.itinerary_who_changed() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' OR NEW.version IS DISTINCT FROM OLD.version THEN
        NEW.changed_at := now();
        NEW.changed_by := coalesce(app.current_person(), NEW.changed_by);
    END IF;
    RETURN NEW;
END
$$;
CREATE TRIGGER itinerary_who_changed BEFORE INSERT OR UPDATE ON app.itinerary
    FOR EACH ROW EXECUTE FUNCTION app.itinerary_who_changed();

CREATE FUNCTION app.trip_who_changed() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.updated_at IS DISTINCT FROM OLD.updated_at THEN
        NEW.updated_by := coalesce(app.current_person(), NEW.updated_by);
    END IF;
    RETURN NEW;
END
$$;
CREATE TRIGGER trip_who_changed BEFORE UPDATE ON app.trip
    FOR EACH ROW EXECUTE FUNCTION app.trip_who_changed();
"""
    )


def downgrade() -> None:
    op.execute(
        """
DROP TRIGGER trip_who_changed ON app.trip;
DROP FUNCTION app.trip_who_changed();
DROP TRIGGER itinerary_who_changed ON app.itinerary;
DROP FUNCTION app.itinerary_who_changed();
DROP FUNCTION app.current_person();
ALTER TABLE app.trip DROP COLUMN updated_by;
ALTER TABLE app.itinerary DROP COLUMN changed_by, DROP COLUMN changed_at;
"""
    )
