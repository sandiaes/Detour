"""The independent validator: it passes the engine's plans and catches each kind of broken plan.

Each test takes a valid plan and breaks one thing, the way a bug in the engine could.
"""

import dataclasses
from collections.abc import Callable
from datetime import date
from typing import Any

import pytest

from detour_api.planner import engine
from detour_api.planner.config import DEFAULT_CONFIG
from detour_api.planner.travel import FixedTravelSource, TravelLookup
from detour_api.planner.types import DayPlan, Generation, Note, Plan, PlannedItem
from detour_api.planner.validator import validate_generation, validate_plan
from detour_api.travel.types import Coord, Mode
from tests.planner_helpers import candidates, request, restaurants, towns

START = date(2026, 5, 4)


@pytest.fixture(scope="module")
def generation() -> Generation:
    return engine.generate(
        request("city-large", 2, START),
        candidates("city-large"),
        FixedTravelSource(),
        restaurants=restaurants("city-large"),
    )


@pytest.fixture(scope="module")
def area_generation() -> Generation:
    return engine.generate(
        request("area", 7, START),
        candidates("area"),
        FixedTravelSource(),
        restaurants=restaurants("area"),
    )


def known_times(plan: Plan, fixture: str = "city-large") -> dict[Any, Any]:
    """What a source without routed answers returns for every leg the plan could use."""
    lookup = TravelLookup(FixedTravelSource(), DEFAULT_CONFIG.walk_max_m)
    for d in plan.days:
        for a, b in zip(d.items, d.items[1:], strict=False):
            lookup.get(Coord.from_degrees(a.lat, a.lon), Coord.from_degrees(b.lat, b.lon))
    cities = towns(fixture)
    for t1 in cities:
        for t2 in cities:
            lookup.get(t1.coord, t2.coord)
    return lookup.known()


def check(plan: Plan, days: int = 2, fixture: str = "city-large") -> list[str]:
    by_id = {c.place_id: c for c in candidates(fixture)}
    eat = {r.place_id: r for r in restaurants(fixture)}
    found = validate_plan(
        plan,
        request(fixture, days, START),
        by_id,
        eat,
        known_times(plan, fixture),
        DEFAULT_CONFIG,
    )
    return [v.code for v in found]


def nth(plan: Plan, day: int, kind: str, n: int = 0) -> int:
    """The position in the day's items of the n-th visit or meal (negative n counts back)."""
    positions = [i for i, item in enumerate(plan.days[day].items) if item.kind == kind]
    return positions[n]


def change_item(plan: Plan, day: int, pos: int, fn: Callable[[PlannedItem], PlannedItem]) -> Plan:
    days = list(plan.days)
    items = list(days[day].items)
    items[pos] = fn(items[pos])
    days[day] = dataclasses.replace(days[day], items=tuple(items))
    return dataclasses.replace(plan, days=tuple(days))


def change_day(plan: Plan, day: int, **changes: Any) -> Plan:
    days = list(plan.days)
    days[day] = dataclasses.replace(days[day], **changes)
    return dataclasses.replace(plan, days=tuple(days))


def test_generated_plans_pass(generation: Generation, area_generation: Generation) -> None:
    for plan in generation.plans:
        assert check(plan) == []
        assert all(d.meals for d in plan.days), "every day with visits has its meals"
    for plan in area_generation.plans:
        assert check(plan, 7, "area") == []
    assert validate_generation(generation, DEFAULT_CONFIG) == []
    assert validate_generation(area_generation, DEFAULT_CONFIG) == []


# -- visits --------------------------------------------------------------------------------------


def test_a_manufactured_attraction_is_caught(generation: Generation) -> None:
    plan = generation.plans[0]
    plan = change_item(
        plan, 0, nth(plan, 0, "visit"), lambda v: dataclasses.replace(v, place_id="invented")
    )
    assert "UNKNOWN_PLACE" in check(plan)


def test_a_changed_name_or_point_is_caught(generation: Generation) -> None:
    plan = generation.plans[0]
    plan = change_item(
        plan, 0, nth(plan, 0, "visit", 1), lambda v: dataclasses.replace(v, name="Nicer name")
    )
    assert check(plan) == ["SNAPSHOT_MISMATCH"]


def test_the_same_place_twice_is_caught(generation: Generation) -> None:
    plan = generation.plans[0]
    twin = plan.days[0].items[nth(plan, 0, "visit")]
    broken = change_item(plan, 1, nth(plan, 1, "visit"), lambda v: dataclasses.replace(
        twin, start_minute=v.start_minute, end_minute=v.start_minute + twin.duration_minutes,
        transfer=v.transfer))  # fmt: skip
    assert "DUPLICATE_VISIT" in check(broken)


