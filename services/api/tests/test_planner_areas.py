"""Area destinations (Phase 6, ADR 016), without a database. (The meals of Phase 6 were removed by
ADR 026.)

Areas: base cities are chosen by sights and population, kept apart, given days in proportion and
visited in travel-time order; the first day at a new base starts with the drive; long legs are
asked of the travel source like any other cell.
"""

import dataclasses
from datetime import date
from typing import Any

import pytest

from detour_api.planner import areas, engine
from detour_api.planner.config import DEFAULT_CONFIG, PlannerConfig
from detour_api.planner.travel import FixedTravelSource, TravelLookup
from detour_api.planner.types import BaseCity, Generation, PlanningImpossible
from detour_api.repo.geo import ResolvedDestination, area_planning_allowed
from detour_api.travel.types import Coord, distance_m
from tests.planner_helpers import candidates, request, towns

ALL_CASES = [
    ("city-large", 3),
    ("city-large", 7),
    ("city-large", 14),
    ("city-sparse", 1),
    ("city-sparse", 3),
    ("area", 3),
    ("area", 7),
    ("area", 14),
]


def run(name: str, days: int, **kw: Any) -> Generation:
    return engine.generate(
        request(name, days, date(2026, 6, 1)),
        candidates(name),
        FixedTravelSource(),
        **kw,
    )


