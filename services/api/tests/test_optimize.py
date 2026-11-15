"""Optimize's search and its independent check (ADR 029), on synthetic points. No database."""

import random

import pytest

from detour_api.planner.optimize import (
    FAR_STOP_M,
    CityPoint,
    DayInfo,
    Stop,
    build_stops,
    optimize,
)
from detour_api.planner.optimize_validator import validate
from detour_api.planner.travel import FixedTravelSource, TravelLookup
from detour_api.travel.types import Coord

STEP = 0.02  # about 2.2 km of latitude


def stop(
    id_: str,
    x: float,
    day: int = 1,
    start: int | None = None,
    duration: int = 60,
    kind: str = "visit",
    fixed: bool = False,
    allowed: set[int] | None = None,
) -> Stop:
    s = start if start is not None else 540
    return Stop(
        id=id_,
        kind=kind,  # type: ignore[arg-type]
        name=id_,
        lat=48.0 + x * STEP,
        lon=16.0,
        day=day,
        start=s,
        end=s + duration,
        duration=duration,
        fixed=fixed,
        allowed_days=frozenset(allowed if allowed is not None else {day}),
    )


def run(stops: list[Stop], days: list[int], scope: str = "within_days") -> tuple[list[str], object]:
    lookup = TravelLookup(FixedTravelSource(), 2_000)
    out = optimize(stops, days, scope=scope, lookup=lookup, use_provider=False)  # type: ignore[arg-type]
    assert validate(stops, days, out) == []
    return [p.id for d in days for p in out.days[d]], out


def test_a_zigzag_day_is_untangled() -> None:
    xs = [0, 3, 1, 4, 2, 5]
    stops = [stop(f"s{i}", x, start=540 + 70 * i) for i, x in enumerate(xs)]
    order, out = run(stops, [1])
    assert out.travel_after < out.travel_before  # type: ignore[attr-defined]
    assert out.changed_days == (1,)  # type: ignore[attr-defined]
    assert sorted(order) == sorted(s.id for s in stops)


def test_an_order_that_is_already_short_is_left_alone() -> None:
    stops = [stop(f"s{i}", i, start=540 + 70 * i) for i in range(5)]
    _, out = run(stops, [1])
    assert out.changed_days == ()  # type: ignore[attr-defined]
    assert out.travel_after == out.travel_before  # type: ignore[attr-defined]


def test_nothing_changes_day_in_the_first_scope() -> None:
    stops = [
        stop("a", 0, 1, 540),
        stop("b", 10, 1, 610),
        stop("c", 1, 2, 540),
        stop("d", 11, 2, 610),
    ]
    out = run(stops, [1, 2], "within_days")[1]
    placed = {p.id: p.day for d in (1, 2) for p in out.days[d]}  # type: ignore[attr-defined]
    assert placed == {"a": 1, "b": 1, "c": 2, "d": 2}


def test_a_stop_moves_to_the_day_it_belongs_with() -> None:
    # a and c are close, b and d are close; day 1 has a and d, day 2 has b and c.
    allowed = {1, 2}
    stops = [
        stop("a", 0, 1, 540, allowed=allowed),
        stop("d", 20, 1, 610, allowed=allowed),
        stop("b", 21, 2, 540, allowed=allowed),
        stop("c", 1, 2, 610, allowed=allowed),
    ]
    out = run(stops, [1, 2], "across_days")[1]
    placed = {p.id: p.day for d in (1, 2) for p in out.days[d]}  # type: ignore[attr-defined]
    assert placed["a"] == placed["c"] and placed["b"] == placed["d"] and placed["a"] != placed["b"]
    assert out.travel_after < out.travel_before  # type: ignore[attr-defined]


def test_a_locked_stop_keeps_its_day_and_times() -> None:
    allowed = {1, 2}
    stops = [
        stop("a", 0, 1, 540, allowed=allowed),
        stop("lock", 20, 1, 700, fixed=True, allowed=allowed),
        stop("b", 21, 2, 540, allowed=allowed),
        stop("c", 1, 2, 610, allowed=allowed),
    ]
    out = run(stops, [1, 2], "across_days")[1]
    lock = next(p for d in (1, 2) for p in out.days[d] if p.id == "lock")  # type: ignore[attr-defined]
    assert (lock.day, lock.start, lock.end) == (1, 700, 760)


def test_a_restaurant_stays_on_its_day_within_an_hour_of_its_time() -> None:
    lunch = stop("lunch", 2, 1, 12 * 60 + 30, 75, kind="meal")
    xs = [0, 4, 1, 3]
    stops = [stop(f"s{i}", x, start=540 + 60 * i, duration=45) for i, x in enumerate(xs)]
    stops.insert(2, lunch)
    _, out = run(stops, [1])
    placed = next(p for p in out.days[1] if p.id == "lunch")  # type: ignore[attr-defined]
    assert 12 * 60 + 30 <= placed.start <= 13 * 60 + 30


def test_a_dinner_never_starts_after_21() -> None:
    dinner = stop("dinner", 3, 1, 20 * 60 + 30, 90, kind="meal")
    stops = [stop("a", 0, start=18 * 60), stop("b", 5, start=19 * 60), dinner]
    _, out = run(stops, [1])
    placed = next(p for p in out.days[1] if p.id == "dinner")  # type: ignore[attr-defined]
    assert placed.start <= 21 * 60


def test_a_day_cannot_be_made_to_run_past_its_own_end() -> None:
    # A day that ends at 13:00 stays inside the window; nothing is pushed past 20:00.
    stops = [stop(f"s{i}", x, start=540 + 70 * i) for i, x in enumerate([0, 5, 1, 4, 2])]
    out = run(stops, [1])[1]
    assert max(p.end for p in out.days[1]) <= 20 * 60  # type: ignore[attr-defined]


