import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

from detour_api.main import create_app
from detour_api.settings import Settings

API_ROOT = Path(__file__).resolve().parents[1]
TEST_SECRET = "test-secret-with-more-than-32-characters-0123456789"


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never see the developer's own DETOUR_* or Render variables."""
    for name in list(os.environ):
        if name.startswith("DETOUR_") and name != "DETOUR_TEST_DATABASE_URL":
            monkeypatch.delenv(name)
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)


@pytest.fixture
def settings() -> Settings:
    return Settings(environment="test", token_secret=TEST_SECRET)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def scratch_database_url() -> Iterator[str]:
    """A fresh, empty database on the server named by DETOUR_TEST_DATABASE_URL.

    Locally the test is skipped when the variable is absent. In CI DETOUR_REQUIRE_DB_TESTS=1 turns
    that into a failure, so the database tests cannot be skipped by accident.
    """
    admin_url = os.environ.get("DETOUR_TEST_DATABASE_URL")
    if not admin_url:
        if os.environ.get("DETOUR_REQUIRE_DB_TESTS") == "1":
            pytest.fail("DETOUR_TEST_DATABASE_URL is required in CI")
        pytest.skip("DETOUR_TEST_DATABASE_URL is not set")
    name = f"detour_test_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    scratch = make_url(admin_url).set(database=name).render_as_string(hide_password=False)
    try:
        yield scratch
    finally:
        with psycopg.connect(admin_url, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
