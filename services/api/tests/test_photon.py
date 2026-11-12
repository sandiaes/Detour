"""The Photon adapter, contract-tested against a response shaped like Photon's documented format.

No test here reaches the network: the transport is a recorded-response stub.
"""

import json
from pathlib import Path

import httpx
import psycopg
import pytest
from sqlalchemy import create_engine

from detour_api.adapters.photon import PhotonClient, cache_key, parse_features
from detour_api.settings import Settings
from tests.conftest import PHOTON_BUDGET, ApiEnv

FIXTURE = Path(__file__).parent / "fixtures" / "photon-documented-response.json"


def test_parser_keeps_valid_features_and_skips_malformed_ones() -> None:
    results = parse_features(json.loads(FIXTURE.read_text()))
    # out-of-range longitude and a feature without a name are dropped, not repaired
    assert [r.name for r in results] == ["Examplestadt", "Examplestadt Arena"]
    first, second = results
    assert (first.lat, first.lon, first.ref, first.osm_key, first.osm_value) == (
        52.5170365,
        13.3888599,
        "N240109189",
        "place",
        "city",
    )
    assert second.ref == "W38862723" and second.street == "Teststrasse"
    assert second.postcode == "14053" and second.country_code == "TL"
    with pytest.raises(ValueError, match="FeatureCollection"):
        parse_features({"nope": 1})


def test_cache_key_ignores_case_spacing_and_fine_position() -> None:
    a = cache_key("Examplestadt  Arena", 5, "en", ("city",), ("AT",), 48.2082, 16.3738)
    b = cache_key("examplestadt arena", 5, "en", ("city",), ("AT",), 48.2399, 16.4249)
    assert a == b  # same 0.1-degree cell
    assert a != cache_key("examplestadt arena", 5, "de", ("city",), ("AT",), 48.2, 16.4)
    assert a != cache_key("examplestadt arena", 5, "en", ("city",), ("AT",), 49.2, 16.4)


def test_photon_is_off_in_tests_unless_a_transport_is_injected() -> None:
    engine = create_engine("postgresql+psycopg://x@localhost/none")
    assert PhotonClient(Settings(environment="test"), engine).enabled is False
    assert PhotonClient(Settings(environment="test", photon_enabled=False), engine).enabled is False
    assert PhotonClient(Settings(environment="local"), None).enabled is False


@pytest.mark.db
def test_external_search_is_not_made_when_not_requested_or_not_needed(api_env: ApiEnv) -> None:
    c, h = api_env.client, api_env.headers
    c.get("/v1/places/search", params={"q": "nothing here"}, headers=h)
    c.get("/v1/places/search", params={"q": "museum", "include_external": "true"}, headers=h)
    body = c.get(
        "/v1/destinations/search", params={"q": "testburg", "include_external": "true"}, headers=h
    ).json()
    assert body["external"]["state"] == "not_needed"
    assert api_env.photon_requests == []


@pytest.mark.db
def test_nothing_local_asks_photon_once_then_answers_from_the_cache(api_env: ApiEnv) -> None:
    params = {"q": "examplestadt arena", "include_external": "true", "region": "test-region"}
    first = api_env.client.get("/v1/places/search", params=params, headers=api_env.headers).json()
    assert first["results"] == []
    assert first["external"]["state"] == "ok"
    names = [r["name"] for r in first["external"]["results"]]
    assert names == ["Examplestadt", "Examplestadt Arena"]
    arena = first["external"]["results"][1]
    assert arena["provider"] == "photon" and arena["ref"] == "W38862723"
    assert arena["licence"] == "ODbL-1.0"

    second = api_env.client.get("/v1/places/search", params=params, headers=api_env.headers).json()
    assert second["external"]["state"] == "cached"
    assert second["external"]["results"] == first["external"]["results"]
    assert len(api_env.photon_requests) == 1  # one real call for two requests


@pytest.mark.db
def test_the_outgoing_request_identifies_the_app_and_nothing_about_the_user(
    api_env: ApiEnv,
) -> None:
    api_env.client.get(
        "/v1/places/search",
        params={
            "q": "examplestadt",
            "include_external": "true",
            "region": "test-region",
            "lat": 48.2082,
            "lon": 16.3738,
            "lang": "en",
        },
        headers=api_env.headers,
    )
    (request,) = api_env.photon_requests
    assert request.url.path == "/api"
    assert "Detour-backend" in request.headers["user-agent"]
    assert "github.com/sandiaes/Detour" in request.headers["user-agent"]
    assert "authorization" not in request.headers  # the bearer token is never forwarded
    assert str(api_env.installation_id) not in str(request.url)
    params = httpx.QueryParams(request.url.query)
    assert params["q"] == "examplestadt" and params["countrycode"] == "AT"
    assert (params["lat"], params["lon"]) == ("48.2", "16.4")  # the position is rounded
    assert params["lang"] == "en" and params["limit"] == "10"


