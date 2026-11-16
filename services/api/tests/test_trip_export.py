"""Trip export and import as a file (ADR 028): the file shape, the round trip for every kind of
trip, imports that are always new copies, and files that are refused without writing anything."""

import json
from typing import Any

import pytest

from tests.conftest import ApiEnv
from tests.test_api_planning import add_synthetic_sights, generate, make_trip, sql
from tests.test_api_trips import add_item, make_itinerary
from tests.test_past_trips import _archive, _visits
from tests.test_place_destinations import PHOTON

pytestmark = pytest.mark.db


def _place_trip(env: ApiEnv, **over: Any) -> dict[str, Any]:
    body = {"title": "Hallstatt", "duration_days": 2, **PHOTON, **over}
    r = env.client.post("/v1/trips", json=body, headers=env.headers)
    assert r.status_code == 201, r.text
    trip: dict[str, Any] = r.json()
    return trip


def _own_place(env: ApiEnv, kind: str, name: str, lat: float, lon: float) -> str:
    r = env.client.post(
        "/v1/user-places",
        json={"kind": kind, "name": name, "lat": lat, "lon": lon, "source": "manual_pin"},
        headers=env.headers,
    )
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


def _export(env: ApiEnv, trip: dict[str, Any] | None = None) -> dict[str, Any]:
    url = "/v1/trips/export" if trip is None else f"/v1/trips/{trip['id']}/export"
    r = env.client.get(url, headers=env.headers)
    assert r.status_code == 200, r.text
    body: dict[str, Any] = r.json()
    return body


def _import(env: ApiEnv, file: dict[str, Any]) -> Any:
    return env.client.post("/v1/trips/import", json=file, headers=env.headers)


def _stops(env: ApiEnv, trip_id: str) -> list[list[tuple[Any, ...]]]:
    """Each day's stops of the chosen plan: name, start, minutes, who set the length, locked."""
    trip = env.client.get(f"/v1/trips/{trip_id}", headers=env.headers).json()
    plan = env.client.get(
        f"/v1/itineraries/{trip['selected_itinerary_id']}", headers=env.headers
    ).json()
    return [
        [
            (
                i["display_name"],
                i["start_time"],
                i["duration_minutes"],
                i["duration_source"],
                i["locked"],
            )
            for i in d["items"]
            if i["type"] in ("visit", "meal")
        ]
        for d in plan["days"]
    ]


def test_a_hand_made_trip_survives_the_round_trip(api_env: ApiEnv) -> None:
    trip = _place_trip(api_env, start_date="2027-06-01")
    plan = make_itinerary(api_env, trip)
    api_env.client.patch(
        f"/v1/trips/{trip['id']}",
        json={"selected_itinerary_id": plan["id"]},
        headers=api_env.headers,
    )
    church = _own_place(api_env, "location", "Lutheran church", 47.5621, 13.6489)
    cafe = _own_place(api_env, "cafe", "Seecafe", 47.5619, 13.6495)
    add_item(
        api_env,
        plan,
        1,
        type="visit",
        user_place_id=church,
        start_time="09:30:00",
        duration_minutes=50,
    )
    add_item(api_env, plan, 1, type="meal", user_place_id=cafe, start_time="11:00:00", locked=True)
    add_item(api_env, plan, 2, type="visit", user_place_id=church, duration_minutes=20)
    before = _stops(api_env, trip["id"])

    file = _export(api_env, trip)
    assert file["format"] == "detour-trip" and file["format_version"] == 2
    assert [len(d["items"]) for d in file["trips"][0]["days"]] == [2, 1]

    r = _import(api_env, file)
    assert r.status_code == 201, r.text
    made = r.json()["trips"][0]
    assert made["trip_id"] != trip["id"] and made["stops"] == 3 and made["days"] == 2
    assert _stops(api_env, made["trip_id"]) == before
    copy = api_env.client.get(f"/v1/trips/{made['trip_id']}", headers=api_env.headers).json()
    assert copy["title"] == "Hallstatt" and copy["start_date"] == "2027-06-01"
    assert copy["destination"] == trip["destination"]
    assert copy["selected_itinerary_id"] is not None


