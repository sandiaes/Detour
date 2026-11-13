"""Adding a restaurant through the API (Phase 8, ADR 019): search (local, then Photon through the
backend, then manual entry), slot suggestions, and placing the restaurant through a change set, on
the imported fixture region with the planner's synthetic sights and places to eat (Testburg). The
routing provider is off in tests, so every new travel time is a labelled estimate; Photon answers
from a recorded-response stub, never the network.
"""

import json
from typing import Any

import httpx
import psycopg
import pytest

from detour_api.planner.config import DEFAULT_CONFIG
from tests.conftest import PHOTON_BUDGET, ApiEnv
from tests.test_api_changes import _apply, _get, _plan, _preview, _state
from tests.test_api_planning import sql

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


def _suggest(env: ApiEnv, itinerary_id: str, **body: Any) -> Any:
    return env.client.post(
        f"/v1/itineraries/{itinerary_id}/restaurant-suggestions", json=body, headers=env.headers
    )


def _place_near(plan: dict[str, Any], day: int = 1) -> tuple[float, float]:
    item = next(i for i in plan["days"][day - 1]["items"] if i["type"] == "visit")
    return item["lat"] + 0.0008, item["lon"]


def _unplanned_restaurant(env: ApiEnv, plan: dict[str, Any]) -> str:
    used = {i["place_id"] for d in plan["days"] for i in d["items"]}
    rows = sql(
        env,
        "SELECT p.id FROM geo.place p JOIN geo.restaurant_profile rp ON rp.place_id = p.id"
        " WHERE p.kind = 'restaurant' AND p.name LIKE %s AND rp.venue_type = 'restaurant'"
        " ORDER BY p.id",
        "Synthetic restaurant%",
    )
    return next(str(r[0]) for r in rows if str(r[0]) not in used)


def _meal(itinerary: dict[str, Any], name: str) -> dict[str, Any]:
    return next(i for d in itinerary["days"] for i in d["items"] if i["display_name"] == name)


# -- search: local data first, then Photon, then manual entry ------------------------------------


def test_local_restaurants_are_searched_first_and_photon_is_not_asked(api_env: ApiEnv) -> None:
    body = _search(api_env, q="alten post", include_external="true").json()
    assert [r["name"] for r in body["results"]] == ["Zur Alten Post"]
    r = body["results"][0]
    assert r["cuisines"] == ["austrian", "regional"] and r["venue_type"] == "restaurant"
    assert r["meal_types"] == ["dinner", "lunch"]
    assert body["external"]["state"] == "not_needed" and api_env.photon_requests == []


def test_a_restaurant_without_cuisine_data_is_returned_as_unknown(api_env: ApiEnv) -> None:
    rows = sql(
        api_env,
        "SELECT p.name FROM geo.place p JOIN geo.restaurant_profile rp ON rp.place_id = p.id"
        " WHERE rp.cuisines IS NULL AND p.name IS NOT NULL LIMIT 1",
    )
    if not rows:
        pytest.skip("the fixture region has no restaurant without cuisine data")
    body = _search(api_env, q=rows[0][0][:8]).json()
    assert any(r["cuisines"] is None for r in body["results"])


def test_nothing_local_asks_photon_for_restaurants_only(api_env: ApiEnv) -> None:
    body = _search(api_env, q="examplestadt", include_external="true", region="test-region").json()
    assert body["results"] == [] and body["your_places"] == []
    (request,) = api_env.photon_requests
    params = httpx.QueryParams(request.url.query)
    assert params.get_list("osm_tag") == ["amenity:restaurant", "amenity:cafe"]
    assert "Detour-backend" in request.headers["user-agent"]
    assert str(api_env.installation_id) not in str(request.url)
    # The recorded answer holds no restaurant: whatever Photon returns, only restaurants and cafés
    # are passed on, even if the server ignored the tag filter.
    assert body["external"]["state"] == "ok" and body["external"]["results"] == []


