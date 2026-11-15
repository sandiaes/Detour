"""The installation bookkeeping never holds a row lock while a request works (2026-11-15).

An upsert with DO UPDATE locked the installation's row until the request's transaction ended, so
overlapping requests of one phone waited for each other, and with a small connection pool the wait
lasted for the pool timeout. These tests fail if a request can block another of the same phone.
"""

import uuid

import psycopg
import pytest
from sqlalchemy import text

from detour_api import deps
from detour_api.db import make_engine
from detour_api.deps import Database, Session
from detour_api.repo import trips
from tests.conftest import ApiEnv

pytestmark = pytest.mark.db


def _count_installation_writes(env: ApiEnv, monkeypatch: pytest.MonkeyPatch) -> list[int]:
    calls: list[int] = []
    real = trips.ensure_installation

    def counting(conn, installation_id):  # type: ignore[no-untyped-def]
        calls.append(1)
        real(conn, installation_id)

    monkeypatch.setattr(trips, "ensure_installation", counting)
    return calls


def test_a_second_transaction_of_the_same_installation_is_not_blocked(api_env: ApiEnv) -> None:
    with psycopg.connect(api_env.database_url, autocommit=True) as admin:
        admin.execute("INSERT INTO app.installation (id) VALUES (%s)", (api_env.installation_id,))
    engine = make_engine(api_env.database_url)
    try:
        with engine.connect() as first, engine.connect() as second:
            # The first request's transaction is open and has done its installation bookkeeping.
            trips.ensure_installation(first, api_env.installation_id)
            second.execute(text("SET lock_timeout = '1s'"))
            # The second must not wait for it (with DO UPDATE this raised LockNotAvailable).
            trips.ensure_installation(second, api_env.installation_id)
            second.rollback()
            first.rollback()
    finally:
        engine.dispose()


def test_touching_the_installation_does_not_wait_for_an_open_request(api_env: ApiEnv) -> None:
    with psycopg.connect(api_env.database_url, autocommit=True) as admin:
        admin.execute(
            "INSERT INTO app.installation (id, last_seen_at) VALUES (%s, now() - interval '2 hours')",
            (api_env.installation_id,),
        )
    engine = make_engine(api_env.database_url)
    try:
        with engine.connect() as request:
            trips.ensure_installation(request, api_env.installation_id)  # request in progress
            trips.touch_installation(engine, api_env.installation_id)  # must not wait for it
            request.rollback()
        with psycopg.connect(api_env.database_url, autocommit=True) as admin:
            row = admin.execute(
                "SELECT last_seen_at > now() - interval '1 minute' FROM app.installation"
                " WHERE id = %s",
                (api_env.installation_id,),
            ).fetchone()
        assert row == (True,)
    finally:
        engine.dispose()


def test_touch_changes_nothing_when_seen_within_the_hour(api_env: ApiEnv) -> None:
    with psycopg.connect(api_env.database_url, autocommit=True) as admin:
        admin.execute("INSERT INTO app.installation (id) VALUES (%s)", (api_env.installation_id,))
        before = admin.execute(
            "SELECT last_seen_at FROM app.installation WHERE id = %s", (api_env.installation_id,)
        ).fetchone()
    engine = make_engine(api_env.database_url)
    try:
        trips.touch_installation(engine, api_env.installation_id)
    finally:
        engine.dispose()
    with psycopg.connect(api_env.database_url, autocommit=True) as admin:
        after = admin.execute(
            "SELECT last_seen_at FROM app.installation WHERE id = %s", (api_env.installation_id,)
        ).fetchone()
    assert before == after


def test_a_known_installation_makes_no_installation_write(
    api_env: ApiEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _count_installation_writes(api_env, monkeypatch)
    engine = make_engine(api_env.database_url)
    try:
        session = Session(
            db=Database(engine),
            installation_id=uuid.uuid4(),
            photon=None,  # type: ignore[arg-type]
        )
        for _ in range(3):
            with session.tx() as conn:
                conn.execute(text("SELECT 1"))
        assert len(calls) == 1  # the first use only
        with psycopg.connect(api_env.database_url, autocommit=True) as admin:
            row = admin.execute(
                "SELECT count(*) FROM app.installation WHERE id = %s", (session.installation_id,)
            ).fetchone()
        assert row == (1,)
    finally:
        engine.dispose()
        deps._seen.clear()


def test_a_failed_first_request_is_not_remembered(
    api_env: ApiEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _count_installation_writes(api_env, monkeypatch)
    engine = make_engine(api_env.database_url)
    try:
        session = Session(
            db=Database(engine),
            installation_id=uuid.uuid4(),
            photon=None,  # type: ignore[arg-type]
        )
        with pytest.raises(RuntimeError), session.tx():
            raise RuntimeError("the request failed and its transaction rolled back")
        with session.tx() as conn:
            conn.execute(text("SELECT 1"))
        assert len(calls) == 2  # the row was rolled back, so it is created again
    finally:
        engine.dispose()
        deps._seen.clear()