def test_a_duration_that_is_not_the_category_default_is_caught(generation: Generation) -> None:
    plan = generation.plans[0]
    plan = change_item(
        plan,
        0,
        nth(plan, 0, "visit"),
        lambda v: dataclasses.replace(v, duration_minutes=v.duration_minutes + 1),
    )
    assert set(check(plan)) >= {"DURATION_NOT_DEFAULT", "END_NOT_START_PLUS_DURATION"}


def test_overlapping_items_are_caught(generation: Generation) -> None:
    def early(v: PlannedItem) -> PlannedItem:
        return dataclasses.replace(v, start_minute=v.start_minute - 5, end_minute=v.end_minute - 5)

    plan = generation.plans[0]
    assert "OVERLAP" in check(change_item(plan, 0, nth(plan, 0, "visit", 1), early))


def test_items_outside_the_day_are_caught(generation: Generation) -> None:
    def before(v: PlannedItem) -> PlannedItem:
        return dataclasses.replace(v, start_minute=8 * 60, end_minute=8 * 60 + v.duration_minutes)

    plan = generation.plans[0]
    assert "BEFORE_DAY_START" in check(change_item(plan, 0, 0, before))
    last = len(plan.days[0].items) - 1

    def late(v: PlannedItem) -> PlannedItem:
        return dataclasses.replace(v, start_minute=20 * 60, end_minute=20 * 60 + v.duration_minutes)

    assert "AFTER_DAY_END" in check(change_item(plan, 0, last, late))


# -- meals ---------------------------------------------------------------------------------------


def test_a_meal_outside_its_window_is_caught(generation: Generation) -> None:
    plan = generation.plans[0]
    lunch = nth(plan, 0, "meal")
    assert plan.days[0].items[lunch].meal_type == "lunch"

    def early(m: PlannedItem) -> PlannedItem:
        return dataclasses.replace(m, start_minute=11 * 60, end_minute=11 * 60 + 60)

    assert "MEAL_OUTSIDE_WINDOW" in check(change_item(plan, 0, lunch, early))

    def too_long_into_the_afternoon(m: PlannedItem) -> PlannedItem:
        return dataclasses.replace(m, start_minute=14 * 60, end_minute=15 * 60)

    assert "MEAL_OUTSIDE_WINDOW" in check(change_item(plan, 0, lunch, too_long_into_the_afternoon))


def test_meal_length_type_and_venue_rules_are_caught(generation: Generation) -> None:
    plan = generation.plans[0]
    lunch = nth(plan, 0, "meal")
    longer = change_item(
        plan,
        0,
        lunch,
        lambda m: dataclasses.replace(m, end_minute=m.end_minute + 5, duration_minutes=65),
    )
    assert "MEAL_LENGTH" in check(longer)
    breakfast = change_item(plan, 0, lunch, lambda m: dataclasses.replace(m, meal_type="breakfast"))
    assert "MEAL_TYPE_NOT_PLANNED" in check(breakfast)  # Essentials plans lunch and dinner
    cafe = next(r for r in restaurants("city-large") if r.venue_type == "cafe")
    at_a_cafe = change_item(plan, 0, lunch, lambda m: dataclasses.replace(
        m, place_id=cafe.place_id, name=cafe.name, lat=cafe.lat, lon=cafe.lon, category="cafe",
        cuisines=cafe.cuisines))  # fmt: skip
    assert "VENUE_DOES_NOT_SERVE_MEAL" in check(at_a_cafe)  # a cafe serves breakfast and snacks


def test_a_manufactured_place_to_eat_is_caught(generation: Generation) -> None:
    plan = generation.plans[0]
    lunch = nth(plan, 0, "meal")
    invented = change_item(plan, 0, lunch, lambda m: dataclasses.replace(m, place_id="nowhere"))
    assert "UNKNOWN_RESTAURANT" in check(invented)
    renamed = change_item(plan, 0, lunch, lambda m: dataclasses.replace(m, cuisines=("fusion",)))
    assert "SNAPSHOT_MISMATCH" in check(renamed)


def test_the_same_place_to_eat_twice_a_day_and_unexplained_repeats_are_caught(
    generation: Generation,
) -> None:
    plan = generation.plans[0]
    lunch = plan.days[0].items[nth(plan, 0, "meal")]
    dinner_pos = nth(plan, 0, "meal", -1)
    same_place = change_item(plan, 0, dinner_pos, lambda m: dataclasses.replace(
        m, place_id=lunch.place_id, name=lunch.name, lat=lunch.lat, lon=lunch.lon,
        cuisines=lunch.cuisines))  # fmt: skip
    assert "RESTAURANT_TWICE_A_DAY" in check(same_place)
    next_day = change_item(plan, 1, nth(plan, 1, "meal"), lambda m: dataclasses.replace(
        m, place_id=lunch.place_id, name=lunch.name, lat=lunch.lat, lon=lunch.lon,
        cuisines=lunch.cuisines))  # fmt: skip
    assert "REPEATED_PLACE_REASON" in check(next_day)  # repeated without saying so