def test_a_planned_trip_imports_as_a_manual_plan_of_the_users_own_places(api_env: ApiEnv) -> None:
    add_synthetic_sights(api_env)
    trip = make_trip(api_env, duration_days=2)
    plans = generate(api_env, trip).json()["itineraries"]
    api_env.client.patch(
        f"/v1/trips/{trip['id']}",
        json={"selected_itinerary_id": plans[0]["id"]},
        headers=api_env.headers,
    )
    before = _stops(api_env, trip["id"])
    file = _export(api_env, trip)
    # A city of the gazetteer carries its GeoNames id as a reference; nothing else of ours leaves.
    assert file["trips"][0]["destination"]["ref"] == "geonames:900101"
    text = json.dumps(file)
    assert "place_id" not in text and "itinerary" not in text and "installation" not in text

    made = _import(api_env, file).json()["trips"][0]
    copy = api_env.client.get(f"/v1/trips/{made['trip_id']}", headers=api_env.headers).json()
    assert copy["destination"]["kind"] == "place"
    assert copy["destination"]["ref"] == "geonames:900101"
    plan = api_env.client.get(
        f"/v1/itineraries/{copy['selected_itinerary_id']}", headers=api_env.headers
    ).json()
    assert plan["profile"] == "manual"
    items = [i for d in plan["days"] for i in d["items"]]
    assert items and all(i["place_id"] is None and i["user_place_id"] for i in items)
    # Stops and times are those of the original; free time, if any, is derived by the app.
    assert [[s[0] for s in day] for day in _stops(api_env, made["trip_id"])] == [
        [s[0] for s in day] for day in before
    ]
    assert [[s[1:3] for s in day] for day in _stops(api_env, made["trip_id"])] == [
        [s[1:3] for s in day] for day in before
    ]


def test_a_past_trip_comes_back_as_past_with_its_plan(api_env: ApiEnv) -> None:
    trip = _place_trip(api_env)
    plan = make_itinerary(api_env, trip)
    api_env.client.patch(
        f"/v1/trips/{trip['id']}",
        json={"selected_itinerary_id": plan["id"]},
        headers=api_env.headers,
    )
    spot = _own_place(api_env, "location", "Salt mine", 47.5598, 13.6401)
    add_item(
        api_env,
        plan,
        1,
        type="visit",
        user_place_id=spot,
        start_time="10:00:00",
        duration_minutes=90,
    )
    _archive(api_env, trip)

    file = _export(api_env, trip)
    exported = file["trips"][0]
    assert exported["status"] == "past" and exported["visits"] == []
    assert [i["name"] for d in exported["days"] for i in d["items"]] == ["Salt mine"]
    made = _import(api_env, file).json()["trips"][0]
    copy = api_env.client.get(f"/v1/trips/{made['trip_id']}", headers=api_env.headers).json()
    assert copy["status"] == "past" and copy["archived_at"] is not None
    assert copy["selected_itinerary_id"] is not None
    assert _visits(api_env, copy) == []


def test_a_past_trip_of_the_older_archive_comes_back_with_its_visits(api_env: ApiEnv) -> None:
    trip = _place_trip(api_env)
    _archive(api_env, trip)
    sql(
        api_env,
        "INSERT INTO app.trip_visit (id, trip_id, kind, name, point, day_number, position,"
        " start_time, duration_minutes) VALUES (gen_random_uuid(), %s, 'attraction', 'Salt mine',"
        " ST_SetSRID(ST_MakePoint(13.6401, 47.5598), 4326), 1, 1, '10:00', 90)",
        trip["id"],
    )
    visits = _visits(api_env, trip)
    api_env.client.patch(
        f"/v1/trips/{trip['id']}/visits/{visits[-1]['id']}",
        json={"confirmed": False},
        headers=api_env.headers,
    )

    file = _export(api_env, trip)
    assert file["trips"][0]["status"] == "past" and file["trips"][0]["days"] == []
    made = _import(api_env, file).json()["trips"][0]
    copy = api_env.client.get(f"/v1/trips/{made['trip_id']}", headers=api_env.headers).json()
    assert copy["status"] == "past" and copy["archived_at"] is not None
    key = ("kind", "name", "day_number", "start_time", "duration_minutes", "confirmed")
    assert [tuple(v[k] for k in key) for v in _visits(api_env, copy)] == [
        tuple(v[k] for k in key) for v in _visits(api_env, trip)
    ]


def test_a_multi_city_trip_keeps_its_cities_in_the_file_and_imports_as_a_place(
    api_env: ApiEnv,
) -> None:
    trip = _place_trip(api_env)
    file = _export(api_env, trip)
    file["trips"][0]["destination"]["kind"] = "route"
    file["trips"][0]["stops"] = [
        {"name": "Hallstatt", "lat": 47.56, "lon": 13.64, "days": 1},
        {"name": "Bad Ischl", "lat": 47.71, "lon": 13.62, "days": 1},
    ]
    made = _import(api_env, file).json()["trips"][0]
    copy = api_env.client.get(f"/v1/trips/{made['trip_id']}", headers=api_env.headers).json()
    assert copy["destination"]["kind"] == "place" and copy["stops"] == []


