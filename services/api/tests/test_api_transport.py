"""Manual transport legs (ADR 032): a leg the user enters by hand, as an item of the plan. Every
value is the user's; a length not entered stays unknown."""

from typing import Any

import pytest

from tests.conftest import ApiEnv
from tests.test_api_optimize import _trip, _visit
from tests.test_api_trips import add_item, code, sql

pytestmark = pytest.mark.db

TRAIN = {
    "mode": "train",
    "from_name": "Rome",
    "from_lat": 41.9,
    "from_lon": 12.5,
    "to_name": "Florence",
    "to_lat": 43.77,
    "to_lon": 11.25,
}


def _leg(env: ApiEnv, plan: dict[str, Any], day: int, **body: Any) -> Any:
    transport = {**TRAIN, **body.pop("transport", {})}
    return add_item(env, plan, day, type="transport", transport=transport, **body)


def _plan(env: ApiEnv, plan: dict[str, Any]) -> dict[str, Any]:
    got: dict[str, Any] = env.client.get(
        f"/v1/itineraries/{plan['id']}", headers=env.headers
    ).json()
    return got


def test_a_leg_is_saved_as_entered_and_is_fixed(api_env: ApiEnv) -> None:
    _, plan = _trip(api_env)
    r = _leg(
        api_env,
        plan,
        1,
        start_time="10:12:00",
        duration_minutes=90,
        transport={"note": "Coach 7"},
    )
    assert r.status_code == 201, r.text
    leg = r.json()
    assert leg["type"] == "transport" and leg["display_name"] == "Train to Florence"
    assert leg["start_time"] == "10:12:00" and leg["end_time"] == "11:42:00"
    assert leg["duration_minutes"] == 90 and leg["duration_source"] == "user"
    assert leg["locked"] is True and leg["origin"] == "user"
    assert leg["lat"] is None and leg["place_id"] is None and leg["user_place_id"] is None
    assert leg["transport"]["note"] == "Coach 7" and leg["transport"]["to_lat"] == 43.77
    assert leg["default_duration_minutes"] is None


def test_a_length_not_entered_is_unknown(api_env: ApiEnv) -> None:
    _, plan = _trip(api_env)
    r = _leg(
        api_env, plan, 1, start_time="10:00:00", transport={"from_lat": None, "from_lon": None}
    )
    assert r.status_code == 201, r.text
    leg = r.json()
    assert leg["duration_minutes"] is None and leg["end_time"] is None
    assert leg["transport"]["from_lat"] is None
    untimed = _leg(api_env, plan, 2).json()
    assert untimed["start_time"] is None and untimed["duration_minutes"] is None


def test_a_night_train_arrives_the_next_day_and_ends_its_day(api_env: ApiEnv) -> None:
    _, plan = _trip(api_env)
    r = _leg(api_env, plan, 1, start_time="22:30:00", duration_minutes=540)
    assert r.status_code == 201, r.text
    assert r.json()["end_time"] is None and r.json()["duration_minutes"] == 540
    late = _own_visit(api_env, plan, 1, "22:45:00")
    assert late.status_code == 409 and code(late) == "overlap"
    assert _own_visit(api_env, plan, 1, "20:00:00").status_code == 201


def _own_visit(env: ApiEnv, plan: dict[str, Any], day: int, start: str) -> Any:
    place = env.client.post(
        "/v1/user-places",
        json={
            "kind": "location",
            "name": "Museum",
            "lat": 41.9,
            "lon": 12.5,
            "source": "manual_pin",
        },
        headers=env.headers,
    ).json()
    return add_item(
        env,
        plan,
        day,
        type="visit",
        user_place_id=place["id"],
        start_time=start,
        duration_minutes=60,
    )


def test_a_leg_overlaps_like_any_stop_and_a_point_inside_a_stop_clashes(api_env: ApiEnv) -> None:
    _, plan = _trip(api_env)
    assert _own_visit(api_env, plan, 1, "10:00:00").status_code == 201
    inside = _leg(api_env, plan, 1, start_time="10:30:00", duration_minutes=20)
    assert inside.status_code == 409 and code(inside) == "overlap"
    point = _leg(api_env, plan, 1, start_time="10:30:00")
    assert point.status_code == 409 and code(point) == "overlap"
    assert _leg(api_env, plan, 1, start_time="11:00:00").status_code == 201
    assert _leg(api_env, plan, 1, start_time="11:00:00").status_code == 201  # two points


