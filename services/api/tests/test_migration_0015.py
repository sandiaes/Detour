"""Migration 0015 (ADR 026, history step): the day record columns on ``app.trip_visit``."""

import uuid

import psycopg
import pytest
from alembic import command

from tests.test_database import alembic_config

pytestmark = pytest.mark.db


def test_old_archive_rows_survive_and_the_new_columns_work(
    scratch_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DETOUR_DATABASE_URL", scratch_database_url)
    cfg = alembic_config()
    command.upgrade(cfg, "0014")
    inst, trip = uuid.uuid4(), uuid.uuid4()
    with psycopg.connect(scratch_database_url, autocommit=True) as conn:
        conn.execute("INSERT INTO app.installation (id) VALUES (%s)", (inst,))
        conn.execute(
            "INSERT INTO app.trip (id, installation_id, title, destination_kind, destination_ref,"
            " destination_name, destination_point, duration_days, status, archived_at)"
            " VALUES (%s, %s, 't', 'city', '1', 'X', ST_MakePoint(1, 2), 1, 'past', now())",
            (trip, inst),
        )
        conn.execute(
            "INSERT INTO app.trip_visit (id, trip_id, kind, name, point, day_number)"
            " VALUES (%s, %s, 'attraction', 'Old', ST_MakePoint(1, 2), 1)",
            (uuid.uuid4(), trip),
        )

    command.upgrade(cfg, "0015")
    with psycopg.connect(scratch_database_url, autocommit=True) as conn:
        old = conn.execute("SELECT position, start_time, duration_minutes FROM app.trip_visit")
        assert old.fetchall() == [(None, None, None)]  # no time can be invented for old rows
        conn.execute(
            "INSERT INTO app.trip_visit (id, trip_id, kind, name, point, day_number, position,"
            " start_time, duration_minutes) VALUES (%s, %s, 'cafe', 'Café', ST_MakePoint(1, 2), 1,"
            " 2, '11:00', 45)",
            (uuid.uuid4(), trip),
        )
        with pytest.raises(psycopg.Error):
            conn.execute(
                "INSERT INTO app.trip_visit (id, trip_id, kind, name, point, day_number)"
                " VALUES (%s, %s, 'hotel', 'x', ST_MakePoint(1, 2), 1)",
                (uuid.uuid4(), trip),
            )

    command.downgrade(cfg, "0014")
    with psycopg.connect(scratch_database_url, autocommit=True) as conn:
        assert conn.execute("SELECT name FROM app.trip_visit").fetchall() == [("Old",)]