def test_the_backup_has_every_trip_and_an_import_is_always_a_new_copy(api_env: ApiEnv) -> None:
    one = _place_trip(api_env, title="One")
    two = _place_trip(api_env, title="Two", destination_ref="manual")
    file = _export(api_env)
    assert [t["title"] for t in file["trips"]] == ["One", "Two"]  # oldest first
    assert file["trips"][1]["destination"]["ref"] == "manual"
    r = _import(api_env, file)
    assert r.status_code == 201 and len(r.json()["trips"]) == 2
    again = _import(api_env, file)
    assert again.status_code == 201
    listed = api_env.client.get("/v1/trips", headers=api_env.headers).json()
    assert len(listed) == 6 and {one["id"], two["id"]} <= {t["id"] for t in listed}
    assert sorted(t["title"] for t in listed) == ["One"] * 3 + ["Two"] * 3
    assert len({t["id"] for t in listed}) == 6


def test_a_trip_can_be_exported_only_by_its_owner(api_env: ApiEnv) -> None:
    trip = _place_trip(api_env)
    r = api_env.client.get(f"/v1/trips/{trip['id']}/export", headers=api_env.other_installation())
    assert r.status_code == 404
    other = api_env.client.get("/v1/trips/export", headers=api_env.other_installation())
    assert other.status_code == 200 and other.json()["trips"] == []


def test_a_file_from_a_newer_version_is_refused(api_env: ApiEnv) -> None:
    file = _export(api_env)
    file["format_version"] = 3
    r = _import(api_env, file)
    assert r.status_code == 422 and r.json()["code"] == "format_too_new"


def test_a_bad_file_writes_nothing(api_env: ApiEnv) -> None:
    _place_trip(api_env)
    good = _export(api_env)["trips"][0]
    bad_day = {**good, "title": "Bad", "days": [{"day_index": 9, "items": []}]}
    wrong_status = {**good, "title": "Worse", "visits": [good_visit()]}
    for trips in ([good, bad_day], [good, wrong_status]):
        r = _import(api_env, {"format": "detour-trip", "format_version": 1, "trips": trips})
        assert r.status_code == 422, r.text
    bad_point = {**good, "destination": {**good["destination"], "lat": 123}}
    for body in (
        {"format": "detour-trip", "format_version": 1, "trips": [good, bad_point]},
        {"format": "something-else", "format_version": 1, "trips": [good]},
        {"format_version": 1, "trips": [good], "surprise": True},
    ):
        assert _import(api_env, body).status_code == 422
    assert len(api_env.client.get("/v1/trips", headers=api_env.headers).json()) == 1


def good_visit() -> dict[str, Any]:
    return {"kind": "attraction", "name": "X", "lat": 1, "lon": 1, "day_number": 1}


def test_overlapping_stops_in_a_file_are_refused_and_nothing_is_written(api_env: ApiEnv) -> None:
    good = _export(api_env, _place_trip(api_env))["trips"][0]
    item = {"position": 1, "kind": "place", "name": "A", "lat": 1, "lon": 1, "duration_minutes": 60}
    day = {
        "day_index": 1,
        "items": [
            {**item, "start_time": "10:00:00"},
            {**item, "position": 2, "start_time": "10:30:00"},
        ],
    }
    r = _import(api_env, {"format_version": 1, "trips": [{**good, "days": [day]}]})
    assert r.status_code == 409  # the plan's own overlap rule; the whole file rolls back
    assert len(api_env.client.get("/v1/trips", headers=api_env.headers).json()) == 1


# -- version 2: transport legs, stays and Car (ADR 032) -------------------------------------------


def _chosen(api_env: ApiEnv, trip: dict[str, Any]) -> dict[str, Any]:
    plan = make_itinerary(api_env, trip)
    api_env.client.patch(
        f"/v1/trips/{trip['id']}",
        json={"selected_itinerary_id": plan["id"]},
        headers=api_env.headers,
    )
    return plan


def _plan_of(api_env: ApiEnv, trip_id: str) -> dict[str, Any]:
    trip = api_env.client.get(f"/v1/trips/{trip_id}", headers=api_env.headers).json()
    got: dict[str, Any] = api_env.client.get(
        f"/v1/itineraries/{trip['selected_itinerary_id']}", headers=api_env.headers
    ).json()
    return got