def test_a_leg_needs_its_details_and_has_no_place(api_env: ApiEnv) -> None:
    _, plan = _trip(api_env)
    assert add_item(api_env, plan, 1, type="transport").status_code == 422
    place = api_env.client.post(
        "/v1/user-places",
        json={
            "kind": "location",
            "name": "Station",
            "lat": 41.9,
            "lon": 12.5,
            "source": "manual_pin",
        },
        headers=api_env.headers,
    ).json()
    with_place = add_item(
        api_env, plan, 1, type="transport", transport=TRAIN, user_place_id=place["id"]
    )
    assert with_place.status_code == 422
    half_point = _leg(api_env, plan, 1, transport={"to_lon": None})
    assert half_point.status_code == 422
    bad_mode = _leg(api_env, plan, 1, transport={"mode": "plane"})
    assert bad_mode.status_code == 422
    not_a_leg = add_item(
        api_env,
        plan,
        1,
        type="visit",
        user_place_id=place["id"],
        duration_minutes=30,
        transport=TRAIN,
    )
    assert not_a_leg.status_code == 422
    price = _leg(api_env, plan, 1, transport={"price": 12})
    assert price.status_code == 422  # no prices (ADR 017)


def test_a_leg_is_edited_its_length_cleared_and_it_cannot_be_unlocked(api_env: ApiEnv) -> None:
    _, plan = _trip(api_env)
    leg = _leg(api_env, plan, 1, start_time="10:00:00", duration_minutes=60).json()
    url = f"/v1/items/{leg['id']}"
    r = api_env.client.patch(
        url,
        json={"transport": {**TRAIN, "mode": "bus", "to_name": "Siena"}, "locked": False},
        headers=api_env.headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["display_name"] == "Bus to Siena" and r.json()["locked"] is True
    cleared = api_env.client.patch(url, json={"duration_minutes": None}, headers=api_env.headers)
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["duration_minutes"] is None and cleared.json()["end_time"] is None
    stop = _visit(api_env, plan, 1, "Museum", 1, "12:00:00")
    refused = api_env.client.patch(
        f"/v1/items/{stop}", json={"transport": TRAIN}, headers=api_env.headers
    )
    assert refused.status_code == 422 and code(refused) == "not_transport"
    assert api_env.client.delete(url, headers=api_env.headers).status_code == 204


def test_a_leg_between_two_stops_replaces_the_computed_leg(api_env: ApiEnv) -> None:
    _, plan = _trip(api_env)
    _visit(api_env, plan, 1, "Colosseum", 0, "09:00:00")
    _visit(api_env, plan, 1, "Uffizi", 5, "13:00:00")
    leg = _leg(api_env, plan, 1, position=2, start_time="10:12:00", duration_minutes=90).json()
    names = [i["display_name"] for i in _plan(api_env, plan)["days"][0]["items"]]
    assert names == ["Colosseum", "Train to Florence", "Uffizi"]
    assert leg["position"] == 2


def test_a_journey_leg_goes_first_and_covers_the_days_arrival(api_env: ApiEnv) -> None:
    _, plan = _trip(api_env)
    _visit(api_env, plan, 2, "Uffizi", 5, "13:00:00")
    day_id = _plan(api_env, plan)["days"][1]["id"]
    sql(
        api_env,
        "UPDATE app.itinerary_day SET arrival_mode = 'unknown', arrival_confidence = 'unknown'"
        " WHERE id = %s",
        day_id,
    )
    before = _plan(api_env, plan)["days"][1]["arrival"]
    assert before["mode"] == "unknown" and before["covered_by_item_id"] is None
    leg = _leg(
        api_env, plan, 2, start_time="10:12:00", duration_minutes=90, transport={"is_journey": True}
    ).json()
    day = _plan(api_env, plan)["days"][1]
    assert day["items"][0]["id"] == leg["id"]
    assert day["arrival"]["covered_by_item_id"] == leg["id"]


def test_every_edit_of_a_leg_keeps_a_version(api_env: ApiEnv) -> None:
    _, plan = _trip(api_env)
    _leg(api_env, plan, 1, start_time="10:00:00", duration_minutes=60)
    rows = sql(
        api_env,
        "SELECT version, state FROM app.itinerary_version WHERE itinerary_id = %s ORDER BY version",
        plan["id"],
    )
    assert rows and rows[-1][1]["items"] == []  # the version before the leg
    after = sql(api_env, "SELECT transport FROM app.itinerary_item WHERE type = 'transport'")
    assert after[0][0]["mode"] == "train"


# -- Optimize and recalculation (ADR 032, step 2) -------------------------------------------------


def test_optimize_never_moves_a_leg_or_a_stop_across_it(api_env: ApiEnv) -> None:
    from tests.test_api_optimize import _optimize

    _, plan = _trip(api_env, uses_car=True)
    for i, x in enumerate([0, 6, 1]):
        _visit(api_env, plan, 1, f"Before {x}", x, f"{9 + i:02d}:00:00")
    leg = _leg(api_env, plan, 1, start_time="12:30:00", duration_minutes=60).json()
    for i, x in enumerate([20, 26, 21]):
        _visit(api_env, plan, 1, f"After {x}", x, f"{14 + i:02d}:00:00")
    r = _optimize(api_env, plan, "across_days")
    assert r.status_code == 201, r.text
    change = r.json()
    day1 = sorted(
        (s for s in change["proposed"]["stops"] if s["day_index"] == 1),
        key=lambda s: s["position"],
    )
    ids = [s["item_id"] for s in day1]
    at = ids.index(leg["id"])
    assert at == 3
    applied = api_env.client.post(f"/v1/change-sets/{change['id']}/apply", headers=api_env.headers)
    assert applied.status_code == 200, applied.text
    items = _plan(api_env, plan)["days"][0]["items"]
    names = [i["display_name"] for i in items]
    assert names[3] == "Train to Florence" and all(n.startswith("Before") for n in names[:3])
    kept = items[3]
    assert kept["start_time"] == "12:30:00" and kept["transport"]["mode"] == "train"
    assert items[2]["transfer"] is None  # no computed leg runs into the train


def test_optimize_without_a_car_names_the_long_walks(api_env: ApiEnv) -> None:
    from tests.test_api_optimize import _optimize, _zigzag

    _, plan = _trip(api_env, uses_car=False)
    for i, x in enumerate([0, 2, 1, 3]):  # legs of 3.3 km and more, all walked
        _visit(api_env, plan, 1, f"Stop {x}", x, f"{9 + 2 * i:02d}:00:00", minutes=30)
    r = _optimize(api_env, plan, "within_days")
    assert r.status_code == 201, r.text
    change = r.json()
    notes = {n["code"]: n for n in change["notes"]}
    assert "OPTIMIZE_LONG_WALKS" in notes
    assert "Add a transport leg" in notes["OPTIMIZE_LONG_WALKS"]["text"]

    _, with_car = _trip(api_env, uses_car=True)
    _zigzag(api_env, with_car)
    codes = [n["code"] for n in _optimize(api_env, with_car, "within_days").json()["notes"]]
    assert "OPTIMIZE_LONG_WALKS" not in codes


def test_undo_of_optimize_brings_the_leg_back_unchanged(api_env: ApiEnv) -> None:
    from tests.test_api_optimize import _optimize, _zigzag

    _, plan = _trip(api_env, uses_car=True)
    _zigzag(api_env, plan)
    _leg(api_env, plan, 1, start_time="18:00:00", duration_minutes=45, transport={"note": "Late"})
    change = _optimize(api_env, plan, "within_days").json()
    api_env.client.post(f"/v1/change-sets/{change['id']}/apply", headers=api_env.headers)
    undo = api_env.client.post(
        f"/v1/itineraries/{plan['id']}/optimize/undo", headers=api_env.headers
    )
    assert undo.status_code == 201, undo.text
    api_env.client.post(f"/v1/change-sets/{undo.json()['id']}/apply", headers=api_env.headers)
    legs = [i for i in _plan(api_env, plan)["days"][0]["items"] if i["type"] == "transport"]
    assert len(legs) == 1 and legs[0]["transport"]["note"] == "Late"
    assert legs[0]["start_time"] == "18:00:00" and legs[0]["duration_minutes"] == 45


# -- placing a leg and moving the later stops (owner request of 2026-11-16) -----------------------


def test_a_leg_placed_after_its_stop_replaces_the_walk_and_can_move_the_later_stops(
    api_env: ApiEnv,
) -> None:
    from tests.test_api_optimize import _optimize

    _, plan = _trip(api_env, uses_car=False)
    for i, x in enumerate([0, 0.3, 0.1]):  # short walks; Optimize writes the legs
        _visit(api_env, plan, 1, f"Stop {i + 1}", x, f"{9 + i:02d}:00:00", minutes=50)
    change = _optimize(api_env, plan, "within_days").json()
    api_env.client.post(f"/v1/change-sets/{change['id']}/apply", headers=api_env.headers)
    items = _plan(api_env, plan)["days"][0]["items"]
    first, second = items[0], items[1]
    assert first["transfer"] is not None  # a computed walk from stop 1 to stop 2
    # A 30 min bus right after stop 1 runs into stop 2: refused unless the later stops move.
    start = first["end_time"]
    clash = _leg(api_env, plan, 1, position=2, start_time=start, duration_minutes=45)
    assert clash.status_code == 409 and code(clash) == "overlap"
    end_minute = int(start[:2]) * 60 + int(start[3:5]) + 45
    second_start = int(second["start_time"][:2]) * 60 + int(second["start_time"][3:5])
    shift = end_minute - second_start
    r = _leg(
        api_env,
        plan,
        1,
        position=2,
        start_time=start,
        duration_minutes=45,
        shift_later_minutes=shift,
    )
    assert r.status_code == 201, r.text
    after = _plan(api_env, plan)["days"][0]["items"]
    assert [i["type"] for i in after] == ["visit", "transport", "visit", "visit"]
    assert after[0]["transfer"] is None  # the walk is replaced by the leg
    moved = int(after[2]["start_time"][:2]) * 60 + int(after[2]["start_time"][3:5])
    assert moved == end_minute
    assert after[3]["start_time"] > items[2]["start_time"]  # every later stop moved
    versions = sql(
        api_env,
        "SELECT count(*) FROM app.itinerary_version WHERE itinerary_id = %s",
        plan["id"],
    )
    before_leg = versions[0][0]
    assert before_leg >= 1


def test_moving_the_later_stops_is_refused_past_midnight_and_for_a_stop(api_env: ApiEnv) -> None:
    _, plan = _trip(api_env)
    _visit(api_env, plan, 1, "Late show", 0, "22:00:00", minutes=90)
    r = _leg(
        api_env,
        plan,
        1,
        position=1,
        start_time="21:30:00",
        duration_minutes=60,
        shift_later_minutes=60,
    )
    assert r.status_code == 422 and code(r) == "shift_past_midnight"
    assert _plan(api_env, plan)["days"][0]["items"][0]["start_time"] == "22:00:00"  # unchanged
    place = api_env.client.post(
        "/v1/user-places",
        json={
            "kind": "location",
            "name": "Museum",
            "lat": 41.9,
            "lon": 12.5,
            "source": "manual_pin",
        },
        headers=api_env.headers,
    ).json()
    not_leg = add_item(
        api_env,
        plan,
        1,
        type="visit",
        user_place_id=place["id"],
        duration_minutes=30,
        shift_later_minutes=10,
    )
    assert not_leg.status_code == 422


def test_changing_a_leg_can_move_the_later_stops_too(api_env: ApiEnv) -> None:
    _, plan = _trip(api_env)
    _visit(api_env, plan, 1, "Stop 1", 0, "09:00:00", minutes=60)
    leg = _leg(api_env, plan, 1, start_time="10:00:00", duration_minutes=30).json()
    _visit(api_env, plan, 1, "Stop 2", 1, "10:30:00", minutes=60)
    url = f"/v1/items/{leg['id']}"
    longer = api_env.client.patch(url, json={"duration_minutes": 50}, headers=api_env.headers)
    assert longer.status_code == 409 and code(longer) == "overlap"
    r = api_env.client.patch(
        url, json={"duration_minutes": 50, "shift_later_minutes": 20}, headers=api_env.headers
    )
    assert r.status_code == 200, r.text
    items = _plan(api_env, plan)["days"][0]["items"]
    assert [(i["display_name"], i["start_time"]) for i in items] == [
        ("Stop 1", "09:00:00"),
        ("Train to Florence", "10:00:00"),
        ("Stop 2", "10:50:00"),
    ]
