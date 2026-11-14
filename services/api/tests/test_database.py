"""Database connectivity and migrations. Needs PostgreSQL: see conftest.scratch_database_url."""

import os

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from detour_api.db import check_database, make_engine
from detour_api.main import create_app
from detour_api.settings import Settings
from tests.conftest import API_ROOT

pytestmark = pytest.mark.db


def alembic_config() -> Config:
    return Config(str(API_ROOT / "alembic.ini"))


def tables_in(url: str, schema: str) -> list[str]:
    engine = create_engine(url.replace("postgresql://", "postgresql+psycopg://", 1))
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = :s AND table_type = 'BASE TABLE'"
            ),
            {"s": schema},
        )
        # spatial_ref_sys belongs to the PostGIS extension, which may be installed in public.
        names = sorted(r[0] for r in rows if r[0] != "spatial_ref_sys")
    engine.dispose()
    return names


def test_database_is_reachable(scratch_database_url: str) -> None:
    engine = make_engine(scratch_database_url.replace("postgresql://", "postgresql+psycopg://", 1))
    result = check_database(engine)
    engine.dispose()
    assert result.status == "ok"
    assert result.schemas == []  # nothing migrated yet


GEO_TABLES = [
    "admin_area",
    "admin_code",
    "city",
    "country",
    "cover_preview",
    "currency",
    "image",
    "image_lookup",
    "import_run",
    "licence",
    "place",
    "place_signal",
    "place_source",
    "region",
    "restaurant_profile",
    "travel_time",
]
APP_TABLES = [
    "change_set",
    "installation",
    "itinerary",
    "itinerary_day",
    "itinerary_item",
    "itinerary_version",
    "provider_cache",
    "provider_usage",
    "transfer",
    "trip",
    "trip_visit",
    "user_place",
]


def test_migration_creates_the_two_separate_schemas_with_their_tables(
    scratch_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DETOUR_DATABASE_URL", scratch_database_url)
    command.upgrade(alembic_config(), "head")

    engine = make_engine(scratch_database_url.replace("postgresql://", "postgresql+psycopg://", 1))
    result = check_database(engine)
    engine.dispose()
    assert result.schemas == ["app", "geo"]
    assert tables_in(scratch_database_url, "geo") == GEO_TABLES
    assert tables_in(scratch_database_url, "app") == APP_TABLES
    # The migration bookkeeping lives outside both schemas.
    assert tables_in(scratch_database_url, "public") == ["alembic_version"]


def test_migration_is_repeatable_and_reversible(
    scratch_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DETOUR_DATABASE_URL", scratch_database_url)
    cfg = alembic_config()
    command.upgrade(cfg, "head")
    command.upgrade(cfg, "head")  # running it twice changes nothing
    command.downgrade(cfg, "base")
    engine = make_engine(scratch_database_url.replace("postgresql://", "postgresql+psycopg://", 1))
    assert check_database(engine).schemas == []
    engine.dispose()
    command.upgrade(cfg, "head")
    assert tables_in(scratch_database_url, "geo") == GEO_TABLES


def test_connections_find_postgis_in_public_or_in_the_extensions_schema(
    scratch_database_url: str,
) -> None:
    """Supabase installs PostGIS into 'extensions'; both must be on the search path."""
    engine = make_engine(scratch_database_url.replace("postgresql://", "postgresql+psycopg://", 1))
    with engine.connect() as conn:
        assert conn.execute(text("SHOW search_path")).scalar_one() == "public, extensions"
    engine.dispose()


def test_readiness_endpoint_against_a_real_database(
    scratch_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DETOUR_DATABASE_URL", scratch_database_url)
    command.upgrade(alembic_config(), "head")
    settings = Settings(environment="test")
    with TestClient(create_app(settings)) as client:
        response = client.get("/v1/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"]["status"] == "ok"
    assert body["database"]["schemas"] == ["app", "geo"]


def test_ci_database_service_provides_postgis(scratch_database_url: str) -> None:
    """The postgis/postgis image pinned in ADR 001 must really offer PostGIS (needed in Phase 2).

    Only enforced where a PostGIS server is guaranteed (CI); a plain local PostgreSQL skips it.
    """
    if os.environ.get("DETOUR_REQUIRE_DB_TESTS") != "1":
        pytest.skip("only enforced in CI, where the database service is a PostGIS image")
    engine = make_engine(scratch_database_url.replace("postgresql://", "postgresql+psycopg://", 1))
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        version = conn.execute(text("SELECT postgis_version()")).scalar_one()
    engine.dispose()
    assert str(version).startswith("3.")
