"""Adding a restaurant or cafe through the API (ADR 019, ADR 026): search (the user's saved places,
then Photon through the backend), and manual entry. Restaurants and cafes are not imported; the
slot suggestions and the change-set placement are gone (the user chooses the day and time). Photon
answers from a recorded-response stub, never the network.
"""

import json
from typing import Any

import httpx
import psycopg
import pytest

from tests.conftest import PHOTON_BUDGET, ApiEnv
from tests.test_api_changes import _plan, _preview

pytestmark = pytest.mark.db

TESTBURG = (48.2082, 16.3738)


def _search(env: ApiEnv, **params: Any) -> Any:
    return env.client.get("/v1/restaurants/search", params=params, headers=env.headers)


def _save(env: ApiEnv, **body: Any) -> dict[str, Any]:
    payload = {"kind": "restaurant", "source": "manual_pin", **body}
    r = env.client.post("/v1/user-places", json=payload, headers=env.headers)
    assert r.status_code == 201, r.text
    saved: dict[str, Any] = r.json()
    return saved


# -- search: your saved places first, then Photon, then manual entry -----------------------------


def test_nothing_local_asks_photon_for_restaurants_only(api_env: ApiEnv) -> None:
    body = _search(api_env, q="examplestadt", include_external="true", region="test-region").json()
    assert "results" not in body and body["your_places"] == []
    (request,) = api_env.photon_requests
    params = httpx.QueryParams(request.url.query)
    assert params.get_list("osm_tag") == ["amenity:restaurant", "amenity:cafe"]
    assert "Detour-backend" in request.headers["user-agent"]
    assert str(api_env.installation_id) not in str(request.url)
    # The recorded answer holds no restaurant: whatever Photon returns, only restaurants and cafés
    # are passed on, even if the server ignored the tag filter.
    assert body["external"]["state"] == "ok" and body["external"]["results"] == []


def test_photon_results_carry_their_venue_type_and_no_cuisine_or_meal_types(
    api_env: ApiEnv,
) -> None:
    payload = {
        "type": "FeatureCollection",
        "features": [
            _feature("Gasthaus Beispiel", "restaurant", 1),
            _feature("Café Beispiel", "cafe", 2),
            _feature("Kiosk Beispiel", "fast_food", 3),
            {
                **_feature("Park Beispiel", "park", 4),
                "properties": {
                    "name": "Park",
                    "osm_key": "leisure",
                    "osm_value": "park",
                    "osm_type": "N",
                    "osm_id": 4,
                },
            },
        ],
    }
    api_env.photon_requests.clear()
    _use_photon_payload(api_env, payload)
    body = _search(api_env, q="beispiel", include_external="true").json()
    found = {r["name"]: r for r in body["external"]["results"]}
    assert set(found) == {"Gasthaus Beispiel", "Café Beispiel"}
    assert found["Gasthaus Beispiel"]["venue_type"] == "restaurant"
    assert found["Café Beispiel"]["venue_type"] == "cafe"
    assert all(
        "cuisines" not in r and "meal_types" not in r and r["licence"] == "ODbL-1.0"
        for r in found.values()
    )
    assert found["Gasthaus Beispiel"]["ref"] == "N1"


def test_the_provider_budget_counter_stops_restaurant_calls_at_the_limit(api_env: ApiEnv) -> None:
    states = [
        _search(api_env, q=f"nowhere{i}x", include_external="true").json()["external"]["state"]
        for i in range(PHOTON_BUDGET + 2)
    ]
    assert states == ["ok"] * PHOTON_BUDGET + ["budget_exhausted"] * 2
    assert len(api_env.photon_requests) == PHOTON_BUDGET
    # A cached question needs no budget, and local results never needed any.
    assert (
        _search(api_env, q="nowhere0x", include_external="true").json()["external"]["state"]
        == "cached"
    )
    assert len(api_env.photon_requests) == PHOTON_BUDGET
    with psycopg.connect(api_env.database_url) as conn:
        assert conn.execute("SELECT calls FROM app.provider_usage").fetchone() == (PHOTON_BUDGET,)
    # With the budget used up, the search still answers and manual entry still works.
    body = _search(api_env, q="nowhere9y", include_external="true").json()
    assert body["external"] == {"state": "budget_exhausted", "provider": "photon", "results": []}
    assert _save(api_env, name="By hand", lat=48.21, lon=16.37)["kind"] == "restaurant"


def test_your_saved_restaurants_are_found_before_photon_is_asked(api_env: ApiEnv) -> None:
    saved = _save(api_env, name="Tante Emma Stube", lat=48.21, lon=16.37)
    body = _search(api_env, q="emma", include_external="true").json()
    assert [p["id"] for p in body["your_places"]] == [saved["id"]]
    assert body["external"]["state"] == "not_needed" and api_env.photon_requests == []


def test_search_needs_a_query_and_a_token(api_env: ApiEnv) -> None:
    assert api_env.client.get("/v1/restaurants/search", params={"q": "x"}).status_code == 401
    assert _search(api_env, q="x").status_code == 422
    assert _search(api_env, q="post", lat=48.2).status_code == 422


# -- manual entry ----------------------------------------------------------------------------------


def test_manual_entry_keeps_what_the_user_gave_and_nothing_else(api_env: ApiEnv) -> None:
    saved = _save(api_env, name="Mein Lokal", lat=48.21, lon=16.37)
    assert saved["kind"] == "restaurant" and saved["name"] == "Mein Lokal"
    assert "cuisines" not in saved and "meal_types" not in saved  # nothing Photon cannot give
    found = _search(api_env, q="Mein Lokal").json()
    assert [p["name"] for p in found["your_places"]] == ["Mein Lokal"]
    cafe = _save(api_env, kind="cafe", name="Mein Café", lat=48.21, lon=16.37)
    assert cafe["kind"] == "cafe"
    assert [p["name"] for p in _search(api_env, q="Mein Caf").json()["your_places"]] == [
        "Mein Café"
    ]


def test_a_restaurant_is_not_added_through_a_recalculation(api_env: ApiEnv) -> None:
    """ADR 026: the user chooses a restaurant's day and time; the slot engine is gone."""
    plan = _plan(api_env)
    saved = _save(api_env, name="Mein Lokal", lat=48.21, lon=16.37)
    r = _preview(
        api_env, plan["id"], action="add_place", user_place_id=saved["id"], duration_minutes=60
    )
    assert r.status_code == 422 and r.json()["code"] == "wrong_place_kind"
    gone = api_env.client.post(
        f"/v1/itineraries/{plan['id']}/restaurant-suggestions",
        json={"user_place_id": saved["id"]},
        headers=api_env.headers,
    )
    assert gone.status_code in (404, 405)
    assert (
        _preview(
            api_env, plan["id"], action="add_restaurant", user_place_id=saved["id"]
        ).status_code
        == 422
    )


def _feature(name: str, venue: str, osm_id: int) -> dict[str, Any]:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [TESTBURG[1], TESTBURG[0]]},
        "properties": {
            "name": name,
            "osm_key": "amenity",
            "osm_value": venue,
            "osm_type": "N",
            "osm_id": osm_id,
            "countrycode": "AT",
        },
    }


def _use_photon_payload(env: ApiEnv, payload: dict[str, Any]) -> None:
    """Make the stub answer with this payload (the conftest stub reads a fixed file; the adapter
    caches by question, so a new question goes through ``photon_mode``)."""
    env.photon_mode["mode"] = "payload"
    env.photon_mode["payload"] = json.dumps(payload)
