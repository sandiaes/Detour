from fastapi.testclient import TestClient

from detour_api import __version__


def test_health_is_ok_and_needs_no_database(client: TestClient) -> None:
    response = client.get("/v1/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "detour-api",
        "version": __version__,
        "release": None,
    }


def test_health_returns_a_request_id_and_keeps_a_valid_incoming_one(client: TestClient) -> None:
    assert len(client.get("/v1/health").headers["x-request-id"]) == 32
    assert (
        client.get("/v1/health", headers={"X-Request-ID": "abc-123"}).headers["x-request-id"]
        == "abc-123"
    )
    bad = client.get("/v1/health", headers={"X-Request-ID": "not valid!"})
    assert bad.headers["x-request-id"] != "not valid!"


def test_readiness_without_a_database_is_503(client: TestClient) -> None:
    response = client.get("/v1/health/ready")
    assert response.status_code == 503
    assert response.json()["database"]["status"] == "not_configured"


def test_unknown_path_is_404_and_unversioned_paths_do_not_exist(client: TestClient) -> None:
    assert client.get("/health").status_code == 404
    assert client.get("/v2/health").status_code == 404


def test_head_works_for_uptime_monitors(client: TestClient) -> None:
    assert client.head("/v1/health").status_code == 200
    # Same status as GET: 503 here because the test app has no database.
    assert client.head("/v1/health/ready").status_code == 503