def test_legs_stays_and_car_survive_the_round_trip(api_env: ApiEnv) -> None:
    trip = _place_trip(api_env, uses_car=False)
    plan = _chosen(api_env, trip)
    church = _own_place(api_env, "location", "Lutheran church", 47.5621, 13.6489)
    add_item(
        api_env,
        plan,
        1,
        type="visit",
        user_place_id=church,
        start_time="09:30:00",
        duration_minutes=50,
    )
    train = {
        "mode": "train",
        "from_name": "Hallstatt",
        "to_name": "Salzburg",
        "to_lat": 47.8,
        "to_lon": 13.04,
        "note": "Change at Attnang",
    }
    assert (
        add_item(
            api_env,
            plan,
            1,
            type="transport",
            transport=train,
            start_time="16:00:00",
            duration_minutes=150,
        ).status_code
        == 201
    )
    journey = {**train, "is_journey": True, "mode": "bus"}
    add_item(
        api_env,
        plan,
        2,
        type="visit",
        user_place_id=church,
        start_time="12:00:00",
        duration_minutes=30,
    )
    add_item(api_env, plan, 2, type="transport", transport=journey, position=2)
    stay = {"name": "Gasthof", "lat": 47.56, "lon": 13.65, "first_day": 1, "last_day": 2}
    assert (
        api_env.client.post(
            f"/v1/trips/{trip['id']}/stays", json=stay, headers=api_env.headers
        ).status_code
        == 201
    )

    file = _export(api_env, trip)
    exported = file["trips"][0]
    assert exported["uses_car"] is False and exported["stays"][0]["name"] == "Gasthof"
    legs = [i for d in exported["days"] for i in d["items"] if i["kind"] == "transport"]
    assert len(legs) == 2 and legs[0]["lat"] is None and legs[1]["duration_minutes"] is None

    r = _import(api_env, file)
    assert r.status_code == 201, r.text
    made = r.json()["trips"][0]
    copy = api_env.client.get(f"/v1/trips/{made['trip_id']}", headers=api_env.headers).json()
    assert copy["uses_car"] is False
    got_stays = api_env.client.get(
        f"/v1/trips/{made['trip_id']}/stays", headers=api_env.headers
    ).json()
    assert [(s["name"], s["first_day"], s["last_day"]) for s in got_stays] == [("Gasthof", 1, 2)]
    days = _plan_of(api_env, made["trip_id"])["days"]
    day1 = [(i["type"], i["display_name"], i["start_time"]) for i in days[0]["items"]]
    assert day1 == [
        ("visit", "Lutheran church", "09:30:00"),
        ("transport", "Train to Salzburg", "16:00:00"),
    ]
    assert days[0]["items"][1]["transport"]["note"] == "Change at Attnang"
    day2 = [(i["type"], i["duration_minutes"]) for i in days[1]["items"]]
    assert day2 == [("visit", 30), ("transport", None)]  # the file's order, length unknown
    assert days[1]["items"][1]["transport"]["is_journey"] is True


def test_a_version_1_file_still_imports_with_a_car_and_no_stays(api_env: ApiEnv) -> None:
    trip = _place_trip(api_env, uses_car=False)
    file = _export(api_env, trip)
    file["format_version"] = 1
    for t in file["trips"]:
        t.pop("stays")
        t.pop("uses_car")
    r = _import(api_env, file)
    assert r.status_code == 201, r.text
    made = r.json()["trips"][0]
    copy = api_env.client.get(f"/v1/trips/{made['trip_id']}", headers=api_env.headers).json()
    assert copy["uses_car"] is True


def test_a_leg_in_a_file_needs_its_details_and_a_stop_needs_its_point(api_env: ApiEnv) -> None:
    trip = _place_trip(api_env)
    good = _export(api_env, trip)["trips"][0]
    leg_without = {"position": 1, "kind": "transport", "name": "Train"}
    stop_without = {"position": 1, "kind": "place", "name": "Somewhere", "duration_minutes": 30}
    for item in (leg_without, stop_without):
        day = {"day_index": 1, "items": [item]}
        r = _import(api_env, {"format_version": 2, "trips": [{**good, "days": [day]}]})
        assert r.status_code == 422, r.text
    bad_stay = {"name": "Inn", "lat": 47.5, "lon": 13.6, "first_day": 1, "last_day": 9}
    r = _import(api_env, {"format_version": 2, "trips": [{**good, "stays": [bad_stay]}]})
    assert r.status_code == 422 and r.json()["code"] == "bad_file"
