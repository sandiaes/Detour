from fastapi.testclient import TestClient

from detour_api.main import create_app
from detour_api.settings import Settings


def test_config_serves_the_map_style_and_attribution(client: TestClient) -> None:
    body = client.get("/v1/config").json()
    assert body["config_version"] == "1"
    assert body["map"]["style_url"] == "https://tiles.openfreemap.org/styles/liberty"
    assert [a["text"] for a in body["map"]["attribution"]] == [
        "OpenFreeMap",
        "© OpenMapTiles",
        "Data from OpenStreetMap",
    ]


def test_config_follows_backend_settings_so_no_app_release_is_needed() -> None:
    settings = Settings(
        environment="test",
        map_style_url="https://tiles.example.org/fallback.json",
        config_version="2",
    )
    with TestClient(create_app(settings)) as c:
        body = c.get("/v1/config").json()
    assert body["map"]["style_url"] == "https://tiles.example.org/fallback.json"
    assert body["config_version"] == "2"


def test_config_needs_no_token(client: TestClient) -> None:
    assert client.get("/v1/config").status_code == 200
