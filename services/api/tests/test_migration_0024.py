"""Migration 0024 (ADR 034, step 1): every existing installation becomes a person with the same id,
so its trips need no rewrite; a new installation gets a person of its own from the trigger."""

import uuid

import psycopg
import pytest
from alembic import command

from tests.test_database import alembic_config

pytestmark = pytest.mark.db


def test_existing_phones_become_people_and_new_ones_get_a_person(
    scratch_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DETOUR_DATABASE_URL", scratch_database_url)
    cfg = alembic_config()
    command.upgrade(cfg, "0023")
    old, trip = uuid.uuid4(), uuid.uuid4()
    with psycopg.connect(scratch_database_url, autocommit=True) as conn:
        conn.execute("INSERT INTO app.installation (id) VALUES (%s)", (old,))
        conn.execute(
            "INSERT INTO app.trip (id, installation_id, title, destination_kind, destination_ref,"
            " destination_name, destination_point, duration_days)"
            " VALUES (%s, %s, 't', 'city', '1', 'X', ST_MakePoint(1, 2), 1)",
            (trip, old),
        )

    command.upgrade(cfg, "0024")
    new = uuid.uuid4()
    with psycopg.connect(scratch_database_url, autocommit=True) as conn:
        conn.execute("INSERT INTO app.installation (id) VALUES (%s)", (new,))
        rows = conn.execute(
            "SELECT i.id, i.person_id, i.revoked_at, p.recovery_hash FROM app.installation i"
            " JOIN app.person p ON p.id = i.person_id ORDER BY i.created_at"
        ).fetchall()
        assert rows == [(old, old, None, None), (new, new, None, None)]
        assert conn.execute("SELECT installation_id FROM app.trip").fetchall() == [(old,)]
        with pytest.raises(psycopg.Error):  # a recovery hash needs its date, and the reverse
            conn.execute("UPDATE app.person SET recovery_hash = '\\x00' WHERE id = %s", (old,))

    command.downgrade(cfg, "0023")
    with psycopg.connect(scratch_database_url, autocommit=True) as conn:
        assert conn.execute("SELECT count(*) FROM app.trip").fetchone() == (1,)