def test_meals_without_visits_and_twice_the_same_meal_are_caught(generation: Generation) -> None:
    plan = generation.plans[0]
    meals_only = change_day(plan, 0, items=plan.days[0].meals)
    assert "MEALS_WITHOUT_VISITS" in check(meals_only)
    dinner = nth(plan, 0, "meal", -1)
    two_lunches = change_item(plan, 0, dinner, lambda m: dataclasses.replace(m, meal_type="lunch"))
    assert "MEAL_TWICE_A_DAY" in check(two_lunches)


# -- transfers -----------------------------------------------------------------------------------


def test_an_invented_travel_time_is_caught(generation: Generation) -> None:
    def faster(v: PlannedItem) -> PlannedItem:
        assert v.transfer is not None
        leg = dataclasses.replace(v.transfer, seconds=60, minutes=1)
        return dataclasses.replace(v, transfer=leg)

    assert "TRANSFER_NOT_FROM_SOURCE" in check(change_item(generation.plans[0], 0, 0, faster))


def test_an_estimate_labelled_routed_is_caught(generation: Generation) -> None:
    def relabel(v: PlannedItem) -> PlannedItem:
        assert v.transfer is not None
        return dataclasses.replace(v, transfer=dataclasses.replace(v.transfer, confidence="routed"))

    assert "TRANSFER_NOT_FROM_SOURCE" in check(change_item(generation.plans[0], 0, 0, relabel))


def test_transfer_shape_rules_are_caught(generation: Generation) -> None:
    plan = generation.plans[0]

    def no_leg(v: PlannedItem) -> PlannedItem:
        return dataclasses.replace(v, transfer=None)

    def wrong_mode(v: PlannedItem) -> PlannedItem:
        assert v.transfer is not None
        other: Mode = "drive" if v.transfer.mode == "walk" else "walk"
        return dataclasses.replace(v, transfer=dataclasses.replace(v.transfer, mode=other))

    def rounded_down(v: PlannedItem) -> PlannedItem:
        assert v.transfer is not None
        return dataclasses.replace(
            v, transfer=dataclasses.replace(v.transfer, minutes=v.transfer.minutes - 1)
        )

    last = len(plan.days[0].items) - 1

    def extra(v: PlannedItem) -> PlannedItem:
        return dataclasses.replace(v, transfer=plan.days[0].items[0].transfer)

    assert "MISSING_TRANSFER" in check(change_item(plan, 0, 0, no_leg))
    assert "TRANSFER_MODE" in check(change_item(plan, 0, 0, wrong_mode))
    assert "TRANSFER_MINUTES" in check(change_item(plan, 0, 0, rounded_down))
    assert "TRANSFER_AFTER_LAST_ITEM" in check(change_item(plan, 0, last, extra))


# -- areas ---------------------------------------------------------------------------------------


def test_area_bases_and_inter_city_legs_are_checked(area_generation: Generation) -> None:
    plan = area_generation.plans[0]
    moved = next(i for i, d in enumerate(plan.days) if d.arrival is not None)
    assert check(plan, 7, "area") == []
    no_drive = change_day(plan, moved, arrival=None)
    assert "ARRIVAL_MISMATCH" in check(no_drive, 7, "area")
    leg = plan.days[moved].arrival
    assert leg is not None
    stray = change_day(plan, 0, arrival=leg)
    assert "ARRIVAL_MISMATCH" in check(stray, 7, "area")
    shorter = change_day(plan, moved, arrival=dataclasses.replace(leg, seconds=60, minutes=1))
    assert "ARRIVAL_NOT_FROM_SOURCE" in check(shorter, 7, "area")
    nowhere = change_day(plan, moved, base_city_id=123)
    assert "UNKNOWN_BASE" in check(nowhere, 7, "area")


def test_the_first_item_after_a_drive_waits_for_it(area_generation: Generation) -> None:
    plan = area_generation.plans[0]
    moved = next(i for i, d in enumerate(plan.days) if d.arrival is not None)
    leg = plan.days[moved].arrival
    assert leg is not None
    assert plan.days[moved].items[0].start_minute >= 9 * 60 + leg.minutes

    def at_nine(v: PlannedItem) -> PlannedItem:
        return dataclasses.replace(v, start_minute=9 * 60, end_minute=9 * 60 + v.duration_minutes)

    assert "BEFORE_DAY_START" in check(change_item(plan, moved, 0, at_nine), 7, "area")


