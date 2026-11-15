"""Optimize a hand-made trip through the API (ADR 029): both scopes, restaurants, stops that stay,
the saving, apply and undo, and the refusals. Travel times are labelled estimates here: the test
database has no routing provider."""

from typing import Any

import pytest

from tests.conftest import ApiEnv
from tests.test_api_trips import add_item, make_itinerary
from tests.test_place_destinations import PHOTON

pytestmark = pytest.mark.db

STEP = 0.03  # about 3.3 km of latitude: every leg is driven, so travel grows with distance


def _own_place(env: ApiEnv, kind: str, name: str, lat: float, lon: float) -> str:
    r = env.client.post(
        "/v1/user-places",
        json={"kind": kind, "name": name, "lat": lat, "lon": lon, "source": "manual_pin"},
        headers=env.headers,
    )
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


def _trip(env: ApiEnv, days: int = 2, **over: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    body = {"title": "Hallstatt", "duration_days": days, **PHOTON, **over}
    r = env.client.post("/v1/trips", json=body, headers=env.headers)
    assert r.status_code == 201, r.text
    trip = r.json()
    plan = make_itinerary(env, trip)
    env.client.patch(
        f"/v1/trips/{trip['id']}",
        json={"selected_itinerary_id": plan["id"]},
        headers=env.headers,
    )
    return trip, plan


def _visit(
    env: ApiEnv,
    plan: dict[str, Any],
    day: int,
    name: str,
    x: float,
    start: str,
    minutes: int = 45,
    **extra: Any,
) -> str:
    kind = extra.pop("kind", "location")
    place = _own_place(env, kind, name, 47.50 + x * STEP, 13.65)
    r = add_item(
        env,
        plan,
        day,
        type="meal" if kind in ("restaurant", "cafe") else "visit",
        user_place_id=place,
        start_time=start,
        duration_minutes=minutes,
        **extra,
    )
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


def _days(env: ApiEnv, plan: dict[str, Any]) -> list[list[tuple[str, str]]]:
    got = env.client.get(f"/v1/itineraries/{plan['id']}", headers=env.headers).json()
    return [[(i["display_name"], i["start_time"]) for i in d["items"]] for d in got["days"]]


def _names(env: ApiEnv, plan: dict[str, Any]) -> list[list[str]]:
    return [[n for n, _ in d] for d in _days(env, plan)]


def _optimize(env: ApiEnv, plan: dict[str, Any], scope: str, **body: Any) -> Any:
    return env.client.post(
        f"/v1/itineraries/{plan['id']}/optimize",
        json={"scope": scope, **body},
        headers=env.headers,
    )


def _zigzag(env: ApiEnv, plan: dict[str, Any], day: int = 1) -> None:
    for i, x in enumerate([0, 6, 1, 7, 2]):
        _visit(env, plan, day, f"Stop {x}", x, f"{9 + i:02d}:00:00")


def test_a_zigzag_day_is_reordered_and_nothing_changes_before_apply(api_env: ApiEnv) -> None:
    _, plan = _trip(api_env)
    _zigzag(api_env, plan)
    before = _days(api_env, plan)
    r = _optimize(api_env, plan, "within_days")
    assert r.status_code == 201, r.text
    change = r.json()
    assert change["action"] == "optimize" and change["status"] == "pending"
    assert change["diff"]["travel_minutes_added"] < 0
    assert change["diff"]["days_changed"] == [1]
    codes = [n["code"] for n in change["notes"]]
    assert (
        "OPTIMIZED" in codes and "OPTIMIZE_NOT_SHORTEST" in codes and "OPTIMIZE_NO_HOURS" in codes
    )
    assert _days(api_env, plan) == before  # a preview changes nothing


def test_applying_gives_a_new_version_with_every_stop_and_undo_restores_the_order(
    api_env: ApiEnv,
) -> None:
    _, plan = _trip(api_env)
    _zigzag(api_env, plan)
    before = _names(api_env, plan)
    version = api_env.client.get(f"/v1/itineraries/{plan['id']}", headers=api_env.headers).json()[
        "version"
    ]
    change = _optimize(api_env, plan, "within_days").json()
    applied = api_env.client.post(f"/v1/change-sets/{change['id']}/apply", headers=api_env.headers)
    assert applied.status_code == 200, applied.text
    after = _names(api_env, plan)
    assert sorted(after[0]) == sorted(before[0]) and after[0] != before[0]
    assert applied.json()["itinerary"]["version"] == version + 1

    undo = api_env.client.post(
        f"/v1/itineraries/{plan['id']}/optimize/undo", headers=api_env.headers
    )
    assert undo.status_code == 201, undo.text
    assert undo.json()["restores_version"] == version
    api_env.client.post(f"/v1/change-sets/{undo.json()['id']}/apply", headers=api_env.headers)
    assert _names(api_env, plan) == before
    # The undo is not itself offered again as something to undo.
    again = api_env.client.post(
        f"/v1/itineraries/{plan['id']}/optimize/undo", headers=api_env.headers
    )
    assert again.status_code == 409 and again.json()["code"] == "nothing_to_undo"


def test_there_is_nothing_to_undo_after_another_change(api_env: ApiEnv) -> None:
    _, plan = _trip(api_env)
    _zigzag(api_env, plan)
    change = _optimize(api_env, plan, "within_days").json()
    api_env.client.post(f"/v1/change-sets/{change['id']}/apply", headers=api_env.headers)
    _visit(api_env, plan, 2, "Another", 3, "10:00:00")
    r = api_env.client.post(f"/v1/itineraries/{plan['id']}/optimize/undo", headers=api_env.headers)
    assert r.status_code == 409 and r.json()["code"] == "nothing_to_undo"


def test_the_second_scope_moves_a_visit_to_the_day_it_belongs_with(api_env: ApiEnv) -> None:
    _, plan = _trip(api_env)
    _visit(api_env, plan, 1, "North A", 20, "09:00:00")
    _visit(api_env, plan, 1, "South A", 0, "10:30:00")
    _visit(api_env, plan, 1, "South B", 1, "12:00:00")
    _visit(api_env, plan, 2, "North B", 21, "09:00:00")
    _visit(api_env, plan, 2, "South C", 2, "10:30:00")
    _visit(api_env, plan, 2, "North C", 22, "12:00:00")
    within = _optimize(api_env, plan, "within_days")
    across = _optimize(api_env, plan, "across_days")
    assert across.status_code == 201, across.text
    assert across.json()["diff"]["moved"], "a visit should change day"
    assert across.json()["diff"]["travel_minutes_added"] < 0
    if within.status_code == 201:  # within each day nothing may change day
        assert within.json()["diff"]["moved"] == []
    api_env.client.post(f"/v1/change-sets/{across.json()['id']}/apply", headers=api_env.headers)
    days = _names(api_env, plan)
    assert sorted(days[0] + days[1]) == sorted(
        ["North A", "South A", "South B", "North B", "South C", "North C"]
    )
    assert days[0] and days[1]  # a day never ends up empty


def test_a_restaurant_keeps_its_day_and_stays_near_its_time(api_env: ApiEnv) -> None:
    _, plan = _trip(api_env)
    _visit(api_env, plan, 1, "Far", 8, "09:00:00", 30)
    _visit(api_env, plan, 1, "Near", 1, "10:00:00", 30)
    _visit(api_env, plan, 1, "Lunch", 2, "12:30:00", 60, kind="restaurant")
    _visit(api_env, plan, 1, "Farther", 9, "14:00:00", 30)
    _visit(api_env, plan, 1, "Nearer", 0, "15:00:00", 30)
    r = _optimize(api_env, plan, "across_days")
    if r.status_code == 201:
        api_env.client.post(f"/v1/change-sets/{r.json()['id']}/apply", headers=api_env.headers)
    day1 = dict(_days(api_env, plan)[0])
    assert "Lunch" in day1
    hour, minute = (int(p) for p in day1["Lunch"].split(":")[:2])
    assert 12 * 60 + 30 <= hour * 60 + minute <= 13 * 60 + 30


def test_locked_and_kept_stops_do_not_move(api_env: ApiEnv) -> None:
    _, plan = _trip(api_env)
    _visit(api_env, plan, 1, "Locked", 6, "09:00:00", locked=True)
    kept = _visit(api_env, plan, 1, "Ticketed", 7, "10:30:00")
    _visit(api_env, plan, 1, "Mid", 1, "12:00:00")
    _visit(api_env, plan, 1, "Near", 0, "13:30:00")
    _visit(api_env, plan, 1, "Next", 2, "15:00:00")
    before = dict(_days(api_env, plan)[0])
    r = _optimize(api_env, plan, "within_days", fixed_item_ids=[kept])
    if r.status_code == 201:
        api_env.client.post(f"/v1/change-sets/{r.json()['id']}/apply", headers=api_env.headers)
    after = dict(_days(api_env, plan)[0])
    assert after["Locked"] == before["Locked"] and after["Ticketed"] == before["Ticketed"]


def test_a_plan_that_is_already_short_gets_no_proposal(api_env: ApiEnv) -> None:
    _, plan = _trip(api_env)
    for i in range(4):
        _visit(api_env, plan, 1, f"In order {i}", i, f"{9 + i:02d}:00:00")
    r = _optimize(api_env, plan, "across_days")
    assert r.status_code == 409 and r.json()["code"] == "no_better_order"


def test_refusals(api_env: ApiEnv) -> None:
    _, plan = _trip(api_env)
    _visit(api_env, plan, 1, "A", 0, "09:00:00")
    _visit(api_env, plan, 1, "B", 1, "10:00:00")
    few = _optimize(api_env, plan, "within_days")
    assert few.status_code == 422 and few.json()["code"] == "not_enough_stops"
    _visit(api_env, plan, 1, "C", 2, "11:00:00")
    unknown = _optimize(
        api_env, plan, "within_days", fixed_item_ids=["00000000-0000-4000-8000-000000000000"]
    )
    assert unknown.status_code == 422 and unknown.json()["code"] == "unknown_items"
    missing = api_env.client.post(
        "/v1/itineraries/00000000-0000-4000-8000-000000000000/optimize",
        json={"scope": "within_days"},
        headers=api_env.headers,
    )
    assert missing.status_code == 404
    bad = api_env.client.post(
        f"/v1/itineraries/{plan['id']}/optimize",
        json={"scope": "everywhere"},
        headers=api_env.headers,
    )
    assert bad.status_code == 422


def test_a_far_stop_on_a_place_trip_keeps_its_day(api_env: ApiEnv) -> None:
    _, plan = _trip(api_env)
    far = _own_place(api_env, "location", "Day trip", 48.2, 13.65)  # about 80 km away
    add_item(
        api_env,
        plan,
        1,
        type="visit",
        user_place_id=far,
        start_time="09:00:00",
        duration_minutes=60,
    )
    _visit(api_env, plan, 2, "Local A", 0, "09:00:00")
    _visit(api_env, plan, 2, "Local B", 6, "10:00:00")
    _visit(api_env, plan, 2, "Local C", 1, "11:00:00")
    _visit(api_env, plan, 1, "Local D", 7, "12:00:00")
    r = _optimize(api_env, plan, "across_days")
    assert r.status_code == 201, r.text
    assert "OPTIMIZE_FAR_KEPT" in [n["code"] for n in r.json()["notes"]]
    api_env.client.post(f"/v1/change-sets/{r.json()['id']}/apply", headers=api_env.headers)
    assert "Day trip" in _names(api_env, plan)[0]
