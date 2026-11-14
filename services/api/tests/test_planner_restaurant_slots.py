"""Adding a restaurant: scoring every day and meal slot, and placing it (Phase 8, ADR 019), on the
synthetic fixtures. No database and no network: the travel source returns labelled estimates.
"""

from dataclasses import replace
from datetime import date

import pytest

from detour_api.planner import diff, recalc
from detour_api.planner.config import DEFAULT_CONFIG, MEAL_TYPES, MealType
from detour_api.planner.recalc import Entry, RDay, Revision, RPlan
from detour_api.planner.restaurant_slots import Dining, add_restaurant, suggest
from detour_api.planner.revision_validator import validate_revision
from detour_api.planner.travel import FixedTravelSource
from detour_api.planner.types import PlanningImpossible
from tests import planner_helpers as ph
from tests.recalc_helpers import generated, lock, recalc_input

CANDS = ph.candidates("city-large")
RESTS = ph.restaurants("city-large")
CONFIG = DEFAULT_CONFIG


def _world(profile: str = "essentials", days: int = 3) -> tuple[recalc.RecalcInput, RPlan]:
    req = ph.request("city-large", days, date(2027, 5, 1))
    plan, rp = generated(req, CANDS, RESTS, profile)
    return recalc_input(plan, rp, req, CANDS, RESTS), rp


def _near(rp: RPlan, day: int, metres: float = 150.0) -> tuple[float, float]:
    """A point a little north of the first visit of a day."""
    v = rp.days[day - 1].visits[0]
    return v.lat + metres / 111_320.0, v.lon


def _pin(
    lat: float,
    lon: float,
    *,
    meals: tuple[str, ...] | None = ("dinner", "lunch"),
    cuisines: tuple[str, ...] | None = None,
    name: str = "Pin Bistro",
) -> Dining:
    return Dining(
        name=name, lat=lat, lon=lon, cuisines=cuisines, meal_types=meals, user_place_id="user-1"
    )


def _validate(inp: recalc.RecalcInput, rev: Revision, dining: Dining) -> list[object]:
    return list(
        validate_revision(
            inp.plan,
            rev,
            added=dining.key,
            removed=None,
            candidates={c.place_id: c for c in CANDS},
            restaurants={r.place_id: r for r in RESTS},
            config=CONFIG,
            added_meal=dining,
        )
    )


def _place(inp: recalc.RecalcInput, dining: Dining, s: object) -> Revision:
    from detour_api.planner.restaurant_slots import Suggestion

    assert isinstance(s, Suggestion)
    return add_restaurant(
        inp, dining, s.day_index, s.meal_type, s.after_item_id, FixedTravelSource()
    )


def _day_of(rev: Revision, key: str) -> tuple[RDay, Entry]:
    for d in rev.plan.days:
        for e in d.items:
            if e.key == key:
                return d, e
    raise AssertionError(key)


def test_at_most_three_distinct_slots_best_first() -> None:
    inp, rp = _world()
    dining = _pin(*_near(rp, 2))
    result = suggest(inp, dining, FixedTravelSource(), config=CONFIG)
    assert 1 <= len(result.suggestions) <= 3
    slots = [(s.day_index, s.meal_type) for s in result.suggestions]
    assert len(set(slots)) == len(slots)
    costs = [s.cost for s in result.suggestions]
    assert costs == sorted(costs)
    assert result.slots_considered >= len(result.suggestions)


def test_scoring_prefers_the_slot_where_the_traveller_already_is() -> None:
    inp, rp = _world()
    for day in (1, 2, 3):
        # The stop before lunch: a place next to it, serving lunch only, belongs in that lunch.
        d = rp.days[day - 1]
        lunch = next(i for i, e in enumerate(d.items) if e.meal_type == "lunch")
        before = d.items[lunch - 1]
        dining = _pin(before.lat + 0.0007, before.lon, meals=("lunch",), name=f"Next to {day}")
        offered = suggest(inp, dining, FixedTravelSource(), config=CONFIG).suggestions
        # The lunch next to the pin is among the suggestions with a small detour. (The cheapest
        # slot can be another day's lunch when this day's lunch is late: cost also counts retiming.)
        here = next(s for s in offered if (s.day_index, s.meal_type) == (day, "lunch"))
        assert here.detour_m < 1_000
        codes = [r.code for r in here.reasons]
        assert "SLOT_NEAR_PREVIOUS" in codes or "SLOT_NEAR_NEXT" in codes