def test_the_same_plan_gives_the_same_answer() -> None:
    xs = [0, 7, 2, 9, 4, 1, 8]
    stops = [stop(f"s{i}", x, start=540 + 65 * i, duration=40) for i, x in enumerate(xs)]
    first = run(stops, [1])[0]
    assert run(stops, [1])[0] == first


@pytest.mark.parametrize("seed", range(12))
def test_never_worse_and_every_stop_survives(seed: int) -> None:
    rng = random.Random(seed)  # noqa: S311 - a fixed seed for a fixture, not security
    days = [1, 2, 3]
    stops: list[Stop] = []
    for d in days:
        t = 540
        for i in range(rng.randint(2, 6)):
            dur = rng.choice([30, 45, 60, 90])
            stops.append(stop(f"d{d}s{i}", rng.randint(0, 30), d, t, dur, allowed={1, 2, 3}))
            t += dur + 15
    lunch = stop("lunch", 5, 2, 12 * 60 + 30, 60, kind="meal", allowed={2})
    stops.append(lunch)
    stops.sort(key=lambda s: (s.day, s.start or 0))
    for scope in ("within_days", "across_days"):
        order, out = run(stops, days, scope)
        assert sorted(order) == sorted(s.id for s in stops)
        assert out.travel_after <= out.travel_before  # type: ignore[attr-defined]
        meal = next(p for d in days for p in out.days[d] if p.id == "lunch")  # type: ignore[attr-defined]
        assert meal.day == 2


# -- who may move, from the plan ---------------------------------------------------------------


def item(
    id_: str,
    day: int,
    lat: float,
    start: int,
    lon: float = 16.0,
    locked: bool = False,
    kind: str = "visit",
) -> dict[str, object]:
    return {
        "id": id_,
        "day": day,
        "type": kind,
        "display_name": id_,
        "lat": lat,
        "lon": lon,
        "start_minute": start,
        "end_minute": start + 60,
        "duration_minutes": 60,
        "locked": locked,
    }


def test_a_place_trip_stop_far_from_the_point_keeps_its_day() -> None:
    days = [DayInfo(1, None), DayInfo(2, None)]
    far_lat = 48.0 + (FAR_STOP_M + 5_000) / 111_000
    items = [item("near", 1, 48.0, 540), item("far", 1, far_lat, 620), item("n2", 2, 48.01, 540)]
    stops, far = build_stops(
        items, days, scope="across_days", fixed_ids=[], place_point=(48.0, 16.0)
    )
    by_id = {s.id: s for s in stops}
    assert by_id["near"].allowed_days == {1, 2}
    assert by_id["far"].allowed_days == {1}
    assert far == 1


def test_a_stop_stays_in_the_days_of_its_own_city() -> None:
    days = [DayInfo(1, 10), DayInfo(2, 10), DayInfo(3, 20)]
    cities = [CityPoint(10, 48.2, 16.4), CityPoint(20, 47.8, 13.0)]
    items = [item("vienna", 1, 48.21, 540, lon=16.4), item("salzburg", 3, 47.8, 540, lon=13.0)]
    stops, _ = build_stops(items, days, scope="across_days", fixed_ids=[], cities=cities)
    by_id = {s.id: s for s in stops}
    assert by_id["vienna"].allowed_days == {1, 2}
    assert by_id["salzburg"].allowed_days == {3}


def test_locked_and_kept_stops_are_fixed_and_free_time_is_a_block() -> None:
    days = [DayInfo(1, None)]
    free = item("free", 1, 0.0, 700, kind="free_time")
    free["lat"] = None
    free["lon"] = None
    items = [
        item("a", 1, 48.0, 540, locked=True),
        item("b", 1, 48.1, 620),
        item("c", 1, 48.2, 700),
        free,
    ]
    stops, _ = build_stops(items, days, scope="within_days", fixed_ids=["b"])
    assert {s.id: s.fixed for s in stops} == {"a": True, "b": True, "c": False, "free": True}


def test_a_day_with_an_untimed_item_is_left_as_it_is() -> None:
    days = [DayInfo(1, None), DayInfo(2, None)]
    untimed = item("u", 1, 48.0, 0)
    untimed["start_minute"] = None
    untimed["end_minute"] = None
    items = [untimed, item("v", 1, 48.1, 620), item("w", 2, 48.2, 540)]
    stops, _ = build_stops(items, days, scope="across_days", fixed_ids=[])
    by_id = {s.id: s for s in stops}
    assert by_id["v"].fixed and by_id["u"].fixed
    assert by_id["w"].allowed_days == {2}


def test_an_empty_day_stays_empty_and_a_day_keeps_a_stop() -> None:
    allowed = {1, 2, 3}
    stops = [
        stop("a", 0, 1, 540, allowed=allowed),
        stop("b", 1, 1, 610, allowed=allowed),
        stop("c", 2, 1, 680, allowed=allowed),
        stop("d", 30, 3, 540, allowed=allowed),  # day 2 is empty
    ]
    out = run(stops, [1, 2, 3], "across_days")[1]
    assert out.days[2] == ()  # type: ignore[attr-defined]
    assert out.days[3] and out.days[1]  # type: ignore[attr-defined]


def test_without_a_car_every_leg_is_walked_however_long() -> None:
    far = (Coord.from_degrees(0.0, 0.0), Coord.from_degrees(0.0, 1.0))  # about 110 km apart
    driving = TravelLookup(FixedTravelSource(), 2_000)
    walking = TravelLookup(FixedTravelSource(), 10**9)  # optimize_service.WALK_EVERYWHERE_M
    assert driving.mode(*far) == "drive"
    assert walking.mode(*far) == "walk"
    assert walking.get(*far).seconds > driving.get(*far).seconds
