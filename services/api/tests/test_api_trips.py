"""Trips, user places, itineraries and items: validation rules, ownership, lifecycle."""

import uuid
from typing import Any

import psycopg
import pytest
from httpx import Response

from tests.conftest import ApiEnv

pytestmark = pytest.mark.db

CITY = {"destination_kind": "city", "destination_ref": "900101"}  # Testburg, in AT -> EUR


def trip_body(**over: Any) -> dict[str, Any]:
    return {"title": "Weekend", **CITY, "duration_days": 3, **over}


def make_trip(env: ApiEnv, **over: Any) -> dict[str, Any]:
    r = env.client.post("/v1/trips", json=trip_body(**over), headers=env.headers)
    assert r.status_code == 201, r.text
    body: dict[str, Any] = r.json()
    return body


def find_place(env: ApiEnv, q: str, **params: str) -> dict[str, Any]:
    r = env.client.get("/v1/places/search", params={"q": q, **params}, headers=env.headers)
    first: dict[str, Any] = r.json()["results"][0]
    return first


def make_itinerary(env: ApiEnv, trip: dict[str, Any]) -> dict[str, Any]:
    r = env.client.post(f"/v1/trips/{trip['id']}/itineraries", headers=env.headers)
    assert r.status_code == 201, r.text
    body: dict[str, Any] = r.json()
    return body


def add_item(env: ApiEnv, itinerary: dict[str, Any], day: int, **body: Any) -> Response:
    response: Response = env.client.post(
        f"/v1/itineraries/{itinerary['id']}/days/{day}/items", json=body, headers=env.headers
    )
    return response


def code(response: Response) -> str:
    return str(response.json().get("code"))


def sql(env: ApiEnv, query: str, *params: Any) -> list[tuple[Any, ...]]:
    with psycopg.connect(env.database_url, autocommit=True) as conn:
        cur = conn.execute(query, params)
        return cur.fetchall() if cur.description else []


# -- trips ---------------------------------------------------------------------------------


def test_create_trip_computes_the_end_date_and_has_no_money_fields(api_env: ApiEnv) -> None:
    trip = make_trip(api_env, start_date="2027-05-01")
    assert trip["end_date"] == "2027-05-03" and trip["status"] == "active"
    # ADR 017: no currency, meal budget or price bands.
    assert not {"currency_code", "meal_budget_per_person", "price_band_thresholds"} & set(trip)
    assert trip["destination"] == {
        "kind": "city",
        "ref": "900101",
        "name": "Testburg",
        "lat": pytest.approx(48.2082),
        "lon": pytest.approx(16.3738),
    }
    assert trip["is_seed"] is False
    assert sql(api_env, "SELECT count(*) FROM app.installation") == [(1,)]  # created on first use


def test_an_area_can_be_a_destination(api_env: ApiEnv) -> None:
    area = api_env.client.get(
        "/v1/destinations/search", params={"q": "testland"}, headers=api_env.headers
    ).json()["results"][0]
    trip = make_trip(api_env, destination_kind="area", destination_ref=area["ref"])
    assert trip["destination"]["kind"] == "area" and trip["destination"]["name"] == "Testland"


@pytest.mark.parametrize(
    ("over", "status", "expected_code"),
    [
        ({"destination_ref": "999999"}, 422, "destination_not_found"),
        ({"destination_ref": "not-a-number"}, 422, "destination_not_found"),
        ({"destination_kind": "area", "destination_ref": "nope"}, 422, "destination_not_found"),
        ({"destination_ref": "900201"}, 409, "region_not_available"),  # Japan: not imported
        ({"currency_code": "EUR"}, 422, "None"),  # ADR 017: no currencies
        ({"duration_days": 0}, 422, "None"),
        ({"duration_days": 31}, 422, "None"),
        ({"title": ""}, 422, "None"),
        ({"title": "x" * 121}, 422, "None"),
        ({"meal_budget_per_person": "25"}, 422, "None"),  # ADR 017: no budgets
        ({"price_band_thresholds": ["10", "20", "30"]}, 422, "None"),
        ({"start_date": "tomorrow"}, 422, "None"),
        ({"surprise": 1}, 422, "None"),
    ],
)
def test_trip_validation(
    api_env: ApiEnv, over: dict[str, Any], status: int, expected_code: str
) -> None:
    r = api_env.client.post("/v1/trips", json=trip_body(**over), headers=api_env.headers)
    assert r.status_code == status, r.text
    if expected_code != "None":
        assert code(r) == expected_code
    assert sql(api_env, "SELECT count(*) FROM app.trip") == [(0,)]