def test_a_city_trip_keeps_its_one_base(generation: Generation) -> None:
    plan = generation.plans[0]
    assert "WRONG_BASE" in check(change_day(plan, 1, base_city_id=1))


# -- reasons, days, statistics, generations --------------------------------------------------------


def test_reasons_need_a_fixed_template(generation: Generation) -> None:
    plan = generation.plans[0]
    assert "MISSING_REASON" in check(
        change_item(plan, 0, 0, lambda v: dataclasses.replace(v, reasons=()))
    )
    assert "UNKNOWN_REASON" in check(
        change_item(plan, 0, 0, lambda v: dataclasses.replace(v, reasons=("BECAUSE_I_SAID_SO",)))
    )
    bad_note = dataclasses.replace(plan, notes=(*plan.notes, Note("FREE_TEXT")))
    missing_param = dataclasses.replace(plan, notes=(Note("PROFILE_ESSENTIALS"),))
    assert "BAD_NOTE" in check(bad_note) and "BAD_NOTE" in check(missing_param)


def test_days_and_dates_are_checked(generation: Generation) -> None:
    plan = generation.plans[0]
    assert "DAY_COUNT" in check(plan, days=3)
    swapped = dataclasses.replace(plan, days=(plan.days[1], plan.days[0]))
    assert "DAY_ORDER" in check(swapped)
    wrong_date = dataclasses.replace(
        plan, days=(dataclasses.replace(plan.days[0], date=date(2026, 1, 1)), plan.days[1])
    )
    assert "DAY_DATE" in check(wrong_date)


def test_statistics_must_match_the_plan(generation: Generation) -> None:
    plan = generation.plans[0]
    inflated = dataclasses.replace(plan, stats=dataclasses.replace(plan.stats, visits=999))
    assert check(inflated) == ["STATS_MISMATCH"]
    no_meals = dataclasses.replace(plan, stats=dataclasses.replace(plan.stats, meals=0))
    assert check(no_meals) == ["STATS_MISMATCH"]


def test_generation_rules(generation: Generation) -> None:
    essentials, wider = generation.plans
    same = dataclasses.replace(
        generation, plans=(essentials, dataclasses.replace(essentials, profile="wider"))
    )
    assert "NOT_DISTINCT" in [v.code for v in validate_generation(same, DEFAULT_CONFIG)]
    one_flagged = dataclasses.replace(generation, plans=(essentials,))
    assert "DISTINCT_FLAG" in [v.code for v in validate_generation(one_flagged, DEFAULT_CONFIG)]
    empty = dataclasses.replace(
        wider,
        days=tuple(dataclasses.replace(d, items=()) for d in wider.days),
    )
    with_empty = dataclasses.replace(generation, plans=(essentials, empty))
    assert "EMPTY_VARIANT" in [v.code for v in validate_generation(with_empty, DEFAULT_CONFIG)]
    no_version = dataclasses.replace(generation, engine_version="")
    assert "MISSING_VERSION" in [v.code for v in validate_generation(no_version, DEFAULT_CONFIG)]
    first_visit = wider.days[0].visits[:1]
    small = dataclasses.replace(
        wider,
        days=(
            dataclasses.replace(wider.days[0], items=first_visit),
            DayPlan(2, wider.days[1].date, (), wider.days[1].base_city_id),
        ),
    )
    small_second = dataclasses.replace(generation, plans=(essentials, small))
    codes = [v.code for v in validate_generation(small_second, DEFAULT_CONFIG)]
    assert "SECOND_VARIANT_TOO_SMALL" in codes
    twins = dataclasses.replace(generation, plans=(essentials, essentials))
    assert "DUPLICATE_PROFILE" in [v.code for v in validate_generation(twins, DEFAULT_CONFIG)]


def test_overlapping_plans_pass_when_their_bases_differ(area_generation: Generation) -> None:
    essentials, wider = area_generation.plans
    assert essentials.allocation() != wider.allocation()
    # The same visits under a different division of days are still two distinct plans.
    renamed = dataclasses.replace(essentials, profile="wider", days=tuple(
        dataclasses.replace(d, base_city_id=w.base_city_id)
        for d, w in zip(essentials.days, wider.days, strict=True)))  # fmt: skip
    pair = dataclasses.replace(area_generation, plans=(essentials, renamed))
    assert "NOT_DISTINCT" not in [v.code for v in validate_generation(pair, DEFAULT_CONFIG)]