def test_a_far_place_costs_more_than_a_near_one_in_the_same_slot() -> None:
    inp, rp = _world()
    d = rp.days[1]
    lunch = next(i for i, e in enumerate(d.items) if e.meal_type == "lunch")
    before = d.items[lunch - 1]
    near = _pin(before.lat + 0.0007, before.lon, meals=("lunch",))
    far = _pin(before.lat + 0.03, before.lon, meals=("lunch",), name="Far Bistro")
    a = suggest(inp, near, FixedTravelSource(), day=2, meal="lunch", config=CONFIG)
    b = suggest(inp, far, FixedTravelSource(), day=2, meal="lunch", config=CONFIG)
    assert a.suggestions[0].cost < b.suggestions[0].cost
    assert a.suggestions[0].detour_m < b.suggestions[0].detour_m


def test_scoring_is_deterministic() -> None:
    inp, rp = _world("wider", 4)
    dining = _pin(*_near(rp, 3), cuisines=("greek",))
    a = suggest(inp, dining, FixedTravelSource(), config=CONFIG)
    b = suggest(inp, dining, FixedTravelSource(), config=CONFIG)
    assert a == b


@pytest.mark.parametrize("profile", ["essentials", "wider"])
@pytest.mark.parametrize(
    "meals",
    [None, ("lunch",), ("dinner",), ("breakfast", "snack"), ("snack",), ("breakfast",)],
)
def test_every_suggestion_respects_its_meal_window_and_the_day(
    profile: str, meals: tuple[str, ...] | None
) -> None:
    inp, rp = _world(profile)
    profile_end = CONFIG.profile(profile).day_end_minute  # type: ignore[arg-type]
    for day in (1, 2, 3):
        dining = _pin(*_near(rp, day, 400.0), meals=meals)
        result = suggest(inp, dining, FixedTravelSource(), config=CONFIG)
        assert result.suggestions, result.issues
        for s in result.suggestions:
            w = CONFIG.meal_window(s.meal_type)
            assert w.start_minute <= s.start_minute and s.end_minute <= w.end_minute
            assert s.end_minute <= min(profile_end, CONFIG.day_window_end_minute)
            if meals is not None:
                assert s.meal_type in meals
            rev = _place(inp, dining, s)
            assert _validate(inp, rev, dining) == []
            d, e = _day_of(rev, dining.key)
            assert (e.start_minute, e.end_minute) == (s.start_minute, s.end_minute)
            assert e.origin == "user" and not e.locked and not e.floating
            assert e.meal_type == s.meal_type and d.day_index == s.day_index
            assert "ADDED_BY_YOU" in e.reasons


def test_placing_a_restaurant_leaves_every_visit_on_its_day() -> None:
    inp, rp = _world("wider", 3)
    dining = _pin(*_near(rp, 2), meals=None)
    before = {e.key: d.day_index for d in rp.days for e in d.visits}
    for s in suggest(inp, dining, FixedTravelSource(), config=CONFIG).suggestions:
        rev = _place(inp, dining, s)
        after = {e.key: d.day_index for d in rev.plan.days for e in d.visits}
        assert after == before  # none left out, none moved to another day
        changed = diff.compare(rp, rev.plan)
        assert not changed.moved
        assert [a.key for a in changed.added if a.kind == "meal"] == [dining.key]
        # "Which items move" is what the suggestion promised.
        moved = {(m.name, m.old_start_minute, m.new_start_minute) for m in s.shifts}
        retimed = {
            (r.name, r.old_start_minute, r.new_start_minute)
            for r in changed.retimed
            if r.day == s.day_index
        }
        assert moved <= retimed


def test_a_restaurant_replaces_the_meal_of_its_type() -> None:
    inp, rp = _world()
    lunch = next(e for e in rp.days[0].items if e.kind == "meal" and e.meal_type == "lunch")
    dining = _pin(lunch.lat + 0.0005, lunch.lon, meals=("lunch",))
    s = suggest(inp, dining, FixedTravelSource(), day=1, config=CONFIG).suggestions[0]
    assert s.meal_type == "lunch" and s.replaces == lunch.name
    assert "SLOT_REPLACES" in [r.code for r in s.reasons]
    rev = _place(inp, dining, s)
    day = rev.plan.days[0]
    assert [e.meal_type for e in day.items if e.kind == "meal"].count("lunch") == 1
    assert lunch.key not in {e.key for e in day.items}
    assert {n.code for n in rev.notes} >= {"RESTAURANT_ADDED", "MEAL_REPLACED"}
    assert rev.stats.meals == sum(1 for d in rp.days for e in d.items if e.kind == "meal")