def test_a_destination_in_a_disabled_region_cannot_be_planned(api_env: ApiEnv) -> None:
    sql(api_env, "UPDATE geo.region SET status = 'disabled'")
    r = api_env.client.post("/v1/trips", json=trip_body(), headers=api_env.headers)
    assert r.status_code == 409 and code(r) == "region_not_available"


def test_trips_need_a_token_and_belong_to_one_installation(api_env: ApiEnv) -> None:
    assert api_env.client.post("/v1/trips", json=trip_body()).status_code == 401
    trip = make_trip(api_env)
    other = api_env.other_installation()
    c = api_env.client
    assert c.get("/v1/trips", headers=other).json() == []
    assert c.get(f"/v1/trips/{trip['id']}", headers=other).status_code == 404
    assert c.patch(f"/v1/trips/{trip['id']}", json={"title": "x"}, headers=other).status_code == 404
    assert c.delete(f"/v1/trips/{trip['id']}", headers=other).status_code == 404
    assert c.post(f"/v1/trips/{trip['id']}/archive", headers=other).status_code == 404
    assert c.post(f"/v1/trips/{trip['id']}/itineraries", headers=other).status_code == 404
    assert c.get(f"/v1/trips/{trip['id']}", headers=api_env.headers).status_code == 200
    random_id = uuid.uuid4()
    assert c.get(f"/v1/trips/{random_id}", headers=api_env.headers).status_code == 404


def test_update_changes_only_the_fields_sent_and_null_clears(api_env: ApiEnv) -> None:
    trip = make_trip(api_env, start_date="2027-05-01")
    c, h, url = api_env.client, api_env.headers, f"/v1/trips/{trip['id']}"
    r = c.patch(url, json={"title": "Renamed"}, headers=h).json()
    assert r["title"] == "Renamed" and r["start_date"] == "2027-05-01"
    r = c.patch(url, json={"start_date": None}, headers=h).json()
    assert r["start_date"] is None and r["end_date"] is None
    assert c.patch(url, json={"title": None}, headers=h).status_code == 422
    assert c.patch(url, json={"meal_budget_per_person": "9"}, headers=h).status_code == 422
    assert c.patch(url, json={"destination_ref": "1"}, headers=h).status_code == 422


def test_days_cannot_change_once_there_are_itineraries(api_env: ApiEnv) -> None:
    trip = make_trip(api_env)
    url = f"/v1/trips/{trip['id']}"
    assert (
        api_env.client.patch(url, json={"duration_days": 5}, headers=api_env.headers).status_code
        == 200
    )
    make_itinerary(api_env, trip)
    r = api_env.client.patch(url, json={"duration_days": 2}, headers=api_env.headers)
    assert r.status_code == 409 and code(r) == "has_itineraries"
    same = api_env.client.patch(url, json={"duration_days": 5}, headers=api_env.headers)
    assert same.status_code == 200


def test_changing_the_start_date_re_dates_the_days(api_env: ApiEnv) -> None:
    trip = make_trip(api_env, start_date="2027-05-01")
    it = make_itinerary(api_env, trip)
    assert [d["date"] for d in it["days"]] == ["2027-05-01", "2027-05-02", "2027-05-03"]
    api_env.client.patch(
        f"/v1/trips/{trip['id']}", json={"start_date": "2027-06-10"}, headers=api_env.headers
    )
    again = api_env.client.get(f"/v1/itineraries/{it['id']}", headers=api_env.headers).json()
    assert [d["date"] for d in again["days"]] == ["2027-06-10", "2027-06-11", "2027-06-12"]


def test_selecting_an_itinerary_is_validated_and_exclusive(api_env: ApiEnv) -> None:
    a, b = make_trip(api_env), make_trip(api_env, title="Other")
    ia, ia2, ib = make_itinerary(api_env, a), make_itinerary(api_env, a), make_itinerary(api_env, b)
    c, h = api_env.client, api_env.headers
    bad = c.patch(f"/v1/trips/{a['id']}", json={"selected_itinerary_id": ib["id"]}, headers=h)
    assert bad.status_code == 422 and code(bad) == "itinerary_not_in_trip"
    c.patch(f"/v1/trips/{a['id']}", json={"selected_itinerary_id": ia["id"]}, headers=h)
    c.patch(f"/v1/trips/{a['id']}", json={"selected_itinerary_id": ia2["id"]}, headers=h)
    statuses = {
        i["id"]: i["status"] for i in c.get(f"/v1/trips/{a['id']}/itineraries", headers=h).json()
    }
    assert statuses == {ia["id"]: "proposed", ia2["id"]: "selected"}
    cleared = c.patch(
        f"/v1/trips/{a['id']}", json={"selected_itinerary_id": None}, headers=h
    ).json()
    assert cleared["selected_itinerary_id"] is None


