import os
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

from detour_api.images.store import MemoryImageStore
from detour_api.main import create_app
from detour_api.settings import Settings
from detour_api.tokens import issue_token

API_ROOT = Path(__file__).resolve().parents[1]
# The test harness itself is configured through these two; everything else is cleared per test.
KEEP_ENVIRONMENT = {"DETOUR_TEST_DATABASE_URL", "DETOUR_REQUIRE_DB_TESTS"}
TEST_SECRET = "test-secret-with-more-than-32-characters-0123456789"


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never see the developer's own DETOUR_* or Render variables."""
    for name in list(os.environ):
        if name.startswith("DETOUR_") and name not in KEEP_ENVIRONMENT:
            monkeypatch.delenv(name)
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)


@pytest.fixture
def settings() -> Settings:
    return Settings(environment="test", token_secret=TEST_SECRET)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@contextmanager
def _scratch_database() -> Iterator[str]:
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


@pytest.fixture
def scratch_database_url() -> Iterator[str]:
    """A fresh, empty database on the server named by DETOUR_TEST_DATABASE_URL.

    Locally the test is skipped when the variable is absent. In CI DETOUR_REQUIRE_DB_TESTS=1 turns
    that into a failure, so the database tests cannot be skipped by accident.
    """
    with _scratch_database() as url:
        yield url


@pytest.fixture
def second_scratch_database_url() -> Iterator[str]:
    """A second fresh database (the import tests use one as the temporary staging PostGIS)."""
    with _scratch_database() as url:
        yield url


# -- an imported database, built once per session and cloned per test -----------------------------


@dataclass
class ApiEnv:
    client: TestClient
    database_url: str
    token: str
    installation_id: uuid.UUID
    headers: dict[str, str]
    photon_requests: list[httpx.Request]
    photon_mode: dict[str, Any]

    def other_installation(self) -> dict[str, str]:
        _, token = issue_token(TEST_SECRET.encode())
        return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def imported_template_name() -> Iterator[str]:
    """Name of a database holding the migrated schema, the fixture region (made available) and
    the fixture gazetteer. Built with the real import commands."""
    from tests.import_helpers import (
        TEST_REGION,
        import_fixture_gazetteer,
        import_fixture_region,
        require_tools,
    )

    require_tools()
    with _scratch_database() as target, _scratch_database() as staging:
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("DETOUR_DATABASE_URL", target)
            command.upgrade(Config(str(API_ROOT / "alembic.ini")), "head")
        import_fixture_gazetteer(target, ["AT", "JP"])
        with tempfile.TemporaryDirectory() as work:
            import_fixture_region(target, staging, Path(work))
        with psycopg.connect(target, autocommit=True) as conn:
            # The tiny fixture region cannot pass ADR 009's gates; tests enable it by hand.
            conn.execute(
                "UPDATE geo.region SET status = 'available' WHERE id = %s", (TEST_REGION.id,)
            )
        yield make_url(target).database or ""


@pytest.fixture
def api_env(imported_template_name: str) -> Iterator[ApiEnv]:
    admin_url = os.environ["DETOUR_TEST_DATABASE_URL"]
    name = f"detour_api_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}" TEMPLATE "{imported_template_name}"')
    url = make_url(admin_url).set(database=name).render_as_string(hide_password=False)

    photon_requests: list[httpx.Request] = []
    photon_mode: dict[str, Any] = {"mode": "ok"}
    body = (Path(__file__).parent / "fixtures" / "photon-documented-response.json").read_text()

    def photon(request: httpx.Request) -> httpx.Response:
        photon_requests.append(request)
        if photon_mode["mode"] == "timeout":
            raise httpx.ConnectTimeout("simulated", request=request)
        if photon_mode["mode"] == "429":
            return httpx.Response(429, headers={"Retry-After": "10"})
        if photon_mode["mode"] == "payload":  # a test's own recorded-style answer
            return httpx.Response(
                200, content=photon_mode["payload"], headers={"content-type": "application/json"}
            )
        return httpx.Response(200, content=body, headers={"content-type": "application/json"})

    settings = Settings(
        environment="test",
        token_secret=TEST_SECRET,
        database_url=url,
        photon_daily_budget=PHOTON_BUDGET,
        # The API tests make requests in bulk no phone makes; the limits have their own tests
        # (test_abuse.py).
        rate_limit_enabled=False,
    )
    installation_id, token = issue_token(TEST_SECRET.encode())
    try:
        with TestClient(
            create_app(
                settings,
                photon_transport=httpx.MockTransport(photon),
                file_store=MemoryImageStore(),
            )
        ) as client:
            yield ApiEnv(
                client=client,
                database_url=url,
                token=token,
                installation_id=installation_id,
                headers={"Authorization": f"Bearer {token}"},
                photon_requests=photon_requests,
                photon_mode=photon_mode,
            )
    finally:
        with psycopg.connect(admin_url, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


PHOTON_BUDGET = 3


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--update-golden",
        action="store_true",
        default=False,
        help="rewrite the planner's golden files instead of comparing with them",
    )