def test_an_empty_slot_is_filled_without_replacing() -> None:
    inp, rp = _world("essentials")  # Essentials plans lunch and dinner only
    dining = _pin(*_near(rp, 1), meals=("snack",))
    s = suggest(inp, dining, FixedTravelSource(), config=CONFIG).suggestions[0]
    assert s.meal_type == "snack" and s.replaces is None
    assert "SLOT_EMPTY" in [r.code for r in s.reasons]
    rev = _place(inp, dining, s)
    assert _validate(inp, rev, dining) == []
    meals = sum(1 for d in rev.plan.days for e in d.items if e.kind == "meal")
    assert (
        meals == rev.stats.meals == sum(1 for d in rp.days for e in d.items if e.kind == "meal") + 1
    )


def test_unknown_meal_types_are_judged_by_place_and_timing_and_cost_more() -> None:
    inp, rp = _world()
    known = _pin(*_near(rp, 1), meals=("dinner", "lunch"))
    unknown = _pin(*_near(rp, 1), meals=None)
    a = suggest(inp, known, FixedTravelSource(), day=1, meal="dinner", config=CONFIG)
    b = suggest(inp, unknown, FixedTravelSource(), day=1, meal="dinner", config=CONFIG)
    assert (
        b.suggestions[0].cost
        == a.suggestions[0].cost + recalc.DEFAULT_RECALC.slot_meal_unknown_cost
    )
    assert "SLOT_MEAL_UNKNOWN" in [r.code for r in b.suggestions[0].reasons]
    assert "SLOT_SERVES_MEAL_YOU" in [r.code for r in a.suggestions[0].reasons]
    # With the meal types unknown every meal type is a slot.
    all_meals = {
        s.meal_type for s in suggest(inp, unknown, FixedTravelSource(), config=CONFIG).suggestions
    }
    assert all_meals <= set(MEAL_TYPES)


def test_a_repeated_cuisine_costs_more_than_a_new_one() -> None:
    inp, rp = _world()
    lunch = next(e for e in rp.days[0].items if e.kind == "meal" and e.cuisines)
    day = next(d.day_index for d in rp.days if lunch in d.items)
    same = _pin(
        lunch.lat, lunch.lon + 0.001, cuisines=tuple(lunch.cuisines or ()), meals=("dinner",)
    )
    other = _pin(lunch.lat, lunch.lon + 0.001, cuisines=("zzz_new_cuisine",), meals=("dinner",))
    a = suggest(inp, same, FixedTravelSource(), day=day, meal="dinner", config=CONFIG)
    b = suggest(inp, other, FixedTravelSource(), day=day, meal="dinner", config=CONFIG)
    assert (
        a.suggestions[0].cost
        == b.suggestions[0].cost + recalc.DEFAULT_RECALC.slot_cuisine_repeat_cost
    )
    assert "SLOT_CUISINE_REPEAT" in [r.code for r in a.suggestions[0].reasons]
    assert "SLOT_CUISINE_NEW" in [r.code for r in b.suggestions[0].reasons]


def test_no_cuisine_stays_not_specified_and_no_price_or_rating_appears() -> None:
    inp, rp = _world()
    dining = _pin(*_near(rp, 1), cuisines=None)
    s = suggest(inp, dining, FixedTravelSource(), config=CONFIG).suggestions[0]
    assert "SLOT_CUISINE_UNKNOWN" in [r.code for r in s.reasons]
    rev = _place(inp, dining, s)
    _, e = _day_of(rev, dining.key)
    assert e.cuisines is None  # the app shows "Cuisine not specified"
    assert "CUISINE_NOT_SPECIFIED_BY_YOU" in e.reasons
    from detour_api.planner.reasons import SLOT_TEMPLATES

    text = " ".join(SLOT_TEMPLATES.values()).lower()
    assert not any(w in text for w in ("price", "rating", "review", "open until", "book"))