def test_the_number_of_trips_and_itineraries_is_bounded(api_env: ApiEnv) -> None:
    trip = make_trip(api_env)
    for _ in range(4):
        make_itinerary(api_env, trip)
    r = api_env.client.post(f"/v1/trips/{trip['id']}/itineraries", headers=api_env.headers)
    assert r.status_code == 201
    r = api_env.client.post(f"/v1/trips/{trip['id']}/itineraries", headers=api_env.headers)
    assert r.status_code == 409 and code(r) == "limit_reached"


def test_deleting_a_trip_removes_its_plans_but_not_the_users_places_or_prices(
    api_env: ApiEnv,
) -> None:
    trip = make_trip(api_env)
    it = make_itinerary(api_env, trip)
    place = api_env.client.post(
        "/v1/user-places",
        json={
            "kind": "restaurant",
            "name": "Mine",
            "lat": 48.2,
            "lon": 16.3,
            "source": "manual_pin",
        },
        headers=api_env.headers,
    ).json()
    item = add_item(
        api_env,
        it,
        1,
        type="meal",
        meal_type="lunch",
        user_place_id=place["id"],
        duration_minutes=60,
    ).json()
    assert item["restaurant"] == {"venue_type": None, "cuisines": None}  # a user place
    assert (
        api_env.client.delete(f"/v1/trips/{trip['id']}", headers=api_env.headers).status_code == 204
    )
    for table in ("trip", "itinerary", "itinerary_day", "itinerary_item"):
        assert sql(api_env, f"SELECT count(*) FROM app.{table}") == [(0,)]  # noqa: S608
    assert sql(api_env, "SELECT count(*) FROM app.user_place") == [(1,)]


# -- user places ---------------------------------------------------------------------------

PIN = {"kind": "location", "name": "Viewpoint", "lat": 48.21, "lon": 16.37, "source": "manual_pin"}


def create_place(env: ApiEnv, **over: Any) -> dict[str, Any]:
    r = env.client.post("/v1/user-places", json={**PIN, **over}, headers=env.headers)
    assert r.status_code == 201, r.text
    body: dict[str, Any] = r.json()
    return body


def test_user_place_crud(api_env: ApiEnv) -> None:
    c, h = api_env.client, api_env.headers
    pin = create_place(api_env)
    assert (
        pin["cuisines"] is None and pin["source"] == "manual_pin" and pin["search_provider"] is None
    )
    resto = create_place(
        api_env,
        kind="restaurant",
        name="Noodle Bar",
        cuisines=["Ramen ", "noodle bar", "ramen"],
        meal_types=["Lunch", "dinner"],
        source="search_result",
        search_provider="photon",
        search_ref="N123",
    )
    assert resto["cuisines"] == ["noodle_bar", "ramen"] and resto["meal_types"] == [
        "dinner",
        "lunch",
    ]
    assert [p["id"] for p in c.get("/v1/user-places", headers=h).json()] == [pin["id"], resto["id"]]
    assert [p["id"] for p in c.get("/v1/user-places?kind=restaurant", headers=h).json()] == [
        resto["id"]
    ]
    renamed = c.patch(
        f"/v1/user-places/{pin['id']}", json={"name": "Better", "lat": 48.0, "lon": 16.0}, headers=h
    )
    assert renamed.json()["name"] == "Better" and renamed.json()["lat"] == 48.0
    assert c.delete(f"/v1/user-places/{pin['id']}", headers=h).status_code == 204
    assert c.get(f"/v1/user-places/{pin['id']}", headers=h).status_code == 404


@pytest.mark.parametrize(
    "over",
    [
        {"cuisines": ["ramen"]},  # not a restaurant
        {"kind": "restaurant", "meal_types": ["brunch"]},
        {"kind": "restaurant", "cuisines": ["no/slash"]},
        {"source": "search_result"},  # needs provider and ref
        {"source": "search_result", "search_provider": "photon"},
        {"search_provider": "photon", "search_ref": "N1"},  # a pin has no provider
        {"source": "search_result", "search_provider": "nominatim", "search_ref": "1"},
        {"lat": 91},
        {"lon": -181},
        {"name": ""},
        {"name": "x" * 201},
        {"kind": "hotel"},
        {"unknown_field": 1},
    ],
)
def test_user_place_validation(api_env: ApiEnv, over: dict[str, Any]) -> None:
    r = api_env.client.post("/v1/user-places", json={**PIN, **over}, headers=api_env.headers)
    assert r.status_code == 422, r.text
    assert sql(api_env, "SELECT count(*) FROM app.user_place") == [(0,)]