def hm(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


# -- areas ---------------------------------------------------------------------------------------


def test_area_bases_follow_sights_population_and_separation() -> None:
    eligible = areas.eligible_bases(towns("area"), candidates("area"), DEFAULT_CONFIG)
    names = [b.city.name for b in eligible]
    assert "Synthetic Town F" not in names  # two sights: too few to stay at
    assert "Synthetic Town E" not in names  # 12 km from the larger Town A: not a main town
    assert names[:4] == ["Synthetic Town A", "Synthetic Town B", "Synthetic Town C",
                         "Synthetic Town D"]  # fmt: skip
    chosen = areas.choose_bases(eligible, 30, DEFAULT_CONFIG.profile("wider"), DEFAULT_CONFIG)
    # Town E (12 km from A) is never a second base next to A.
    assert "Synthetic Town E" not in [b.city.name for b in chosen]
    for a in chosen:
        for b in chosen:
            if a is not b:
                assert (
                    distance_m(a.city.coord, b.city.coord) >= DEFAULT_CONFIG.min_base_separation_m
                )


@pytest.mark.parametrize(
    ("days", "essentials", "wider"),
    [(1, 1, 1), (3, 1, 1), (4, 1, 2), (7, 2, 3), (14, 4, 4)],
)
def test_area_fixtures_give_a_sensible_day_allocation(
    days: int, essentials: int, wider: int
) -> None:
    g = run("area", days)
    by_profile = {p.profile: p for p in g.plans}
    expected = {"essentials": essentials, "wider": wider}
    all_towns = {t.city_id: t for t in towns("area")}
    for profile, plan in by_profile.items():
        allocation = plan.allocation()
        assert len(allocation) == expected[profile], allocation
        assert sum(n for _, n in allocation) == days and all(n >= 1 for _, n in allocation)
        ids = [b for b, _ in allocation]
        assert len(ids) == len(set(ids)), "each base is one run of consecutive days"
        assert ids[0] == 990001, "the best town comes first"
        # More sights and people, at least as many days (A, then B, then C, then D).
        assert [n for _, n in sorted(allocation, key=lambda x: x[0] or 0)] == sorted(
            (n for _, n in allocation), reverse=True
        )
        radius = DEFAULT_CONFIG.profile(profile).radius_m
        for day in plan.days:
            base = all_towns[day.base_city_id or 0]
            assert day.base_city_name == base.name
            for v in day.visits:
                assert distance_m(base.coord, Coord.from_degrees(v.lat, v.lon)) <= radius


def test_bases_are_visited_in_travel_time_order() -> None:
    plan = run("area", 14).plans[0]
    order = [b for b, _ in plan.allocation() if b is not None]
    coords = {t.city_id: t.coord for t in towns("area")}
    # Greedy nearest next base from the best one: A, then the nearer of the rest, and so on.
    left = set(order[1:])
    here = order[0]
    for nxt in order[1:]:
        nearest = min(left, key=lambda c: (distance_m(coords[here], coords[c]), c))
        assert nxt == nearest
        left.remove(nxt)
        here = nxt


def test_a_new_base_starts_its_first_day_with_the_drive() -> None:
    for plan in run("area", 14).plans:
        previous = None
        for day in plan.days:
            moved = previous is not None and day.base_city_id != previous
            assert (day.arrival is not None) == moved
            if day.arrival is not None:
                assert day.arrival.mode == "drive"
                assert day.items == () or day.items[0].start_minute >= 9 * 60 + day.arrival.minutes
                note = next(
                    n
                    for n in plan.notes
                    if n.code == "INTER_CITY_TRAVEL" and n.params["day"] == day.day_index
                )
                assert note.params["minutes"] == day.arrival.minutes
                assert note.params["label"] == day.arrival.confidence
            previous = day.base_city_id
        assert plan.stats.intercity_legs == sum(d.arrival is not None for d in plan.days)
    # The 330-minute drive to Town D leaves a day that starts at 14:30: too late for the midday gap
    # (it must start by 14:00), so that day has none and is still valid.
    late = [
        d
        for p in run("area", 14).plans
        for d in p.days
        if d.items and d.items[0].start_minute > DEFAULT_CONFIG.midday_gap.latest_start
    ]
    assert late
    for d in late:
        for x, y in zip(d.items, d.items[1:], strict=False):
            assert x.transfer is not None
            assert y.start_minute == x.end_minute + x.transfer.minutes


def test_inter_city_legs_are_asked_of_the_travel_source_including_long_ones() -> None:
    town_list = towns("area")
    table = {
        (a.coord, b.coord): (
            int(distance_m(a.coord, b.coord) / 25),
            int(distance_m(a.coord, b.coord) * 1.25),
        )
        for a in town_list
        for b in town_list
        if a is not b
    }
    long_legs = [cell for cell in table if distance_m(*cell) > 150_000]
    assert long_legs, "the fixture has legs beyond the 150 km matrix limit"
    source = FixedTravelSource(table, provider_only=True)
    g = engine.generate(
        request("area", 14),
        candidates("area"),
        source,
        use_provider=True,
    )
    arrivals = [d.arrival for p in g.plans for d in p.days if d.arrival is not None]
    assert arrivals and all(a.confidence == "routed" for a in arrivals)
    assert any(a.meters > 150_000 for a in arrivals)


def test_an_area_without_a_possible_base_explains_why() -> None:
    lonely = [BaseCity(1, "Nowhere", 47.0, 10.0, 500)]
    req = dataclasses.replace(request("area", 3), base_cities=tuple(lonely))
    with pytest.raises(PlanningImpossible) as exc:
        engine.generate(req, candidates("area"), FixedTravelSource())
    [issue] = exc.value.issues
    assert issue.code == "NO_BASE_CITIES"
    assert issue.params == {"destination": "Synthetic Area", "min_sights": 3, "radius_km": 5}


def test_allocation_is_proportional_with_at_least_one_day_each() -> None:
    city = BaseCity(1, "x", 47.0, 10.0)
    bases = [areas.EligibleBase(city, s, 5) for s in (600, 300, 100)]
    assert areas.allocate_days(bases, 3) == [1, 1, 1]
    assert areas.allocate_days(bases, 10) == [5, 3, 2]
    assert sum(areas.allocate_days(bases, 30)) == 30
    zero = [areas.EligibleBase(city, 0, 5)] * 2
    assert areas.allocate_days(zero, 5) == [3, 2]


def test_the_number_of_bases_grows_with_days_per_profile() -> None:
    e, w = DEFAULT_CONFIG.profile("essentials"), DEFAULT_CONFIG.profile("wider")
    assert [areas.base_count(d, 10, e, DEFAULT_CONFIG) for d in (1, 4, 5, 8, 9, 30)] == [
        1, 1, 2, 2, 3, 6]  # fmt: skip
    assert [areas.base_count(d, 10, w, DEFAULT_CONFIG) for d in (1, 3, 4, 7, 30)] == [
        1, 1, 2, 3, 6]  # fmt: skip
    assert areas.base_count(30, 2, w, DEFAULT_CONFIG) == 2


def test_areas_in_japan_are_single_city_only() -> None:
    def dest(country: str | None, region: tuple[str, ...] = ()) -> ResolvedDestination:
        return ResolvedDestination("x", 0.0, 0.0, country, "r", "available", region)

    assert not area_planning_allowed(dest("JP"))
    assert not area_planning_allowed(dest(None, ("JP",)))
    assert area_planning_allowed(dest("AT"))
    assert area_planning_allowed(dest(None, ("AT",)))
    assert PlannerConfig().single_city_countries == ("JP",)


def test_an_area_plan_is_deterministic() -> None:
    first = engine.to_json(run("area", 7))
    shuffled = engine.generate(
        request("area", 7, date(2026, 6, 1)),
        list(reversed(candidates("area"))),
        FixedTravelSource(),
    )
    assert engine.to_json(shuffled) == first


def test_lookup_is_used_for_base_order() -> None:
    town_list = towns("area")[:3]
    lookup = TravelLookup(FixedTravelSource(), DEFAULT_CONFIG.walk_max_m)
    eligible = [areas.EligibleBase(t, 100 - i, 5) for i, t in enumerate(town_list)]
    assert areas.order_bases(eligible, lookup)[0].city.city_id == town_list[0].city_id
    assert [b.city.city_id for b in areas.order_bases([], lookup)] == []