def test_a_meal_the_user_fixed_keeps_its_slot() -> None:
    inp, rp = _world()
    first = _pin(*_near(rp, 1), meals=("dinner",), name="First")
    s = suggest(inp, first, FixedTravelSource(), day=1, meal="dinner", config=CONFIG).suggestions[0]
    rev = _place(inp, first, s)
    inp2 = replace(inp, plan=rev.plan)
    second = replace(_pin(*_near(rp, 1), meals=("dinner",), name="Second"), user_place_id="user-2")
    with pytest.raises(PlanningImpossible) as exc:
        add_restaurant(inp2, second, 1, "dinner", None, FixedTravelSource())
    assert exc.value.issues[0].code == "MEAL_SLOT_TAKEN"
    # The slot is not offered, and the other days still are.
    result = suggest(inp2, second, FixedTravelSource(), meal="dinner", config=CONFIG)
    assert 1 not in {x.day_index for x in result.suggestions}
    # Locked meals are fixed too.
    dinner = next(e for e in rp.days[1].items if e.meal_type == "dinner")
    locked = lock(rp, {dinner.key})
    inp3 = replace(inp, plan=locked)
    result = suggest(inp3, second, FixedTravelSource(), day=2, meal="dinner", config=CONFIG)
    assert result.suggestions == ()


def test_the_restaurant_is_not_added_twice_and_must_serve_the_meal() -> None:
    inp, rp = _world()
    planned = next(e for e in rp.days[0].items if e.kind == "meal")
    already = Dining(
        name=planned.name,
        lat=planned.lat,
        lon=planned.lon,
        venue_type=planned.category,
        meal_types=("dinner", "lunch"),
        place_id=planned.place_id,
    )
    with pytest.raises(PlanningImpossible) as exc:
        suggest(inp, already, FixedTravelSource(), config=CONFIG)
    assert exc.value.issues[0].code == "ALREADY_IN_PLAN"
    cafe = _pin(*_near(rp, 1), meals=("breakfast", "snack"))
    with pytest.raises(PlanningImpossible) as exc2:
        suggest(inp, cafe, FixedTravelSource(), meal="dinner", config=CONFIG)
    assert exc2.value.issues[0].code == "RESTAURANT_DOES_NOT_SERVE_MEAL"
    with pytest.raises(PlanningImpossible) as exc3:
        add_restaurant(inp, cafe, 1, "dinner", None, FixedTravelSource())
    assert exc3.value.issues[0].code == "RESTAURANT_DOES_NOT_SERVE_MEAL"


def test_a_day_without_visits_and_a_slot_that_no_longer_exists_are_explained() -> None:
    req = ph.request("city-large", 3, date(2027, 5, 1))
    plan, rp = generated(req, CANDS, RESTS)
    empty = replace(rp.days[2], items=())
    inp = recalc_input(plan, RPlan(rp.profile, (*rp.days[:2], empty)), req, CANDS, RESTS)
    dining = _pin(*_near(rp, 1))
    result = suggest(inp, dining, FixedTravelSource(), day=3, config=CONFIG)
    assert result.suggestions == () and result.issues[0].code == "DAY_HAS_NO_VISITS"
    with pytest.raises(PlanningImpossible) as exc:
        add_restaurant(inp, dining, 1, "dinner", "item-that-is-gone", FixedTravelSource())
    assert exc.value.issues[0].code == "SLOT_NOT_FOUND"


def test_a_meal_that_cannot_fit_its_window_is_refused_not_squeezed() -> None:
    inp, rp = _world()
    day = rp.days[0]
    # A locked visit ends the day at 21:25: a dinner after it cannot end inside its window.
    last = next(e for e in reversed(day.items) if e.kind == "visit")
    pinned = replace(last, locked=True, start_minute=21 * 60 + 5, end_minute=21 * 60 + 25)
    items = tuple(e for e in day.items if not (e.kind == "meal" and e.meal_type == "dinner"))
    items = tuple(pinned if e.key == last.key else e for e in items)
    squeezed = RDay(day.day_index, day.date, day.base_city_id, day.base_city_name, items, None)
    inp2 = replace(inp, plan=RPlan(rp.profile, (squeezed, *rp.days[1:])))
    dining = _pin(last.lat, last.lon, meals=("dinner",))
    with pytest.raises(PlanningImpossible) as exc:
        add_restaurant(inp2, dining, 1, "dinner", last.item_id, FixedTravelSource())
    assert exc.value.issues[0].code == "MEAL_DOES_NOT_FIT"
    # And it is not offered as a suggestion either (nothing is squeezed to fit).
    offered = suggest(inp2, dining, FixedTravelSource(), day=1, config=CONFIG)
    assert all(s.start_minute + 90 <= 22 * 60 for s in offered.suggestions)
    assert offered.suggestions == () or offered.suggestions[0].after_item_id != last.item_id