def test_user_places_are_private(api_env: ApiEnv) -> None:
    pin = create_place(api_env)
    other = api_env.other_installation()
    assert api_env.client.get("/v1/user-places", headers=other).json() == []
    assert api_env.client.get(f"/v1/user-places/{pin['id']}", headers=other).status_code == 404
    assert api_env.client.delete(f"/v1/user-places/{pin['id']}", headers=other).status_code == 404
    patch = api_env.client.patch(f"/v1/user-places/{pin['id']}", json={"name": "x"}, headers=other)
    assert patch.status_code == 404
    assert api_env.client.post("/v1/user-places", json=PIN).status_code == 401


def test_a_place_used_by_an_item_cannot_be_deleted_and_renames_flow_to_the_item(
    api_env: ApiEnv,
) -> None:
    trip, pin = make_trip(api_env), create_place(api_env)
    it = make_itinerary(api_env, trip)
    item = add_item(
        api_env, it, 1, type="visit", user_place_id=pin["id"], duration_minutes=30
    ).json()
    r = api_env.client.delete(f"/v1/user-places/{pin['id']}", headers=api_env.headers)
    assert r.status_code == 409 and code(r) == "in_use"
    api_env.client.patch(
        f"/v1/user-places/{pin['id']}", json={"name": "Renamed"}, headers=api_env.headers
    )
    assert (
        api_env.client.get(f"/v1/items/{item['id']}", headers=api_env.headers).json()[
            "display_name"
        ]
        == "Renamed"
    )
    api_env.client.delete(f"/v1/items/{item['id']}", headers=api_env.headers)
    assert (
        api_env.client.delete(f"/v1/user-places/{pin['id']}", headers=api_env.headers).status_code
        == 204
    )


# -- items ---------------------------------------------------------------------------------


def test_the_manual_itinerary_has_one_empty_day_per_trip_day(api_env: ApiEnv) -> None:
    it = make_itinerary(api_env, make_trip(api_env, duration_days=4))
    assert [d["day_index"] for d in it["days"]] == [1, 2, 3, 4]
    assert all(d["items"] == [] for d in it["days"])
    assert (it["profile"], it["engine_version"], it["version"], it["import_run_id"]) == (
        "manual",
        "manual",
        1,
        None,
    )


def test_visit_with_an_imported_place_snapshots_name_and_point(api_env: ApiEnv) -> None:
    it = make_itinerary(api_env, make_trip(api_env))
    museum = find_place(api_env, "testburg museum")
    r = add_item(
        api_env,
        it,
        1,
        type="visit",
        place_id=museum["id"],
        duration_minutes=90,
        start_time="10:00:00",
    )
    assert r.status_code == 201, r.text
    item = r.json()
    assert (item["display_name"], item["position"], item["origin"]) == (
        "Testburg Museum",
        1,
        "user",
    )
    assert (item["duration_source"], item["end_time"], item["locked"]) == (
        "user",
        "11:30:00",
        False,
    )
    assert item["lat"] == pytest.approx(48.2082) and item["reasons"] == []
    fetched = api_env.client.get(f"/v1/itineraries/{it['id']}", headers=api_env.headers).json()
    assert fetched["version"] == 2 and fetched["days"][0]["items"][0]["id"] == item["id"]


def test_an_attraction_without_a_duration_gets_its_category_default(api_env: ApiEnv) -> None:
    # Phase 4: the category rule table (planner/durations.py) gives every attraction a default.
    it = make_itinerary(api_env, make_trip(api_env))
    museum = find_place(api_env, "testburg museum")
    item = add_item(api_env, it, 1, type="visit", place_id=museum["id"]).json()
    assert (item["duration_minutes"], item["duration_source"]) == (90, "category_default")


def test_a_meal_still_needs_a_duration(api_env: ApiEnv) -> None:
    it = make_itinerary(api_env, make_trip(api_env))
    restaurant = find_place(api_env, "alten post")
    r = add_item(api_env, it, 1, type="meal", meal_type="lunch", place_id=restaurant["id"])
    assert r.status_code == 422 and code(r) == "duration_required"


