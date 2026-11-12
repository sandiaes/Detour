"""The seed trip is built from imported data only and is marked as seed data."""

import psycopg
import pytest
from sqlalchemy import create_engine

from detour_api.seed import (
    SEED_INSTALLATION_ID,
    SEED_REASON,
    SEED_TITLE,
    SeedError,
    build_seed_trip,
    main,
)
from detour_api.tokens import verify_token
from tests.conftest import TEST_SECRET, ApiEnv

pytestmark = pytest.mark.db


def build(env: ApiEnv) -> str:
    engine = create_engine(env.database_url.replace("postgresql://", "postgresql+psycopg://", 1))
    with engine.begin() as conn:
        trip_id = build_seed_trip(conn)
    engine.dispose()
    return str(trip_id)


def test_the_seed_trip_is_marked_and_made_only_of_imported_places(api_env: ApiEnv) -> None:
    trip_id = build(api_env)
    with psycopg.connect(api_env.database_url) as conn:
        trip = conn.execute(
            "SELECT title, is_seed, installation_id, destination_name, duration_days, status"
            " FROM app.trip WHERE id = %s",
            (trip_id,),
        ).fetchone()
        items = conn.execute(
            "SELECT i.display_name, i.place_id, i.reasons, i.type, i.duration_source, p.name"
            " FROM app.itinerary_item i LEFT JOIN geo.place p ON p.id = i.place_id ORDER BY 1"
        ).fetchall()
        flagged = conn.execute("SELECT is_seed FROM app.installation").fetchall()
    assert trip is not None
    assert (trip[0], trip[1], trip[2], trip[4], trip[5]) == (
        SEED_TITLE,
        True,
        SEED_INSTALLATION_ID,
        2,
        "active",
    )
    with psycopg.connect(api_env.database_url) as conn:
        # the destination is a real imported city, not a typed-in name
        city = conn.execute(
            "SELECT c.name FROM app.trip t JOIN geo.city c ON c.id::text = t.destination_ref"
        ).fetchone()
    assert city == (trip[3],)
    assert SEED_TITLE.startswith("SEED DATA")
    assert items, "the seed trip has items"
    for display_name, place_id, reasons, _, _, geo_name in items:
        assert place_id is not None
        assert display_name == geo_name  # every name comes from the imported data
        assert reasons == [SEED_REASON]
    assert {t for *_, t, _, _ in items} <= {"visit", "meal"}
    assert flagged == [(True,)]


def test_running_the_seed_again_replaces_it_and_gives_the_same_trip(api_env: ApiEnv) -> None:
    def snapshot() -> list[tuple[object, ...]]:
        with psycopg.connect(api_env.database_url) as conn:
            return conn.execute(
                "SELECT d.day_index, i.position, i.display_name, i.type FROM app.itinerary_item i"
                " JOIN app.itinerary_day d ON d.id = i.day_id ORDER BY 1, 2"
            ).fetchall()

    build(api_env)
    first = snapshot()
    build(api_env)
    assert snapshot() == first
    with psycopg.connect(api_env.database_url) as conn:
        assert conn.execute("SELECT count(*) FROM app.trip").fetchone() == (1,)


def test_the_seed_trip_is_invisible_to_other_installations(api_env: ApiEnv) -> None:
    build(api_env)
    assert api_env.client.get("/v1/trips", headers=api_env.headers).json() == []
    assert api_env.client.get("/v1/trips", headers=api_env.other_installation()).json() == []


def test_the_seed_needs_imported_data(
    scratch_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.import_helpers import migrate

    migrate(scratch_database_url, monkeypatch)
    engine = create_engine(
        scratch_database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    )
    with pytest.raises(SeedError, match="import"), engine.begin() as conn:
        build_seed_trip(conn)
    engine.dispose()


def test_printing_a_token_is_refused_in_production(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from detour_api.settings import get_settings

    monkeypatch.setenv("DETOUR_ENVIRONMENT", "production")
    monkeypatch.setenv("DETOUR_TOKEN_SECRET", TEST_SECRET)
    get_settings.cache_clear()
    try:
        assert main(["--print-token"]) == 2
    finally:
        get_settings.cache_clear()
    assert "Refusing" in capsys.readouterr().err


def test_the_printed_token_belongs_to_the_seed_installation(
    api_env: ApiEnv, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from detour_api.settings import get_settings

    monkeypatch.setenv("DETOUR_DATABASE_URL", api_env.database_url)
    monkeypatch.setenv("DETOUR_TOKEN_SECRET", TEST_SECRET)
    get_settings.cache_clear()
    try:
        assert main(["--print-token"]) == 0
    finally:
        get_settings.cache_clear()
    token = capsys.readouterr().out.split("Token: ")[1].strip()
    assert verify_token(TEST_SECRET.encode(), token) == SEED_INSTALLATION_ID
    seeded = api_env.client.get("/v1/trips", headers={"Authorization": f"Bearer {token}"}).json()
    assert [t["is_seed"] for t in seeded] == [True]
    assert seeded[0]["title"].startswith("SEED DATA")