def test_the_validator_catches_a_meal_outside_its_window_or_the_day() -> None:
    inp, rp = _world()
    dining = _pin(*_near(rp, 1), meals=("lunch",))
    s = suggest(inp, dining, FixedTravelSource(), day=1, config=CONFIG).suggestions[0]
    rev = _place(inp, dining, s)

    def tampered(start: int, minutes: int | None = None) -> Revision:
        days = []
        for d in rev.plan.days:
            items = tuple(
                replace(
                    e,
                    start_minute=start,
                    end_minute=start + (minutes or e.duration_minutes),
                    duration_minutes=minutes or e.duration_minutes,
                )
                if e.key == dining.key
                else e
                for e in d.items
            )
            days.append(replace(d, items=items))
        return replace(rev, plan=RPlan(rev.plan.profile, tuple(days)))

    codes = {v.code for v in _validate(inp, tampered(11 * 60), dining)}  # type: ignore[attr-defined]
    assert "MEAL_OUTSIDE_WINDOW" in codes
    codes = {v.code for v in _validate(inp, tampered(14 * 60 + 45), dining)}  # type: ignore[attr-defined]
    assert "MEAL_OUTSIDE_WINDOW" in codes  # starts inside, ends after 15:00
    codes = {v.code for v in _validate(inp, tampered(21 * 60 + 40), dining)}  # type: ignore[attr-defined]
    assert {"MEAL_OUTSIDE_WINDOW", "AFTER_DAY_END"} <= codes
    assert _validate(inp, rev, dining) == []


def test_the_restaurant_is_never_placed_with_the_wrong_meal_type() -> None:
    inp, rp = _world()
    dining = _pin(*_near(rp, 1), meals=("lunch",))
    for s in suggest(inp, dining, FixedTravelSource(), config=CONFIG).suggestions:
        assert s.meal_type == "lunch"
    meal_types: tuple[MealType, ...] = MEAL_TYPES
    assert "lunch" in meal_types


def test_a_later_recalculation_keeps_the_added_restaurant_where_it_is() -> None:
    from detour_api.planner.recalc import Addition

    inp, rp = _world("wider", 3)
    dining = _pin(*_near(rp, 2), meals=("lunch", "dinner"), cuisines=("greek",))
    s = suggest(inp, dining, FixedTravelSource(), config=CONFIG).suggestions[0]
    placed = _place(inp, dining, s)
    _, meal = _day_of(placed, dining.key)
    inp2 = replace(inp, plan=placed.plan)
    used = {e.place_id for d in placed.plan.days for e in d.items}
    sight = next(c for c in CANDS if c.place_id not in used)
    addition = Addition(
        key=recalc.entry_key("visit", sight.place_id, None),
        name=sight.name,
        lat=sight.lat,
        lon=sight.lon,
        duration_minutes=45,
        duration_source="category_default",
        place_id=sight.place_id,
        category=sight.category,
    )
    rev = recalc.add_place(inp2, addition, FixedTravelSource())
    day_after, meal_after = _day_of(rev, dining.key)
    assert (day_after.day_index, meal_after.start_minute, meal_after.end_minute) == (
        s.day_index,
        meal.start_minute,
        meal.end_minute,
    )
    assert meal_after.origin == "user" and meal_after.cuisines == ("greek",)
    problems = validate_revision(
        placed.plan,
        rev,
        added=addition.key,
        removed=None,
        candidates={c.place_id: c for c in CANDS},
        restaurants={r.place_id: r for r in RESTS},
        config=CONFIG,
    )
    assert problems == []


def test_new_cuisine_is_only_claimed_when_it_is_true() -> None:
    inp, rp = _world()
    planned = next(e for d in rp.days for e in d.items if e.kind == "meal" and e.cuisines)
    day = next(d.day_index for d in rp.days if planned in d.items)
    meal = planned.meal_type
    assert meal is not None
    sf = FixedTravelSource()
    # The cuisine of another meal of the plan: repeated, so no NEW_CUISINE reason.
    repeat = _pin(*_near(rp, day), cuisines=tuple(planned.cuisines or ()), meals=("snack",))
    s = suggest(inp, repeat, sf, day=day, meal="snack", config=CONFIG).suggestions[0]
    _, e = _day_of(_place(inp, repeat, s), repeat.key)
    assert "NEW_CUISINE" not in e.reasons and "CUISINE_NOT_SPECIFIED_BY_YOU" not in e.reasons
    fresh = _pin(*_near(rp, day), cuisines=("zzz_new_cuisine",), meals=("snack",))
    s = suggest(inp, fresh, sf, day=day, meal="snack", config=CONFIG).suggestions[0]
    _, e = _day_of(_place(inp, fresh, s), fresh.key)
    assert "NEW_CUISINE" in e.reasons