def test_a_known_category_default_is_used_and_labelled(api_env: ApiEnv) -> None:
    it = make_itinerary(api_env, make_trip(api_env))
    museum = find_place(api_env, "testburg museum")
    sql(api_env, "UPDATE geo.place SET default_visit_minutes = 75 WHERE id = %s", museum["id"])
    item = add_item(api_env, it, 1, type="visit", place_id=museum["id"]).json()
    assert (item["duration_minutes"], item["duration_source"]) == (75, "category_default")


@pytest.mark.parametrize(
    ("body", "expected_code"),
    [
        ({"type": "visit"}, "None"),  # no place
        ({"type": "meal", "meal_type": "lunch"}, "None"),
        ({"type": "meal", "place_id": "RESTAURANT"}, "None"),  # no meal_type
        ({"type": "visit", "place_id": "MUSEUM", "meal_type": "lunch"}, "None"),
        ({"type": "free_time", "place_id": "MUSEUM"}, "None"),
        ({"type": "visit", "place_id": "MUSEUM", "user_place_id": "PIN"}, "None"),
        ({"type": "visit", "place_id": "RESTAURANT"}, "wrong_place_kind"),
        ({"type": "meal", "meal_type": "lunch", "place_id": "MUSEUM"}, "wrong_place_kind"),
        ({"type": "meal", "meal_type": "lunch", "user_place_id": "PIN"}, "wrong_place_kind"),
        ({"type": "visit", "place_id": "00000000-0000-0000-0000-000000000000"}, "place_not_found"),
        (
            {"type": "visit", "user_place_id": "00000000-0000-0000-0000-000000000000"},
            "user_place_not_found",
        ),
        ({"type": "visit", "place_id": "MUSEUM", "start_time": "23:30:00"}, "crosses_midnight"),
        ({"type": "visit", "place_id": "MUSEUM", "position": 5}, "bad_position"),
        ({"type": "visit", "place_id": "MUSEUM", "duration_minutes": 0}, "None"),
        ({"type": "visit", "place_id": "MUSEUM", "duration_minutes": 1441}, "None"),
        ({"type": "visit", "place_id": "MUSEUM", "start_time": "10:00:00+02:00"}, "None"),
        ({"type": "visit", "place_id": "MUSEUM", "unknown": 1}, "None"),
    ],
)
def test_item_validation(api_env: ApiEnv, body: dict[str, Any], expected_code: str) -> None:
    it = make_itinerary(api_env, make_trip(api_env))
    ids = {
        "MUSEUM": find_place(api_env, "testburg museum")["id"],
        "RESTAURANT": find_place(api_env, "alten post")["id"],
        "PIN": create_place(api_env)["id"],
    }
    body = {k: ids.get(v, v) if isinstance(v, str) else v for k, v in body.items()}
    body.setdefault("duration_minutes", 60)
    r = add_item(api_env, it, 1, **body)
    assert r.status_code == 422, r.text
    if expected_code != "None":
        assert code(r) == expected_code
    assert sql(api_env, "SELECT count(*) FROM app.itinerary_item") == [(0,)]


def test_a_meal_needs_a_restaurant_and_free_time_needs_none(api_env: ApiEnv) -> None:
    it = make_itinerary(api_env, make_trip(api_env))
    post = find_place(api_env, "alten post")
    meal = add_item(
        api_env, it, 1, type="meal", meal_type="dinner", place_id=post["id"], duration_minutes=90
    )
    assert meal.status_code == 201 and meal.json()["meal_type"] == "dinner"
    free = add_item(api_env, it, 1, type="free_time", duration_minutes=45)
    assert free.status_code == 201
    assert (free.json()["display_name"], free.json()["lat"]) == ("Free time", None)


def test_items_of_other_installations_and_bad_days_are_not_found(api_env: ApiEnv) -> None:
    it = make_itinerary(api_env, make_trip(api_env))
    museum = find_place(api_env, "testburg museum")
    body = {"type": "visit", "place_id": museum["id"], "duration_minutes": 30}
    other = api_env.other_installation()
    path = f"/v1/itineraries/{it['id']}/days/1/items"
    assert api_env.client.post(path, json=body, headers=other).status_code == 404
    assert add_item(api_env, it, 9, **body).status_code == 404
    mine = add_item(api_env, it, 1, **body).json()
    for method in ("get", "patch", "delete"):
        r = getattr(api_env.client, method)(
            f"/v1/items/{mine['id']}",
            headers=other,
            **({"json": {"locked": True}} if method == "patch" else {}),
        )
        assert r.status_code == 404
    assert api_env.client.get(f"/v1/itineraries/{it['id']}", headers=other).status_code == 404
    assert api_env.client.delete(f"/v1/itineraries/{it['id']}", headers=other).status_code == 404


