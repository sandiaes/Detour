"""Phase 9 journeys on the fixture database (docs/test-plan-phase-9.md).

The single journeys each have their own tests elsewhere; this file chains the manager-first ones
the way the owner uses the app, so a break between two features shows up: journey a (a fresh
empty trip filled by hand: a sight, a town, a pin, a restaurant through Photon and one by hand
with a chosen day and time), e (Optimize, preview, apply, undo), h (export and import), i (mark as
past: the plan is kept) and l (no routing provider: every
travel time is a labelled estimate). Photon is the recorded-format stub of ``conftest``; nothing
calls the network.
"""

import json
from typing import Any

import pytest

from tests.conftest import ApiEnv
from tests.test_api_trips import add_item, find_place, make_itinerary, make_trip
from tests.test_trip_export import _export, _import

pytestmark = pytest.mark.db


def _user_place(env: ApiEnv, **body: Any) -> dict[str, Any]:
    r = env.client.post("/v1/user-places", json=body, headers=env.headers)
    assert r.status_code == 201, r.text
    out: dict[str, Any] = r.json()
    return out


def _plan(env: ApiEnv, plan_id: str) -> dict[str, Any]:
    r = env.client.get(f"/v1/itineraries/{plan_id}", headers=env.headers)
    assert r.status_code == 200, r.text
    out: dict[str, Any] = r.json()
    return out


def _stops(plan: dict[str, Any]) -> list[tuple[int, str, str, int]]:
    return [
        (d["day_index"], i["display_name"], (i["start_time"] or "")[:5], i["duration_minutes"])
        for d in plan["days"]
        for i in d["items"]
    ]


