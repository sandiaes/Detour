"""Migration 0025 (ADR 034, step 2): a trip's owner is its person and its first member; places and
display names belong to the person; downgrading puts the columns back."""

import uuid

import psycopg
import pytest
from alembic import command

from tests.test_database import alembic_config

pytestmark = pytest.mark.db


def test_existing_trips_get_their_owner_as_member(
    scratch_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DETOUR_DATABASE_URL", scratch_database_url)
    cfg = alembic_config()
    command.upgrade(cfg, "0024")
    inst, trip, place = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with psycopg.connect(scratch_database_url, autocommit=True) as conn:
        conn.execute("INSERT INTO app.installation (id) VALUES (%s)", (inst,))
        conn.execute(
            "INSERT INTO app.trip (id, installation_id, title, destination_kind, destination_ref,"
            " destination_name, destination_point, duration_days)"
            " VALUES (%s, %s, 't', 'city', '1', 'X', ST_MakePoint(1, 2), 1)",
            (trip, inst),
        )
        conn.execute(
            "INSERT INTO app.user_place (id, installation_id, kind, name, geom, source)"
            " VALUES (%s, %s, 'location', 'p', ST_MakePoint(1, 2), 'manual_pin')",
            (place, inst),
        )

    command.upgrade(cfg, "0025")
    with psycopg.connect(scratch_database_url, autocommit=True) as conn:
        assert conn.execute("SELECT owner_person_id FROM app.trip").fetchall() == [(inst,)]
        assert conn.execute("SELECT person_id FROM app.user_place").fetchall() == [(inst,)]
        members = conn.execute("SELECT trip_id, person_id, role FROM app.trip_member").fetchall()
        assert members == [(trip, inst, "owner")]

    command.downgrade(cfg, "0024")
    with psycopg.connect(scratch_database_url, autocommit=True) as conn:
        assert conn.execute("SELECT installation_id FROM app.trip").fetchall() == [(inst,)]
        assert conn.execute("SELECT installation_id FROM app.user_place").fetchall() == [(inst,)]