def test_an_inactive_place_cannot_be_added(api_env: ApiEnv) -> None:
    it = make_itinerary(api_env, make_trip(api_env))
    museum = find_place(api_env, "testburg museum")
    sql(api_env, "UPDATE geo.place SET is_active = false WHERE id = %s", museum["id"])
    r = add_item(api_env, it, 1, type="visit", place_id=museum["id"], duration_minutes=30)
    assert r.status_code == 422 and code(r) == "place_not_found"


def positions(env: ApiEnv, it: dict[str, Any], day: int) -> list[str]:
    body = env.client.get(f"/v1/itineraries/{it['id']}", headers=env.headers).json()
    return [i["display_name"] for i in body["days"][day - 1]["items"]]


def test_positions_stay_dense_on_insert_move_and_delete(api_env: ApiEnv) -> None:
    it = make_itinerary(api_env, make_trip(api_env))
    pins = {n: create_place(api_env, name=n)["id"] for n in "ABCD"}
    ids = {}
    for n in "ABC":
        ids[n] = add_item(
            api_env, it, 1, type="visit", user_place_id=pins[n], duration_minutes=10
        ).json()["id"]
    assert positions(api_env, it, 1) == ["A", "B", "C"]
    ids["D"] = add_item(
        api_env, it, 1, type="visit", user_place_id=pins["D"], duration_minutes=10, position=1
    ).json()["id"]
    assert positions(api_env, it, 1) == ["D", "A", "B", "C"]
    c, h = api_env.client, api_env.headers
    c.patch(f"/v1/items/{ids['D']}", json={"position": 3}, headers=h)
    assert positions(api_env, it, 1) == ["A", "B", "D", "C"]
    c.patch(f"/v1/items/{ids['C']}", json={"position": 1}, headers=h)
    assert positions(api_env, it, 1) == ["C", "A", "B", "D"]
    c.patch(f"/v1/items/{ids['A']}", json={"day_index": 2}, headers=h)
    assert positions(api_env, it, 1) == ["C", "B", "D"] and positions(api_env, it, 2) == ["A"]
    c.patch(f"/v1/items/{ids['B']}", json={"day_index": 2, "position": 1}, headers=h)
    assert positions(api_env, it, 2) == ["B", "A"]
    c.delete(f"/v1/items/{ids['C']}", headers=h)
    assert positions(api_env, it, 1) == ["D"]
    rows = sql(
        api_env,
        "SELECT d.day_index, i.position FROM app.itinerary_item i JOIN app.itinerary_day d ON d.id = i.day_id ORDER BY 1, 2",
    )
    assert rows == [(1, 1), (2, 1), (2, 2)]
    bad = c.patch(f"/v1/items/{ids['D']}", json={"position": 2}, headers=h)
    assert bad.status_code == 422 and code(bad) == "bad_position"
    assert c.patch(f"/v1/items/{ids['D']}", json={"day_index": 9}, headers=h).status_code == 422


def test_every_accepted_edit_bumps_the_itinerary_version(api_env: ApiEnv) -> None:
    it = make_itinerary(api_env, make_trip(api_env))
    pin = create_place(api_env)["id"]
    item = add_item(api_env, it, 1, type="visit", user_place_id=pin, duration_minutes=10).json()
    api_env.client.patch(f"/v1/items/{item['id']}", json={"locked": True}, headers=api_env.headers)
    api_env.client.delete(f"/v1/items/{item['id']}", headers=api_env.headers)
    v = api_env.client.get(f"/v1/itineraries/{it['id']}", headers=api_env.headers).json()["version"]
    assert v == 4
    rejected = add_item(api_env, it, 1, type="visit", user_place_id=pin)  # 422: no change
    assert rejected.status_code == 422
    assert (
        api_env.client.get(f"/v1/itineraries/{it['id']}", headers=api_env.headers).json()["version"]
        == 4
    )


def test_timed_items_may_touch_but_not_overlap(api_env: ApiEnv) -> None:
    it = make_itinerary(api_env, make_trip(api_env))
    pins = [create_place(api_env, name=f"P{i}")["id"] for i in range(3)]
    first = add_item(
        api_env,
        it,
        1,
        type="visit",
        user_place_id=pins[0],
        duration_minutes=60,
        start_time="10:00:00",
    )
    assert first.status_code == 201
    touching = add_item(
        api_env,
        it,
        1,
        type="visit",
        user_place_id=pins[1],
        duration_minutes=30,
        start_time="11:00:00",
    )
    assert touching.status_code == 201  # starts exactly when the first ends
    clash = add_item(
        api_env,
        it,
        1,
        type="visit",
        user_place_id=pins[2],
        duration_minutes=60,
        start_time="10:30:00",
    )
    assert clash.status_code == 409 and code(clash) == "overlap"
    unscheduled = add_item(api_env, it, 1, type="visit", user_place_id=pins[2], duration_minutes=60)
    assert unscheduled.status_code == 201 and unscheduled.json()["start_time"] is None
    # another day is independent
    assert (
        add_item(
            api_env,
            it,
            2,
            type="visit",
            user_place_id=pins[2],
            duration_minutes=60,
            start_time="10:30:00",
        ).status_code
        == 201
    )


