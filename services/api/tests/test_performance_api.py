"""Phase 9 performance pass through the API on the fixture database (docs/kpis.md, section 3).

Measures what the app's screens wait for: the trip list (GET /v1/trips with 20 trips), a plan of 30
stops (the day list and the map read the same GET /v1/itineraries/{id}), an Optimize preview of
that plan, and a destination search. The bounds are loose on purpose (a slow CI runner must not
fail): the numbers are printed with ``-s`` and recorded in docs/test-plan-phase-9.md. Nothing
calls a provider: travel times are labelled estimates.
"""

import statistics
import time
from collections.abc import Callable
from typing import Any

import pytest

from tests.conftest import ApiEnv
from tests.test_api_trips import add_item, make_itinerary, make_trip

pytestmark = pytest.mark.db


def _ms(fn: Callable[[], Any], runs: int = 5) -> tuple[float, float]:
    times = []
    for _ in range(runs):
        started = time.perf_counter()
        fn()
        times.append((time.perf_counter() - started) * 1000)
    return statistics.median(times), max(times)


def test_screens_wait_well_under_their_targets(api_env: ApiEnv) -> None:
    c, h = api_env.client, api_env.headers
    for n in range(19):
        make_trip(api_env, title=f"Trip {n}", duration_days=3)
    trip = make_trip(api_env, title="Big", duration_days=7, start_date="2027-05-01")
    plan = make_itinerary(api_env, trip)
    c.patch(f"/v1/trips/{trip['id']}", json={"selected_itinerary_id": plan["id"]}, headers=h)
    for k in range(30):
        day = k % 7 + 1
        r = c.post(
            "/v1/user-places",
            json={
                "kind": "location",
                "name": f"Stop {k}",
                "lat": 48.20 + ((k * 37) % 30) * 0.002,
                "lon": 16.36 + ((k * 11) % 30) * 0.003,
                "source": "manual_pin",
            },
            headers=h,
        )
        place = r.json()["id"]
        start = f"{9 + k // 7:02d}:00"
        r = add_item(
            api_env,
            plan,
            day,
            type="visit",
            user_place_id=place,
            start_time=start,
            duration_minutes=45,
        )
        assert r.status_code == 201, r.text

    trips_ms = _ms(lambda: c.get("/v1/trips", headers=h).raise_for_status())
    plan_ms = _ms(lambda: c.get(f"/v1/itineraries/{plan['id']}", headers=h).raise_for_status())
    search_ms = _ms(
        lambda: c.get(
            "/v1/destinations/search", params={"q": "testburg"}, headers=h
        ).raise_for_status()
    )

    def preview() -> None:
        r = c.post(
            f"/v1/itineraries/{plan['id']}/optimize", json={"scope": "across_days"}, headers=h
        )
        assert r.status_code in (201, 409), r.text

    optimize_ms = _ms(preview, runs=3)
    for label, (median, worst) in (
        ("trip list (20 trips)", trips_ms),
        ("plan of 30 stops (day list and map)", plan_ms),
        ("destination search", search_ms),
        ("Optimize preview, 30 stops, across days", optimize_ms),
    ):
        print(f"\nPERF {label}: median {median:.0f} ms, worst {worst:.0f} ms")
    assert trips_ms[1] < 3_000
    assert plan_ms[1] < 3_000
    assert search_ms[1] < 3_000
    assert optimize_ms[1] < 5_000  # the Optimize latency KPI