def test_photon_restaurants_get_meal_types_from_the_venue_rule_and_no_cuisine(
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
    assert found["Gasthaus Beispiel"]["meal_types"] == ["dinner", "lunch"]
    assert found["Café Beispiel"]["meal_types"] == ["breakfast", "snack"]
    assert all(r["cuisines"] is None and r["licence"] == "ODbL-1.0" for r in found.values())
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


def test_manual_entry_without_cuisine_stays_not_specified(api_env: ApiEnv) -> None:
    plan = _plan(api_env)
    lat, lon = _place_near(plan)
    saved = _save(api_env, name="Mein Lokal", lat=lat, lon=lon)
    assert saved["cuisines"] is None and saved["meal_types"] is None
    preview = _preview_best(api_env, plan["id"], user_place_id=saved["id"])
    assert preview.status_code == 201, preview.text
    applied = _apply(api_env, preview.json()["id"]).json()["itinerary"]
    meal = _meal(applied, "Mein Lokal")
    assert meal["type"] == "meal" and meal["origin"] == "user"
    assert meal["restaurant"]["cuisines"] is None  # the app shows "Cuisine not specified"
    assert meal["restaurant"]["venue_type"] is None
    assert "CUISINE_NOT_SPECIFIED_BY_YOU" in meal["reasons"]
    assert "ADDED_BY_YOU" in meal["reasons"]


def test_typed_coordinates_and_given_cuisines_and_meals_are_kept(api_env: ApiEnv) -> None:
    plan = _plan(api_env)
    lat, lon = _place_near(plan, 2)
    saved = _save(
        api_env,
        name="Trattoria Eingegeben",
        lat=lat,
        lon=lon,
        cuisines=["Italian", "pizza"],
        meal_types=["dinner"],
    )
    assert saved["cuisines"] == ["italian", "pizza"] and saved["meal_types"] == ["dinner"]
    suggested = _suggest(api_env, plan["id"], user_place_id=saved["id"]).json()
    assert suggested["restaurant"]["meal_types"] == ["dinner"]
    assert suggested["restaurant"]["meal_types_basis"] == "you"
    assert {s["meal_type"] for s in suggested["suggestions"]} == {"dinner"}


# -- suggestions -------------------------------------------------------------------------------------


def test_up_to_three_suggestions_with_reasons_detour_and_moved_items(api_env: ApiEnv) -> None:
    plan = _plan(api_env)
    lat, lon = _place_near(plan, 2)
    saved = _save(api_env, name="Nahe Küche", lat=lat, lon=lon, meal_types=["lunch", "dinner"])
    r = _suggest(api_env, plan["id"], user_place_id=saved["id"])
    assert r.status_code == 200, r.text
    body = r.json()
    suggestions = body["suggestions"]
    assert 1 <= len(suggestions) <= 3
    assert [s["rank"] for s in suggestions] == list(range(1, len(suggestions) + 1))
    assert [s["score"] for s in suggestions] == sorted(s["score"] for s in suggestions)
    assert body["restaurant"]["cuisines"] is None and body["issues"] == []
    for s in suggestions:
        assert s["reasons"] and all(x["text"] for x in s["reasons"])
        codes = [x["code"] for x in s["reasons"]]
        assert codes[0] == "SLOT_WINDOW" and "SLOT_TRAVEL" in codes
        assert s["travel_label"] in ("routed", "estimated")
        assert isinstance(s["detour_metres"], int) and isinstance(s["travel_minutes_added"], int)
        assert isinstance(s["items_moved"], list)
        window = {
            "lunch": ("12:00:00", "14:30:00"),
            "dinner": ("18:30:00", "21:00:00"),
        }[s["meal_type"]]
        assert window[0] <= s["start_time"] < s["end_time"] <= window[1]
        assert s["end_time"] <= "21:00:00"
    # Suggestions store nothing.
    assert _get(api_env, plan["id"])["version"] == 1
    assert sql(api_env, "SELECT count(*) FROM app.change_set") == [(0,)]


def test_suggestions_can_be_limited_to_a_day_or_a_meal(api_env: ApiEnv) -> None:
    plan = _plan(api_env)
    lat, lon = _place_near(plan)
    saved = _save(api_env, name="Überall", lat=lat, lon=lon)
    only = _suggest(api_env, plan["id"], user_place_id=saved["id"], day=2, meal_type="dinner")
    assert only.status_code == 200, only.text
    assert [(s["day"], s["meal_type"]) for s in only.json()["suggestions"]] == [(2, "dinner")]
    assert "SLOT_MEAL_UNKNOWN" in [x["code"] for x in only.json()["suggestions"][0]["reasons"]]
    assert _suggest(api_env, plan["id"], user_place_id=saved["id"], day=99).status_code == 422


def test_an_imported_restaurant_is_suggested_with_its_venue_rule(api_env: ApiEnv) -> None:
    plan = _plan(api_env)
    place = _unplanned_restaurant(api_env, plan)
    body = _suggest(api_env, plan["id"], place_id=place).json()
    assert body["restaurant"]["meal_types_basis"] == "venue_type"
    assert body["restaurant"]["venue_type"] == "restaurant"
    assert {s["meal_type"] for s in body["suggestions"]} <= {"lunch", "dinner"}
    assert any(
        x["code"] == "SLOT_SERVES_MEAL_VENUE" for s in body["suggestions"] for x in s["reasons"]
    )


def test_a_restaurant_already_in_the_plan_or_of_the_wrong_kind_is_explained(
    api_env: ApiEnv,
) -> None:
    plan = _plan(api_env)
    planned = next(
        i for d in plan["days"] for i in d["items"] if i["type"] == "meal" and i["place_id"]
    )
    r = _suggest(api_env, plan["id"], place_id=planned["place_id"])
    assert r.status_code == 422 and r.json()["code"] == "recalculation_impossible"
    assert r.json()["issues"][0]["code"] == "ALREADY_IN_PLAN"
    sight = sql(api_env, "SELECT id FROM geo.place WHERE kind = 'attraction' LIMIT 1")[0][0]
    assert _suggest(api_env, plan["id"], place_id=str(sight)).status_code == 422
    pin = _save(api_env, kind="location", name="Not a restaurant", lat=48.2, lon=16.4)
    assert _suggest(api_env, plan["id"], user_place_id=pin["id"]).status_code == 422
    assert _suggest(api_env, plan["id"]).status_code == 422  # neither id
    assert (
        _suggest(
            api_env, plan["id"], place_id=planned["place_id"], user_place_id=pin["id"]
        ).status_code
        == 422
    )


def test_suggestions_need_a_planned_itinerary_of_your_own(api_env: ApiEnv) -> None:
    plan = _plan(api_env)
    saved = _save(api_env, name="X Lokal", lat=48.2, lon=16.4)
    other = api_env.other_installation()
    r = api_env.client.post(
        f"/v1/itineraries/{plan['id']}/restaurant-suggestions",
        json={"user_place_id": saved["id"]},
        headers=other,
    )
    assert r.status_code == 404


# -- placing it ------------------------------------------------------------------------------------


def test_the_chosen_slot_is_previewed_applied_and_validated(api_env: ApiEnv) -> None:
    plan = _plan(api_env, days=3)
    lat, lon = _place_near(plan, 2)
    saved = _save(
        api_env,
        name="Gewählt",
        lat=lat,
        lon=lon,
        cuisines=["greek"],
        meal_types=["lunch", "dinner"],
    )
    old = _state(api_env, plan["id"])
    best = _suggest(api_env, plan["id"], user_place_id=saved["id"]).json()["suggestions"][0]
    r = _preview_restaurant(
        api_env,
        plan["id"],
        saved["id"],
        day=best["day"],
        meal_type=best["meal_type"],
        after_item_id=best["after_item_id"],
    )
    assert r.status_code == 201, r.text
    change = r.json()
    assert change["action"] == "add_restaurant" and change["status"] == "pending"
    assert change["notes"][0]["code"] == "RESTAURANT_ADDED"
    added = [a for a in change["diff"]["added"] if a["kind"] == "meal" and a["added_by_you"]]
    assert len(added) == 1 and added[0]["name"] == "Gewählt"
    assert (added[0]["day"], added[0]["meal_type"]) == (best["day"], best["meal_type"])
    # Visits do not change day and none is left out.
    assert change["diff"]["moved"] == []
    assert not [x for x in change["diff"]["removed"] if x["kind"] == "visit"]
    assert _get(api_env, plan["id"])["version"] == 1  # a preview changes nothing

    applied = _apply(api_env, change["id"])
    assert applied.status_code == 200, applied.text
    itinerary = applied.json()["itinerary"]
    assert itinerary["version"] == 2 and itinerary["engine_version"].endswith("+recalc-1.1.0")
    meal = _meal(itinerary, "Gewählt")
    assert meal["restaurant"]["cuisines"] == ["greek"]
    assert meal["origin"] == "user" and meal["locked"] is False
    window = DEFAULT_CONFIG.meal_window(meal["meal_type"])
    start = int(meal["start_time"][:2]) * 60 + int(meal["start_time"][3:5])
    end = int(meal["end_time"][:2]) * 60 + int(meal["end_time"][3:5])
    assert window.start_minute <= start < end <= window.end_minute
    # The saved plan is exactly what was previewed.
    from detour_api.planner import diff
    from detour_api.repo import changes
    from detour_api.repo.plan_state import to_rplan

    new = _state(api_env, plan["id"])
    again = changes.diff_model(
        diff.compare(to_rplan(old, "essentials"), to_rplan(new, "essentials"))
    )
    assert again.model_dump(mode="json") == change["diff"]
    versions = api_env.client.get(
        f"/v1/itineraries/{plan['id']}/versions", headers=api_env.headers
    ).json()
    assert versions[0]["action"] == "add_restaurant" and versions[0]["target_name"] == "Gewählt"
    # The slot is now taken: the same restaurant is in the plan, another cannot take its slot.
    second = _save(api_env, name="Zweites Lokal", lat=lat, lon=lon, meal_types=[best["meal_type"]])
    again2 = _preview_restaurant(
        api_env, plan["id"], second["id"], day=best["day"], meal_type=best["meal_type"]
    )
    assert again2.status_code == 422
    assert again2.json()["issues"][0]["code"] == "MEAL_SLOT_TAKEN"


def test_an_imported_restaurant_can_be_placed_and_replaces_the_planned_meal(
    api_env: ApiEnv,
) -> None:
    plan = _plan(api_env)
    place = _unplanned_restaurant(api_env, plan)
    best = _suggest(api_env, plan["id"], place_id=place).json()["suggestions"][0]
    r = _preview_restaurant(
        api_env,
        plan["id"],
        None,
        place_id=place,
        day=best["day"],
        meal_type=best["meal_type"],
        after_item_id=best["after_item_id"],
    )
    assert r.status_code == 201, r.text
    change = r.json()
    if best["replaces"] is not None:
        assert any(x["name"] == best["replaces"] for x in change["diff"]["removed"])
        assert "MEAL_REPLACED" in [n["code"] for n in change["notes"]]
    applied = _apply(api_env, change["id"]).json()["itinerary"]
    meal = next(i for d in applied["days"] for i in d["items"] if i["place_id"] == place)
    assert meal["origin"] == "user" and meal["restaurant"]["venue_type"] == "restaurant"
    per_day = [[i["meal_type"] for i in d["items"] if i["type"] == "meal"] for d in applied["days"]]
    assert all(len(m) == len(set(m)) for m in per_day)  # at most one meal of a type a day


def test_a_restaurant_slot_that_does_not_exist_or_does_not_fit_is_refused(api_env: ApiEnv) -> None:
    plan = _plan(api_env)
    lat, lon = _place_near(plan)
    cafe = _save(api_env, name="Nur Frühstück", lat=lat, lon=lon, meal_types=["breakfast", "snack"])
    r = _preview_restaurant(api_env, plan["id"], cafe["id"], day=1, meal_type="dinner")
    assert r.status_code == 422
    assert r.json()["issues"][0]["code"] == "RESTAURANT_DOES_NOT_SERVE_MEAL"
    r = _preview_restaurant(api_env, plan["id"], cafe["id"], day=9, meal_type="snack")
    assert r.status_code == 422 and r.json()["code"] == "day_not_found"
    r = _preview_restaurant(
        api_env,
        plan["id"],
        cafe["id"],
        day=1,
        meal_type="snack",
        after_item_id="00000000-0000-4000-8000-000000000000",
    )
    assert r.status_code == 422 and r.json()["issues"][0]["code"] == "SLOT_NOT_FOUND"
    # A visit cannot be added as a restaurant, and a restaurant cannot be added as a visit.
    sight = sql(api_env, "SELECT id FROM geo.place WHERE kind = 'attraction' LIMIT 1")[0][0]
    assert (
        _preview_restaurant(
            api_env, plan["id"], None, place_id=str(sight), day=1, meal_type="lunch"
        ).status_code
        == 422
    )
    wrong = _preview(
        api_env, plan["id"], action="add_place", user_place_id=cafe["id"], duration_minutes=30
    )
    assert wrong.status_code == 422


def test_the_request_shape_is_validated(api_env: ApiEnv) -> None:
    plan = _plan(api_env)
    saved = _save(api_env, name="Form Prüfung", lat=48.2, lon=16.4)
    base = {"action": "add_restaurant", "user_place_id": saved["id"]}
    for extra in (
        {},  # no day or meal
        {"day": 1},
        {"meal_type": "lunch"},
        {"day": 1, "meal_type": "lunch", "duration_minutes": 30},
        {"day": 1, "meal_type": "brunch"},
    ):
        r = api_env.client.post(
            f"/v1/itineraries/{plan['id']}/change-sets",
            json={**base, **extra},
            headers=api_env.headers,
        )
        assert r.status_code == 422, extra
    r = _preview(api_env, plan["id"], action="add_place", user_place_id=saved["id"], day=1)
    assert r.status_code == 422


def test_a_hand_edit_after_the_preview_expires_it(api_env: ApiEnv) -> None:
    plan = _plan(api_env)
    lat, lon = _place_near(plan)
    saved = _save(api_env, name="Veraltet", lat=lat, lon=lon, meal_types=["lunch"])
    change = _preview_best(api_env, plan["id"], user_place_id=saved["id"]).json()
    item = next(i for i in plan["days"][0]["items"] if i["type"] == "visit")
    r = api_env.client.patch(
        f"/v1/items/{item['id']}", json={"locked": True}, headers=api_env.headers
    )
    assert r.status_code == 200, r.text
    stale = _apply(api_env, change["id"])
    assert stale.status_code == 409 and stale.json()["code"] == "change_set_stale"


# -- helpers -------------------------------------------------------------------------------------


def _preview_restaurant(
    env: ApiEnv,
    itinerary_id: str,
    user_place_id: str | None,
    *,
    place_id: str | None = None,
    day: int | None = None,
    meal_type: str = "lunch",
    after_item_id: str | None = None,
) -> Any:
    body: dict[str, Any] = {
        "action": "add_restaurant",
        "day": 1 if day is None else day,
        "meal_type": meal_type,
        "after_item_id": after_item_id,
    }
    if user_place_id is not None:
        body["user_place_id"] = user_place_id
    if place_id is not None:
        body["place_id"] = place_id
    return env.client.post(
        f"/v1/itineraries/{itinerary_id}/change-sets", json=body, headers=env.headers
    )


def _preview_best(env: ApiEnv, itinerary_id: str, **ids: str) -> Any:
    """Preview the best slot the suggestions name, as the app does."""
    got = _suggest(env, itinerary_id, **ids)
    assert got.status_code == 200, got.text
    best = got.json()["suggestions"][0]
    return _preview_restaurant(
        env,
        itinerary_id,
        ids.get("user_place_id"),
        place_id=ids.get("place_id"),
        day=best["day"],
        meal_type=best["meal_type"],
        after_item_id=best["after_item_id"],
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