def test_patching_time_duration_and_lock(api_env: ApiEnv) -> None:
    it = make_itinerary(api_env, make_trip(api_env))
    pins = [create_place(api_env, name=f"P{i}")["id"] for i in range(2)]
    a = add_item(
        api_env,
        it,
        1,
        type="visit",
        user_place_id=pins[0],
        duration_minutes=60,
        start_time="09:00:00",
    ).json()
    b = add_item(
        api_env,
        it,
        1,
        type="visit",
        user_place_id=pins[1],
        duration_minutes=60,
        start_time="10:00:00",
    ).json()
    c, h = api_env.client, api_env.headers
    r = c.patch(f"/v1/items/{a['id']}", json={"duration_minutes": 90, "locked": True}, headers=h)
    assert r.status_code == 409 and code(r) == "overlap"  # 09:00-10:30 now hits b
    r = c.patch(
        f"/v1/items/{b['id']}", json={"start_time": "10:30:00", "duration_minutes": 15}, headers=h
    ).json()
    assert (r["start_time"], r["end_time"], r["duration_source"]) == (
        "10:30:00",
        "10:45:00",
        "user",
    )
    r = c.patch(
        f"/v1/items/{a['id']}", json={"duration_minutes": 90, "locked": True}, headers=h
    ).json()
    assert (r["end_time"], r["locked"]) == ("10:30:00", True)
    r = c.patch(f"/v1/items/{a['id']}", json={"start_time": None}, headers=h).json()
    assert (r["start_time"], r["end_time"], r["duration_minutes"]) == (
        None,
        None,
        90,
    )  # unscheduled
    assert (
        c.patch(f"/v1/items/{a['id']}", json={"duration_minutes": None}, headers=h).status_code
        == 422
    )
    assert (
        c.patch(f"/v1/items/{a['id']}", json={"meal_type": "lunch"}, headers=h).status_code == 422
    )


def test_deleting_an_itinerary_clears_a_selection(api_env: ApiEnv) -> None:
    trip = make_trip(api_env)
    it = make_itinerary(api_env, trip)
    api_env.client.patch(
        f"/v1/trips/{trip['id']}", json={"selected_itinerary_id": it["id"]}, headers=api_env.headers
    )
    assert (
        api_env.client.delete(f"/v1/itineraries/{it['id']}", headers=api_env.headers).status_code
        == 204
    )
    assert (
        api_env.client.get(f"/v1/trips/{trip['id']}", headers=api_env.headers).json()[
            "selected_itinerary_id"
        ]
        is None
    )


# -- the past-trip archive (ADR 006) -------------------------------------------------------


