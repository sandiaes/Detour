"""Multi-city trips through the API (ADR 024), on the imported fixture region (Testburg, Austria)
with the planner's synthetic sights. A city in Japan (Kōnan) is in the gazetteer but its region is
not imported, so it is refused.
"""

from typing import Any

import psycopg
import pytest

from detour_api.naming import route_name
from tests.conftest import ApiEnv
from tests.planner_helpers import insert_synthetic_sights

pytestmark = pytest.mark.db

TESTBURG, MUEHLBACH, ALPENAU, KONAN = 900101, 900103, 900105, 900201


def route(env: ApiEnv, stops: list[tuple[int, int]], **over: Any) -> Any:
    body = {
        "title": "ignored",
        "destination_kind": "route",
        "stops": [{"city_id": c, "days": d} for c, d in stops],
        "duration_days": sum(d for _, d in stops),
        **over,
    }
    return env.client.post("/v1/trips", json=body, headers=env.headers)


def code(r: Any) -> str:
    return str(r.json().get("code"))


def test_a_route_is_created_with_its_stops_and_named_after_them(api_env: ApiEnv) -> None:
    r = route(api_env, [(TESTBURG, 2), (ALPENAU, 1)], start_date="2027-05-01")
    assert r.status_code == 201, r.text
    trip = r.json()
    assert trip["title"] == "Testburg to Alpenau"
    assert trip["destination"]["kind"] == "route"
    assert trip["destination"]["ref"] == str(TESTBURG)
    assert [(s["position"], s["city_id"], s["days"]) for s in trip["stops"]] == [
        (1, TESTBURG, 2),
        (2, ALPENAU, 1),
    ]
    assert trip["stops"][0]["country_iso2"] == "AT"
    listed = api_env.client.get("/v1/trips", headers=api_env.headers).json()
    assert listed[0]["stops"] == trip["stops"]
    three = route(api_env, [(TESTBURG, 1), (ALPENAU, 1), (MUEHLBACH, 1)]).json()
    assert three["title"] == "Multi-city Testland"  # the fixture's name for AT


@pytest.mark.parametrize(
    ("stops", "over", "status", "expected"),
    [
        ([(TESTBURG, 2)], {}, 422, "route_needs_two_stops"),
        ([(TESTBURG, 1), (ALPENAU, 1)] * 4, {}, 422, "too_many_stops"),
        ([(TESTBURG, 2), (ALPENAU, 1)], {"duration_days": 4}, 422, "stop_days_mismatch"),
        ([(TESTBURG, 1), (TESTBURG, 1)], {}, 422, "stop_repeated"),
        ([(TESTBURG, 1), (123, 1)], {}, 422, "destination_not_found"),
        ([(TESTBURG, 1), (KONAN, 1)], {}, 409, "region_not_available"),
    ],
)
def test_bad_stops_are_refused_with_a_reason(
    api_env: ApiEnv,
    stops: list[tuple[int, int]],
    over: dict[str, Any],
    status: int,
    expected: str,
) -> None:
    r = route(api_env, stops, **over)
    assert r.status_code == status, r.text
    assert code(r) == expected


def test_a_city_may_come_back_later(api_env: ApiEnv) -> None:
    r = route(api_env, [(TESTBURG, 1), (ALPENAU, 1), (TESTBURG, 1)])
    assert r.status_code == 201, r.text


def test_stops_and_destination_ref_do_not_mix(api_env: ApiEnv) -> None:
    r = route(api_env, [(TESTBURG, 1), (ALPENAU, 1)], destination_ref=str(TESTBURG))
    assert r.status_code == 422
    city = api_env.client.post(
        "/v1/trips",
        json={
            "title": "x",
            "destination_kind": "city",
            "destination_ref": str(TESTBURG),
            "stops": [{"city_id": TESTBURG, "days": 1}],
            "duration_days": 1,
        },
        headers=api_env.headers,
    )
    assert city.status_code == 422


def test_a_route_is_planned_per_stop_in_the_users_order(api_env: ApiEnv) -> None:
    insert_synthetic_sights(api_env.database_url)
    trip = route(api_env, [(ALPENAU, 1), (TESTBURG, 2)], start_date="2027-05-01").json()
    r = api_env.client.post(f"/v1/trips/{trip['id']}/itineraries/generate", headers=api_env.headers)
    assert r.status_code == 201, r.text
    for itinerary in r.json()["itineraries"]:
        days = itinerary["days"]
        assert [d["base_city_id"] for d in days] == [ALPENAU, TESTBURG, TESTBURG]
        assert days[0]["arrival"] is None
        assert days[1]["arrival"]["mode"] in ("walk", "drive")
        assert days[1]["arrival"]["seconds"] is not None
    with psycopg.connect(api_env.database_url, autocommit=True) as conn:
        versions = conn.execute(
            "SELECT DISTINCT stops_version FROM app.itinerary WHERE trip_id = %s", (trip["id"],)
        ).fetchall()
    assert versions == [(0,)]


def test_a_leg_with_no_time_is_stored_and_read_as_unknown(api_env: ApiEnv) -> None:
    insert_synthetic_sights(api_env.database_url)
    trip = route(api_env, [(TESTBURG, 1), (ALPENAU, 1)]).json()
    # Pretend the second stop is in a country travelled by rail (the fixture has no such region).
    with psycopg.connect(api_env.database_url, autocommit=True) as conn:
        conn.execute(
            "UPDATE app.trip_stop SET country_iso2 = 'JP' WHERE trip_id = %s AND position = 2",
            (trip["id"],),
        )
    r = api_env.client.post(f"/v1/trips/{trip['id']}/itineraries/generate", headers=api_env.headers)
    assert r.status_code == 201, r.text
    day = r.json()["itineraries"][0]["days"][1]
    assert day["arrival"]["mode"] == "unknown" and day["arrival"]["confidence"] == "unknown"
    assert day["arrival"]["seconds"] is None and day["arrival"]["meters"] is None
    notes = [n["code"] for n in r.json()["itineraries"][0]["notes"]]
    assert "ARRIVAL_TIME_UNKNOWN" in notes


def test_route_names_follow_the_fixed_table() -> None:
    names = {"JP": "Japan", "AT": "Austria", "CZ": "Czechia", "FR": "France", "TH": "Thailand"}
    assert route_name(["Tokyo", "Osaka"], ["JP", "JP"], names) == "Tokyo to Osaka"
    assert route_name(["Tokyo", "Kyoto", "Osaka"], ["JP"] * 3, names) == "Multi-city Japan"
    assert (
        route_name(["Vienna", "Prague", "Salzburg"], ["AT", "CZ", "AT"], names)
        == "Multi-city Central Europe"
    )
    assert route_name(["Vienna", "Paris", "Prague"], ["AT", "FR", "CZ"], names) == (
        "Multi-city Europe"
    )
    assert route_name(["Vienna", "Tokyo", "Bangkok"], ["AT", "JP", "TH"], names) == (
        "Multi-city trip"
    )
    assert route_name(["A", "B", "C"], ["AT", None, "AT"], names) == "Multi-city trip"
    assert route_name(["A", "B", "C"], ["ZZ"] * 3, names) == "Multi-city trip"
