"""Needs no server: points at a port where nothing listens."""

from fastapi.testclient import TestClient

from detour_api.main import create_app
from detour_api.settings import Settings


def test_unreachable_database_gives_503_and_leaks_no_credentials() -> None:
    settings = Settings(
        environment="test",
        database_url="postgresql://someuser:hunter2@127.0.0.1:1/postgres",
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/v1/health").status_code == 200  # liveness does not need the database
        response = client.get("/v1/health/ready")
    assert response.status_code == 503
    assert response.json()["database"]["status"] == "unavailable"
    assert "hunter2" not in response.text
    assert "someuser" not in response.text
