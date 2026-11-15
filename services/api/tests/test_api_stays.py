"""Stays (ADR 030): where the traveller sleeps, per range of days, and what they change: the
morning leg on a day, and Optimize starting each day at its stay. Travel times are labelled
estimates: the test database has no routing provider."""

from typing import Any

import pytest

from tests.conftest import ApiEnv
from tests.test_api_optimize import _optimize, _trip, _visit, _zigzag

pytestmark = pytest.mark.db

LON = 13.65


def _stay(env: ApiEnv, trip: dict[str, Any], first: int, last: int, x: float = 0.0) -> Any:
    return env.client.post(
        f"/v1/trips/{trip['id']}/stays",
        json={
            "name": f"Hotel {first}-{last}",
            "lat": 47.50 + x * 0.03,
            "lon": LON,
            "first_day": first,
            "last_day": last,
        },
        headers=env.headers,
    )


def test_stays_are_created_listed_changed_and_removed(api_env: ApiEnv) -> None:
    trip, _ = _trip(api_env, days=4)
    assert _stay(api_env, trip, 1, 2).status_code == 201
    second = _stay(api_env, trip, 3, 4)
    assert second.status_code == 201
    got = api_env.client.get(f"/v1/trips/{trip['id']}/stays", headers=api_env.headers).json()
    assert [(s["first_day"], s["last_day"]) for s in got] == [(1, 2), (3, 4)]
    url = f"/v1/trips/{trip['id']}/stays/{second.json()['id']}"
    r = api_env.client.patch(url, json={"name": "Pension"}, headers=api_env.headers)
    assert r.status_code == 200 and r.json()["name"] == "Pension"
    assert api_env.client.delete(url, headers=api_env.headers).status_code == 204
    assert (
        api_env.client.get(url.rsplit("/", 1)[0], headers=api_env.headers).json()[0]["last_day"]
        == 2
    )


def test_stays_may_not_overlap_or_leave_the_trip(api_env: ApiEnv) -> None:
    trip, _ = _trip(api_env, days=3)
    assert _stay(api_env, trip, 1, 2).status_code == 201
    overlap = _stay(api_env, trip, 2, 3)
    assert overlap.status_code == 409 and overlap.json()["code"] == "stay_overlap"
    assert _stay(api_env, trip, 3, 5).json()["code"] == "day_out_of_range"
    assert _stay(api_env, trip, 3, 2).json()["code"] == "bad_day_range"


def test_a_day_with_a_stay_says_how_the_morning_goes(api_env: ApiEnv) -> None:
    trip, plan = _trip(api_env)
    first = _visit(api_env, plan, 1, "Museum", 3, "09:00:00")
    assert _stay(api_env, trip, 1, 2).status_code == 201
    got = api_env.client.get(f"/v1/itineraries/{plan['id']}", headers=api_env.headers).json()
    start = got["days"][0]["start"]
    assert start["to_item_id"] == first and start["seconds"] > 0
    assert start["confidence"] == "estimated"  # nothing routed it
    assert got["days"][1]["start"] is None  # no stop on day 2


def test_optimize_starts_each_day_at_its_stay(api_env: ApiEnv) -> None:
    trip, plan = _trip(api_env)
    _zigzag(api_env, plan)  # stops at x = 0, 6, 1, 7, 2
    assert _stay(api_env, trip, 1, 2, x=7).status_code == 201
    r = _optimize(api_env, plan, "within_days")
    assert r.status_code == 201, r.text
    change = r.json()
    day1 = [s for s in change["proposed"]["stops"] if s["day_index"] == 1]
    order = [s["item_id"] for s in sorted(day1, key=lambda s: s["position"])]
    assert change["proposed"]["starts"][0]["to_item_id"] == order[0]
    assert change["diff"]["travel_minutes_added"] < 0