def test_archiving_keeps_snapshots_and_deletes_the_plans(api_env: ApiEnv) -> None:
    trip = make_trip(api_env, duration_days=2)
    keep, drop = make_itinerary(api_env, trip), make_itinerary(api_env, trip)
    museum, castle = find_place(api_env, "testburg museum"), find_place(api_env, "testburg castle")
    post = find_place(api_env, "alten post")
    city_pin = create_place(api_env, kind="city", name="Pin Town")
    add_item(api_env, keep, 1, type="visit", place_id=museum["id"], duration_minutes=60)
    add_item(
        api_env, keep, 1, type="meal", meal_type="lunch", place_id=post["id"], duration_minutes=60
    )
    add_item(api_env, keep, 2, type="visit", place_id=castle["id"], duration_minutes=60)
    add_item(api_env, keep, 2, type="visit", user_place_id=city_pin["id"], duration_minutes=60)
    add_item(api_env, keep, 2, type="free_time", duration_minutes=30)
    add_item(api_env, drop, 1, type="visit", place_id=museum["id"], duration_minutes=60)
    sql(
        api_env,
        "UPDATE app.itinerary_day SET base_city_id = 900101 WHERE itinerary_id = %s AND day_index = 1",
        keep["id"],
    )
    sql(
        api_env,
        "UPDATE app.itinerary_day SET base_city_id = 900105 WHERE itinerary_id = %s AND day_index = 2",
        keep["id"],
    )
    api_env.client.patch(
        f"/v1/trips/{trip['id']}",
        json={"selected_itinerary_id": keep["id"]},
        headers=api_env.headers,
    )

    r = api_env.client.post(f"/v1/trips/{trip['id']}/archive", headers=api_env.headers)
    assert r.status_code == 200, r.text
    past = r.json()
    assert (
        past["status"] == "past" and past["archived_at"] and past["selected_itinerary_id"] is None
    )

    visits = api_env.client.get(f"/v1/trips/{trip['id']}/visits", headers=api_env.headers).json()
    summary = [(v["day_number"], v["kind"], v["name"]) for v in visits]
    assert summary == [
        (1, "city", "Testburg"),
        (1, "attraction", "Testburg Museum"),
        (2, "city", "Alpenau"),
        (2, "city", "Pin Town"),
        (2, "attraction", "Testburg Castle"),
    ]
    assert all(v["confirmed"] for v in visits)
    assert visits[1]["geo_place_ref"] == museum["id"] and visits[3]["geo_place_ref"] is None
    assert visits[1]["lat"] == pytest.approx(48.2082)  # a snapshot: no routes, no times
    assert "start_time" not in visits[1] and "seconds" not in visits[1]

    for table in ("itinerary", "itinerary_day", "itinerary_item", "transfer"):
        assert sql(api_env, f"SELECT count(*) FROM app.{table}") == [(0,)]  # noqa: S608


def test_a_past_trip_is_read_only_and_archiving_is_one_way(api_env: ApiEnv) -> None:
    trip = make_trip(api_env)
    it = make_itinerary(api_env, trip)
    api_env.client.post(f"/v1/trips/{trip['id']}/archive", headers=api_env.headers)
    c, h = api_env.client, api_env.headers
    assert code(c.post(f"/v1/trips/{trip['id']}/archive", headers=h)) == "already_archived"
    assert (
        code(c.patch(f"/v1/trips/{trip['id']}", json={"title": "x"}, headers=h)) == "trip_archived"
    )
    assert code(c.post(f"/v1/trips/{trip['id']}/itineraries", headers=h)) == "trip_archived"
    assert c.get(f"/v1/itineraries/{it['id']}", headers=h).status_code == 404
    assert [t["id"] for t in c.get("/v1/trips?status=past", headers=h).json()] == [trip["id"]]
    assert c.get("/v1/trips?status=active", headers=h).json() == []
    assert c.delete(f"/v1/trips/{trip['id']}", headers=h).status_code == 204


def test_a_trip_without_a_selected_itinerary_archives_its_destination_city(api_env: ApiEnv) -> None:
    trip = make_trip(api_env)
    api_env.client.post(f"/v1/trips/{trip['id']}/archive", headers=api_env.headers)
    visits = api_env.client.get(f"/v1/trips/{trip['id']}/visits", headers=api_env.headers).json()
    assert [(v["kind"], v["name"], v["day_number"]) for v in visits] == [("city", "Testburg", 1)]


def test_the_user_can_clear_a_visit_that_did_not_happen(api_env: ApiEnv) -> None:
    trip = make_trip(api_env)
    api_env.client.post(f"/v1/trips/{trip['id']}/archive", headers=api_env.headers)
    (visit,) = api_env.client.get(f"/v1/trips/{trip['id']}/visits", headers=api_env.headers).json()
    url = f"/v1/trips/{trip['id']}/visits/{visit['id']}"
    r = api_env.client.patch(url, json={"confirmed": False}, headers=api_env.headers)
    assert r.status_code == 200 and r.json()["confirmed"] is False
    assert (
        api_env.client.patch(
            url, json={"confirmed": False}, headers=api_env.other_installation()
        ).status_code
        == 404
    )
    missing = f"/v1/trips/{trip['id']}/visits/{uuid.uuid4()}"
    assert (
        api_env.client.patch(missing, json={"confirmed": True}, headers=api_env.headers).status_code
        == 404
    )


def test_the_database_unavailable_is_a_503_not_a_crash(api_env: ApiEnv) -> None:
    from fastapi.testclient import TestClient

    from detour_api.main import create_app
    from detour_api.settings import Settings
    from tests.conftest import TEST_SECRET

    no_db = Settings(environment="test", token_secret=TEST_SECRET)
    with TestClient(create_app(no_db)) as client:
        r = client.get("/v1/trips", headers=api_env.headers)
    assert r.status_code == 503 and r.json()["code"] == "database_unavailable"