def test_a_fresh_trip_is_filled_optimized_exported_imported_and_kept_as_history(
    api_env: ApiEnv,
) -> None:
    c, h = api_env.client, api_env.headers

    # -- a. a fresh, empty trip ------------------------------------------------------------------
    trip = make_trip(api_env, title="Testburg", duration_days=2, start_date="2027-05-01")
    plan = make_itinerary(api_env, trip)  # the empty, hand-made plan
    assert plan["profile"] == "manual" and all(d["items"] == [] for d in plan["days"])
    c.patch(f"/v1/trips/{trip['id']}", json={"selected_itinerary_id": plan["id"]}, headers=h)

    # A sight from the imported data.
    museum = find_place(api_env, "testburg museum")
    r = add_item(api_env, plan, 1, type="visit", place_id=museum["id"], start_time="09:30")
    assert r.status_code == 201, r.text
    # A town, found in the gazetteer and saved as the user's own place of kind city.
    (town,) = c.get("/v1/destinations/search", params={"q": "ostertal"}, headers=h).json()[
        "results"
    ]
    saved_town = _user_place(
        api_env,
        kind="city",
        name=town["name"],
        lat=town["lat"],
        lon=town["lon"],
        source="search_result",
        search_provider="geonames",
        search_ref=str(town["ref"]),
    )
    r = add_item(
        api_env,
        plan,
        2,
        type="visit",
        user_place_id=saved_town["id"],
        start_time="10:00",
        duration_minutes=120,  # the app's default for a town
    )
    assert r.status_code == 201, r.text
    # A dropped pin.
    pin = _user_place(
        api_env, kind="location", name="Viewpoint", lat=48.212, lon=16.372, source="manual_pin"
    )
    r = add_item(
        api_env,
        plan,
        1,
        type="visit",
        user_place_id=pin["id"],
        start_time="11:00",
        duration_minutes=30,
    )
    assert r.status_code == 201, r.text
    # A restaurant through Photon (the backend asks; the app never does).
    api_env.photon_mode["mode"] = "payload"
    api_env.photon_mode["payload"] = json.dumps(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [16.371, 48.209]},
                    "properties": {
                        "name": "Gasthaus Journey",
                        "osm_key": "amenity",
                        "osm_value": "restaurant",
                        "osm_type": "N",
                        "osm_id": 777,
                        "countrycode": "AT",
                    },
                }
            ],
        }
    )
    found = c.get(
        "/v1/restaurants/search",
        params={"q": "gasthaus journey", "lat": 48.21, "lon": 16.37, "include_external": "true"},
        headers=h,
    ).json()
    (ext,) = found["external"]["results"]
    assert ext["venue_type"] == "restaurant" and "cuisines" not in ext
    lunch = _user_place(
        api_env,
        kind="restaurant",
        name=ext["name"],
        lat=ext["lat"],
        lon=ext["lon"],
        source="search_result",
        search_provider="photon",
        search_ref=ext["ref"],
    )
    r = add_item(api_env, plan, 1, type="meal", user_place_id=lunch["id"], start_time="13:00")
    assert r.status_code == 201, r.text
    assert r.json()["duration_minutes"] == 75  # the default length of a restaurant
    # One by hand, on the day and at the time the user chose.
    cafe = _user_place(
        api_env, kind="cafe", name="Corner Café", lat=48.205, lon=16.375, source="manual_pin"
    )
    r = add_item(api_env, plan, 2, type="meal", user_place_id=cafe["id"], start_time="16:30")
    assert r.status_code == 201, r.text
    assert r.json()["duration_minutes"] == 45

    filled = _plan(api_env, plan["id"])
    assert [(d, n, t) for d, n, t, _ in _stops(filled)] == [
        (1, "Testburg Museum", "09:30"),
        (1, "Viewpoint", "11:00"),
        (1, "Gasthaus Journey", "13:00"),
        (2, town["name"], "10:00"),
        (2, "Corner Café", "16:30"),
    ]
    # No meal type, cuisine or price on any stop (ADR 017, ADR 026).
    text = json.dumps(filled).lower()
    for word in ("cuisine", "meal_type", "price", "currency", "budget"):
        assert word not in text, word

    # -- e. Optimize across days, preview, apply, undo ------------------------------------------
    preview = c.post(
        f"/v1/itineraries/{plan['id']}/optimize", json={"scope": "across_days"}, headers=h
    )
    # The stops are spread over two days on purpose, so a shorter order exists.
    assert preview.status_code == 201, preview.text
    change = preview.json()
    assert _stops(_plan(api_env, plan["id"])) == _stops(filled)  # nothing until applied
    applied = c.post(f"/v1/change-sets/{change['id']}/apply", headers=h)
    assert applied.status_code == 200, applied.text
    after = _plan(api_env, plan["id"])
    assert sorted(n for _, n, _, _ in _stops(after)) == sorted(n for _, n, _, _ in _stops(filled))
    undo = c.post(f"/v1/itineraries/{plan['id']}/optimize/undo", headers=h)
    assert undo.status_code == 201, undo.text
    assert c.post(f"/v1/change-sets/{undo.json()['id']}/apply", headers=h).status_code == 200
    assert _stops(_plan(api_env, plan["id"])) == _stops(filled)

    # -- l. no routing provider: every leg is a labelled estimate -------------------------------
    legs = [i["transfer"] for d in _plan(api_env, plan["id"])["days"] for i in d["items"]]
    assert all(t is None or t["confidence"] == "estimated" for t in legs)

    # -- h. export, then import as a new trip ---------------------------------------------------
    file = _export(api_env, trip)
    assert file["format"] == "detour-trip" and len(file["trips"]) == 1
    imported = _import(api_env, file)
    assert imported.status_code == 201, imported.text
    (new,) = imported.json()["trips"]
    new_id = new["trip_id"]
    new_trip = c.get(f"/v1/trips/{new_id}", headers=h).json()
    assert new_trip["destination"]["kind"] == "place"  # always a hand-made copy (ADR 028)
    copy = _plan(api_env, new_trip["selected_itinerary_id"])
    assert [(d, n, t, m) for d, n, t, m in _stops(copy)] == _stops(_plan(api_env, plan["id"]))
    damaged = _import(api_env, {"format": "detour-trip", "format_version": 1, "trips": "x"})
    assert damaged.status_code == 422

    # -- i. mark as past: the plan is kept and still works ---------------------------------------
    past = c.post(f"/v1/trips/{trip['id']}/archive", headers=h)
    assert past.status_code == 200 and past.json()["status"] == "past"
    assert past.json()["selected_itinerary_id"] == plan["id"]
    assert _stops(_plan(api_env, plan["id"])) == _stops(filled)
    assert c.get(f"/v1/trips/{trip['id']}/visits", headers=h).json() == []
    # A past trip is read-only: Optimize is refused until it is reopened.
    refused = c.post(
        f"/v1/itineraries/{plan['id']}/optimize", json={"scope": "within_days"}, headers=h
    )
    assert refused.status_code == 409 and refused.json()["code"] == "trip_past"