@pytest.mark.db
def test_cached_rows_carry_no_installation_identifier(api_env: ApiEnv) -> None:
    api_env.client.get(
        "/v1/places/search",
        params={"q": "examplestadt", "include_external": "true"},
        headers=api_env.headers,
    )
    with psycopg.connect(api_env.database_url) as conn:
        columns = [
            r[0]
            for r in conn.execute(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_schema = 'app' AND table_name = 'provider_cache'"
            ).fetchall()
        ]
        dump = conn.execute("SELECT response::text FROM app.provider_cache").fetchone()
    assert columns == ["cache_key", "provider", "response", "fetched_at", "expires_at"]
    assert dump is not None and str(api_env.installation_id) not in dump[0]


@pytest.mark.db
def test_the_daily_budget_stops_calls_before_the_limit(api_env: ApiEnv) -> None:
    states = []
    for i in range(PHOTON_BUDGET + 2):
        body = api_env.client.get(
            "/v1/destinations/search",
            params={"q": f"nowhere{i}x", "include_external": "true"},
            headers=api_env.headers,
        ).json()
        states.append(body["external"]["state"])
    assert states == ["ok"] * PHOTON_BUDGET + ["budget_exhausted"] * 2
    assert len(api_env.photon_requests) == PHOTON_BUDGET
    # Cached answers do not need budget.
    again = api_env.client.get(
        "/v1/destinations/search",
        params={"q": "nowhere0x", "include_external": "true"},
        headers=api_env.headers,
    ).json()
    assert again["external"]["state"] == "cached"
    with psycopg.connect(api_env.database_url) as conn:
        row = conn.execute("SELECT calls FROM app.provider_usage").fetchone()
    assert row == (PHOTON_BUDGET,)


@pytest.mark.db
def test_a_photon_outage_degrades_to_local_results_and_pauses_calls(api_env: ApiEnv) -> None:
    api_env.photon_mode["mode"] = "timeout"
    c, h = api_env.client, api_env.headers
    first = c.get(
        "/v1/places/search", params={"q": "xyzzy1", "include_external": "true"}, headers=h
    )
    assert first.status_code == 200
    assert first.json()["external"] == {"state": "unavailable", "provider": "photon", "results": []}
    # Local search still works while Photon is down.
    local = c.get(
        "/v1/places/search", params={"q": "museum", "include_external": "true"}, headers=h
    )
    assert local.json()["results"] and local.json()["external"]["state"] == "not_needed"
    # A second miss does not hammer the failing service: it is paused.
    c.get("/v1/places/search", params={"q": "xyzzy2", "include_external": "true"}, headers=h)
    assert len(api_env.photon_requests) == 1


@pytest.mark.db
def test_rate_limiting_by_photon_pauses_calls_for_longer(api_env: ApiEnv) -> None:
    api_env.photon_mode["mode"] = "429"
    c, h = api_env.client, api_env.headers
    body = c.get(
        "/v1/places/search", params={"q": "xyzzy1", "include_external": "true"}, headers=h
    ).json()
    assert body["external"]["state"] == "unavailable"
    api_env.photon_mode["mode"] = "ok"
    again = c.get(
        "/v1/places/search", params={"q": "xyzzy2", "include_external": "true"}, headers=h
    ).json()
    assert again["external"]["state"] == "unavailable"  # still paused after the 429
    assert len(api_env.photon_requests) == 1


@pytest.mark.db
def test_external_search_needs_a_query_and_a_token(api_env: ApiEnv) -> None:
    r = api_env.client.get(
        "/v1/places/search",
        params={"lat": 48.2, "lon": 16.3, "include_external": "true"},
        headers=api_env.headers,
    )
    assert r.status_code == 422 and r.json()["code"] == "query_required"
    r = api_env.client.get("/v1/places/search", params={"q": "xyzzy", "include_external": "true"})
    assert r.status_code == 401
    assert api_env.photon_requests == []
