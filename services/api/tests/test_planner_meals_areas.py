"""Meals and area destinations (Phase 6, ADR 016), without a database.

Meals: every meal lies inside its window and the day's hours, at an imported place to eat whose
venue type serves that meal; places are chosen by proximity, cuisine variety and venue type; a
missing place to eat is said, never invented.

Areas: base cities are chosen by sights and population, kept apart, given days in proportion and
visited in travel-time order; the first day at a new base starts with the drive; long legs are
asked of the travel source like any other cell.
"""

import dataclasses
import re
from datetime import date
from typing import Any

import pytest

from detour_api.planner import areas, engine
from detour_api.planner.config import DEFAULT_CONFIG, PlannerConfig
from detour_api.planner.meals import RestaurantIndex, choose
from detour_api.planner.reasons import ITEM_TEMPLATES
from detour_api.planner.travel import FixedTravelSource, TravelLookup
from detour_api.planner.types import (
    BaseCity,
    Generation,
    PlanningImpossible,
    Restaurant,
)
from detour_api.repo.geo import ResolvedDestination, area_planning_allowed
from detour_api.travel.types import Coord, distance_m
from tests.planner_helpers import candidates, request, restaurants, towns

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
        restaurants=restaurants(name),
        **kw,
    )


def hm(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


# -- meals ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(("name", "days"), ALL_CASES)
def test_meals_are_inside_their_windows_and_the_day(name: str, days: int) -> None:
    by_id = {r.place_id: r for r in restaurants(name)}
    g = run(name, days)
    for plan in g.plans:
        profile = DEFAULT_CONFIG.profile(plan.profile)
        planned = skipped = 0
        for day in plan.days:
            types = [m.meal_type for m in day.meals]
            assert len(types) == len(set(types)), "each meal at most once a day"
            assert types == [t for t in profile.meals if t in types], "meals in time order"
            for meal in day.meals:
                assert meal.meal_type is not None
                window = DEFAULT_CONFIG.meal_window(meal.meal_type)
                assert window.start_minute <= meal.start_minute
                assert meal.end_minute <= min(window.end_minute, profile.day_end_minute)
                place = by_id[meal.place_id]  # an imported place, never an invented one
                assert meal.meal_type in place.meal_types
                assert meal.duration_minutes == DEFAULT_CONFIG.meal_minutes(
                    meal.meal_type, place.venue_type
                )
            if day.items:
                assert day.items[-1].end_minute <= profile.day_end_minute
            planned += len(day.meals)
            skipped += (len(profile.meals) if day.visits else 0) - len(day.meals)
        counts = [
            n.params["count"]
            for n in plan.notes
            if n.code in ("MEALS_NOT_PLANNED", "MEALS_SKIPPED_FOR_TRAVEL")
        ]
        explained = sum(c for c in counts if isinstance(c, int))
        assert skipped == explained, "every meal not planned is explained in a note"
        assert plan.stats.meals == planned


def test_venue_type_decides_which_meals_a_place_serves() -> None:
    plan = run("city-large", 3).plans[1]  # Wider: lunch, snack, dinner
    by_type: dict[str, set[str]] = {}
    for day in plan.days:
        for meal in day.meals:
            assert meal.meal_type is not None
            by_type.setdefault(meal.meal_type, set()).add(meal.category)
    assert by_type == {"lunch": {"restaurant"}, "snack": {"cafe"}, "dinner": {"restaurant"}}


def test_unknown_cuisine_is_kept_unknown() -> None:
    meals = [m for p in run("city-large", 7).plans for d in p.days for m in d.meals]
    unknown = [m for m in meals if m.cuisines is None]
    assert unknown, "the fixture has places without a cuisine tag"
    assert all("CUISINE_NOT_SPECIFIED" in m.reasons for m in unknown)
    assert all("NEW_CUISINE" not in m.reasons for m in unknown)
    assert ITEM_TEMPLATES["CUISINE_NOT_SPECIFIED"] == "Cuisine not specified in the map data."


def test_the_meal_reason_templates_match_the_configured_windows() -> None:
    for window in DEFAULT_CONFIG.meal_windows:
        text = ITEM_TEMPLATES[f"{window.meal_type.upper()}_WINDOW"]
        assert re.findall(r"\d\d:\d\d", text) == [hm(window.start_minute), hm(window.end_minute)]


def test_without_places_to_eat_meals_are_not_planned_and_the_plan_says_so() -> None:
    g = engine.generate(
        request("city-large", 2), candidates("city-large"), FixedTravelSource(), restaurants=[]
    )
    for plan in g.plans:
        assert all(not d.meals for d in plan.days)
        note = next(n for n in plan.notes if n.code == "MEALS_NOT_PLANNED")
        assert note.params["count"] == 2 * len(DEFAULT_CONFIG.profile(plan.profile).meals)


def test_breakfast_can_be_planned_before_the_first_visit() -> None:
    with_breakfast = dataclasses.replace(
        DEFAULT_CONFIG,
        profiles=tuple(
            dataclasses.replace(p, meals=("breakfast", "lunch", "dinner"))
            for p in DEFAULT_CONFIG.profiles
        ),
    )
    g = run("city-large", 2, config=with_breakfast)
    for plan in g.plans:
        for day in plan.days:
            first = day.items[0]
            assert (first.kind, first.meal_type, first.category) == ("meal", "breakfast", "cafe")
            assert first.start_minute == 9 * 60 and first.end_minute <= 10 * 60


def _eatery(
    pid: str, lat: float, cuisines: tuple[str, ...] | None, venue: str = "restaurant"
) -> Restaurant:
    meal_types = ("dinner", "lunch") if venue == "restaurant" else ("breakfast", "snack")
    return Restaurant(pid, f"Place {pid}", venue, lat, 16.0, meal_types, cuisines)


def test_choice_prefers_near_then_new_cuisine_then_known_cuisine() -> None:
    here = Coord.from_degrees(48.0, 16.0)
    index = RestaurantIndex(
        [
            _eatery("a", 48.0010, ("pizza",)),  # 111 m, a cuisine the plan already has
            _eatery("b", 48.0012, ("greek",)),  # 133 m, a new cuisine
            _eatery("c", 48.0011, None),  # 122 m, cuisine not stated
            _eatery("d", 48.0001, ("cake",), venue="cafe"),  # nearest, but a cafe
            _eatery("e", 48.0100, ("thai",)),  # 1.1 km: outside the first ring
        ]
    )
    c = DEFAULT_CONFIG
    pick = choose(index, "lunch", here, None, set(), {"pizza"}, c)
    assert pick is not None and pick.restaurant.place_id == "b" and pick.ring == 0
    # Without the pizza already in the plan, the nearest restaurant wins.
    pick = choose(index, "lunch", here, None, set(), set(), c)
    assert pick is not None and pick.restaurant.place_id == "a"
    # A snack needs a cafe.
    pick = choose(index, "snack", here, None, set(), set(), c)
    assert pick is not None and pick.restaurant.place_id == "d"
    # Places of earlier days are used again only when nothing unused is within reach.
    pick = choose(index, "lunch", here, None, {"a", "b", "c"}, set(), c)
    assert pick is not None and pick.restaurant.place_id == "e" and not pick.repeated
    pick = choose(index, "lunch", here, None, {"a", "b", "c", "e"}, set(), c)
    assert pick is not None and pick.repeated
    # Never twice on the same day.
    assert choose(index, "lunch", here, None, set(), set(), c, today={"a", "b", "c", "e"}) is None


def test_choice_counts_the_detour_between_the_visits_before_and_after() -> None:
    prev = Coord.from_degrees(48.0, 16.0)
    nxt = Coord.from_degrees(48.0040, 16.0)
    index = RestaurantIndex(
        [_eatery("on-the-way", 48.0020, ("a",)), _eatery("behind", 47.9990, ("b",))]
    )
    pick = choose(index, "dinner", prev, nxt, set(), set(), DEFAULT_CONFIG)
    assert pick is not None and pick.restaurant.place_id == "on-the-way" and pick.detour_m == 0


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
    skipped = [n for p in run("area", 14).plans for n in p.notes
               if n.code == "MEALS_SKIPPED_FOR_TRAVEL"]  # fmt: skip
    assert skipped, "the long drive to Town D (over 150 km) takes the time of lunch"


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
        restaurants=restaurants("area"),
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
        restaurants=list(reversed(restaurants("area"))),
    )
    assert engine.to_json(shuffled) == first


def test_lookup_is_used_for_base_order() -> None:
    town_list = towns("area")[:3]
    lookup = TravelLookup(FixedTravelSource(), DEFAULT_CONFIG.walk_max_m)
    eligible = [areas.EligibleBase(t, 100 - i, 5) for i, t in enumerate(town_list)]
    assert areas.order_bases(eligible, lookup)[0].city.city_id == town_list[0].city_id
    assert [b.city.city_id for b in areas.order_bases([], lookup)] == []
