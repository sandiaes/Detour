"""The independent validator: it passes the engine's plans and catches each kind of broken plan.

Each test takes a valid plan and breaks one thing, the way a bug in the engine could.
"""

import dataclasses
from collections.abc import Callable
from datetime import date

import pytest

from detour_api.planner import engine
from detour_api.planner.config import DEFAULT_CONFIG
from detour_api.planner.travel import FixedTravelSource, TravelLookup
from detour_api.planner.types import DayPlan, Generation, Note, Plan, PlannedVisit
from detour_api.planner.validator import validate_generation, validate_plan
from detour_api.travel.types import Mode
from tests.planner_helpers import candidates, request

START = date(2026, 5, 4)


@pytest.fixture(scope="module")
def generation() -> Generation:
    return engine.generate(
        request("city-large", 2, START), candidates("city-large"), FixedTravelSource()
    )


def known_times(plan: Plan) -> dict:  # type: ignore[type-arg]
    by_id = {c.place_id: c for c in candidates("city-large")}
    lookup = TravelLookup(FixedTravelSource(), DEFAULT_CONFIG.walk_max_m)
    for d in plan.days:
        for a, b in zip(d.visits, d.visits[1:], strict=False):
            if a.place_id in by_id and b.place_id in by_id:
                lookup.get(by_id[a.place_id].coord, by_id[b.place_id].coord)
    return lookup.known()


def check(plan: Plan, days: int = 2) -> list[str]:
    by_id = {c.place_id: c for c in candidates("city-large")}
    found = validate_plan(
        plan, request("city-large", days, START), by_id, known_times(plan), DEFAULT_CONFIG
    )
    return [v.code for v in found]


def change_visit(
    plan: Plan, day: int, pos: int, fn: Callable[[PlannedVisit], PlannedVisit]
) -> Plan:
    days = list(plan.days)
    visits = list(days[day].visits)
    visits[pos] = fn(visits[pos])
    days[day] = dataclasses.replace(days[day], visits=tuple(visits))
    return dataclasses.replace(plan, days=tuple(days))


def test_generated_plans_pass(generation: Generation) -> None:
    for plan in generation.plans:
        assert check(plan) == []
    assert validate_generation(generation, DEFAULT_CONFIG) == []


def test_a_manufactured_attraction_is_caught(generation: Generation) -> None:
    plan = change_visit(
        generation.plans[0], 0, 0, lambda v: dataclasses.replace(v, place_id="invented")
    )
    assert "UNKNOWN_PLACE" in check(plan)


def test_a_changed_name_or_point_is_caught(generation: Generation) -> None:
    plan = change_visit(
        generation.plans[0], 0, 1, lambda v: dataclasses.replace(v, name="Nicer name")
    )
    assert check(plan) == ["SNAPSHOT_MISMATCH"]


def test_the_same_place_twice_is_caught(generation: Generation) -> None:
    plan = generation.plans[0]
    twin = plan.days[0].visits[0]
    broken = change_visit(plan, 1, 0, lambda v: dataclasses.replace(
        twin, start_minute=v.start_minute, end_minute=v.start_minute + twin.duration_minutes,
        transfer=v.transfer))  # fmt: skip
    assert "DUPLICATE_VISIT" in check(broken)


def test_a_duration_that_is_not_the_category_default_is_caught(generation: Generation) -> None:
    plan = change_visit(
        generation.plans[0],
        0,
        0,
        lambda v: dataclasses.replace(v, duration_minutes=v.duration_minutes + 1),
    )
    assert set(check(plan)) >= {"DURATION_NOT_DEFAULT", "END_NOT_START_PLUS_DURATION"}


def test_overlapping_items_are_caught(generation: Generation) -> None:
    def early(v: PlannedVisit) -> PlannedVisit:
        return dataclasses.replace(v, start_minute=v.start_minute - 5, end_minute=v.end_minute - 5)

    assert "OVERLAP" in check(change_visit(generation.plans[0], 0, 1, early))


def test_items_outside_the_day_are_caught(generation: Generation) -> None:
    def before(v: PlannedVisit) -> PlannedVisit:
        return dataclasses.replace(v, start_minute=8 * 60, end_minute=8 * 60 + v.duration_minutes)

    assert "BEFORE_DAY_START" in check(change_visit(generation.plans[0], 0, 0, before))
    plan = generation.plans[0]
    last = len(plan.days[0].visits) - 1

    def late(v: PlannedVisit) -> PlannedVisit:
        return dataclasses.replace(v, start_minute=20 * 60, end_minute=20 * 60 + v.duration_minutes)

    assert "AFTER_DAY_END" in check(change_visit(plan, 0, last, late))


def test_an_invented_travel_time_is_caught(generation: Generation) -> None:
    def faster(v: PlannedVisit) -> PlannedVisit:
        assert v.transfer is not None
        leg = dataclasses.replace(v.transfer, seconds=60, minutes=1)
        return dataclasses.replace(v, transfer=leg)

    assert "TRANSFER_NOT_FROM_SOURCE" in check(change_visit(generation.plans[0], 0, 0, faster))


def test_an_estimate_labelled_routed_is_caught(generation: Generation) -> None:
    def relabel(v: PlannedVisit) -> PlannedVisit:
        assert v.transfer is not None
        return dataclasses.replace(v, transfer=dataclasses.replace(v.transfer, confidence="routed"))

    assert "TRANSFER_NOT_FROM_SOURCE" in check(change_visit(generation.plans[0], 0, 0, relabel))


def test_transfer_shape_rules_are_caught(generation: Generation) -> None:
    plan = generation.plans[0]

    def no_leg(v: PlannedVisit) -> PlannedVisit:
        return dataclasses.replace(v, transfer=None)

    def wrong_mode(v: PlannedVisit) -> PlannedVisit:
        assert v.transfer is not None
        other: Mode = "drive" if v.transfer.mode == "walk" else "walk"
        return dataclasses.replace(v, transfer=dataclasses.replace(v.transfer, mode=other))

    def rounded_down(v: PlannedVisit) -> PlannedVisit:
        assert v.transfer is not None
        return dataclasses.replace(
            v, transfer=dataclasses.replace(v.transfer, minutes=v.transfer.minutes - 1)
        )

    last = len(plan.days[0].visits) - 1

    def extra(v: PlannedVisit) -> PlannedVisit:
        return dataclasses.replace(v, transfer=plan.days[0].visits[0].transfer)

    assert "MISSING_TRANSFER" in check(change_visit(plan, 0, 0, no_leg))
    assert "TRANSFER_MODE" in check(change_visit(plan, 0, 0, wrong_mode))
    assert "TRANSFER_MINUTES" in check(change_visit(plan, 0, 0, rounded_down))
    assert "TRANSFER_AFTER_LAST_VISIT" in check(change_visit(plan, 0, last, extra))


def test_reasons_need_a_fixed_template(generation: Generation) -> None:
    plan = generation.plans[0]
    assert "MISSING_REASON" in check(
        change_visit(plan, 0, 0, lambda v: dataclasses.replace(v, reasons=()))
    )
    assert "UNKNOWN_REASON" in check(
        change_visit(plan, 0, 0, lambda v: dataclasses.replace(v, reasons=("BECAUSE_I_SAID_SO",)))
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


def test_generation_rules(generation: Generation) -> None:
    essentials, wider = generation.plans
    same = dataclasses.replace(
        generation, plans=(essentials, dataclasses.replace(essentials, profile="wider"))
    )
    assert "NOT_DISTINCT" in [v.code for v in validate_generation(same, DEFAULT_CONFIG)]
    one_flagged = dataclasses.replace(generation, plans=(essentials,))
    assert "DISTINCT_FLAG" in [v.code for v in validate_generation(one_flagged, DEFAULT_CONFIG)]
    empty = dataclasses.replace(
        wider, days=tuple(DayPlan(d.day_index, d.date, ()) for d in wider.days)
    )
    with_empty = dataclasses.replace(generation, plans=(essentials, empty))
    assert "EMPTY_VARIANT" in [v.code for v in validate_generation(with_empty, DEFAULT_CONFIG)]
    no_version = dataclasses.replace(generation, engine_version="")
    assert "MISSING_VERSION" in [v.code for v in validate_generation(no_version, DEFAULT_CONFIG)]
    one_day = dataclasses.replace(wider, days=(wider.days[0], DayPlan(2, wider.days[1].date, ())))
    small = dataclasses.replace(
        one_day,
        days=(dataclasses.replace(one_day.days[0], visits=one_day.days[0].visits[:1]),
              one_day.days[1]),
    )  # fmt: skip
    small_second = dataclasses.replace(generation, plans=(essentials, small))
    codes = [v.code for v in validate_generation(small_second, DEFAULT_CONFIG)]
    assert "SECOND_VARIANT_TOO_SMALL" in codes
    twins = dataclasses.replace(generation, plans=(essentials, essentials))
    assert "DUPLICATE_PROFILE" in [v.code for v in validate_generation(twins, DEFAULT_CONFIG)]
