"""Recalculation after adding or removing a place (Phase 7, ADR 018), on the synthetic fixtures.

No database and no network: the travel source returns labelled estimates.
"""

import math
from dataclasses import replace
from datetime import date

import pytest

from detour_api.planner import diff, recalc
from detour_api.planner.config import DEFAULT_CONFIG
from detour_api.planner.recalc import Addition, Revision, entry_key
from detour_api.planner.revision_validator import validate_revision
from detour_api.planner.travel import FixedTravelSource
from detour_api.planner.types import BaseCity, Candidate, PlanningImpossible, Restaurant
from tests import planner_helpers as ph
from tests.recalc_helpers import generated, lock, recalc_input

CANDS = ph.candidates("city-large")
RESTS = ph.restaurants("city-large")
BY_ID = {c.place_id: c for c in CANDS}
R_BY_ID = {r.place_id: r for r in RESTS}


def _addition(c: Candidate, minutes: int | None = None) -> Addition:
    return Addition(
        key=entry_key("visit", c.place_id, None),
        name=c.name,
        lat=c.lat,
        lon=c.lon,
        duration_minutes=minutes or 45,
        duration_source="user" if minutes else "category_default",
        place_id=c.place_id,
        category=c.category,
    )


def _pin(name: str, lat: float, lon: float, minutes: int = 60) -> Addition:
    return Addition(
        key=f"user:{name}",
        name=name,
        lat=lat,
        lon=lon,
        duration_minutes=minutes,
        duration_source="user",
        user_place_id=name,
    )


def _check(
    old: recalc.RPlan,
    rev: Revision,
    *,
    added: str | None = None,
    removed: str | None = None,
    cands: list[Candidate] = CANDS,
    rests: list[Restaurant] = RESTS,
) -> None:
    problems = validate_revision(
        old,
        rev,
        added=added,
        removed=removed,
        candidates={c.place_id: c for c in cands},
        restaurants={r.place_id: r for r in rests},
        config=DEFAULT_CONFIG,
    )
    assert problems == []


def _unplanned(rplan: recalc.RPlan) -> list[Candidate]:
    used = {e.place_id for d in rplan.days for e in d.items}
    return [c for c in CANDS if c.place_id not in used]


@pytest.mark.parametrize("profile", ["essentials", "wider"])
def test_an_addition_changes_few_days_and_keeps_every_rule(profile: str) -> None:
    req = ph.request("city-large", 3, date(2027, 5, 1))
    plan, rp = generated(req, CANDS, RESTS, profile)
    extra = _unplanned(rp)[0]
    add = _addition(extra)
    rev = recalc.add_place(recalc_input(plan, rp, req, CANDS, RESTS), add, FixedTravelSource())
    _check(rp, rev, added=add.key)
    d = diff.compare(rp, rev.plan)
    assert [a.key for a in d.added if a.kind == "visit"] == [add.key]
    # Disruption KPI: at most 20 % of existing visits change day after one addition in the city.
    visits = sum(len(day.visits) for day in rp.days)
    assert len(d.moved) * 5 <= visits
    assert len(rev.changed_days) <= 2
    assert rev.notes[0].code == "PLACE_ADDED"


def test_locked_items_never_move() -> None:
    req = ph.request("city-large", 3)
    plan, rp = generated(req, CANDS, RESTS)
    # Lock every other item of every day, meals included, then add three places in turn.
    keys = {e.key for d in rp.days for n, e in enumerate(d.items) if n % 2 == 0}
    current = lock(rp, keys)
    locked_before = {
        (d.day_index, e.key, e.start_minute, e.end_minute)
        for d in current.days
        for e in d.items
        if e.locked
    }
    for extra in _unplanned(rp)[:3]:
        inp = recalc_input(plan, current, req, CANDS, RESTS)
        try:
            rev = recalc.add_place(inp, _addition(extra), FixedTravelSource())
        except PlanningImpossible as exc:
            assert exc.issues  # explained, never a silent change
            continue
        _check(current, rev, added=_addition(extra).key)
        current = rev.plan
        locked_now = {
            (d.day_index, e.key, e.start_minute, e.end_minute)
            for d in current.days
            for e in d.items
            if e.locked
        }
        assert locked_now == locked_before


def test_items_the_user_added_are_never_left_out() -> None:
    req = ph.request("city-large", 2)
    plan, rp = generated(req, CANDS, RESTS)
    current = rp
    added: list[str] = []
    for extra in _unplanned(rp)[:6]:
        a = _addition(extra, minutes=60)
        try:
            rev = recalc.add_place(
                recalc_input(plan, current, req, CANDS, RESTS), a, FixedTravelSource()
            )
        except PlanningImpossible:
            break
        current = rev.plan
        added.append(a.key)
        keys = {e.key for d in current.days for e in d.items}
        assert set(added) <= keys


def test_removing_a_place_lays_its_day_out_again() -> None:
    req = ph.request("city-large", 3)
    plan, rp = generated(req, CANDS, RESTS)
    victim = rp.days[1].visits[2]
    rev = recalc.remove_place(
        recalc_input(plan, rp, req, CANDS, RESTS), victim.key, FixedTravelSource()
    )
    _check(rp, rev, removed=victim.key)
    d = diff.compare(rp, rev.plan)
    assert [r.key for r in d.removed if r.kind == "visit"] == [victim.key]
    assert rev.changed_days == (2,)
    assert d.travel_minutes_added <= 0 or d.days_changed == (2,)


def test_a_locked_item_cannot_be_removed() -> None:
    req = ph.request("city-large", 2)
    plan, rp = generated(req, CANDS, RESTS)
    victim = rp.days[0].visits[0]
    locked = lock(rp, {victim.key})
    with pytest.raises(PlanningImpossible) as info:
        recalc.remove_place(
            recalc_input(plan, locked, req, CANDS, RESTS), victim.key, FixedTravelSource()
        )
    assert [i.code for i in info.value.issues] == ["ITEM_LOCKED"]


# -- a distant addition ----------------------------------------------------------------------


def _far_world() -> tuple[BaseCity, list[Candidate], list[Restaurant]]:
    """A town 60 km east of the synthetic city, with five invented sights and two places to eat."""
    lat, lon = ph.request("city-large", 1).lat, ph.request("city-large", 1).lon
    east = lon + 60_000 / (111_320 * math.cos(math.radians(lat)))
    town = BaseCity(900202, "Farburg", lat, east, 30_000)
    sights = [
        Candidate(
            f"f0000000-0000-4000-8000-00000000000{i}",
            f"Far sight {i}",
            "museum",
            lat + 0.004 * i,
            east + 0.003 * i,
            {"has_wikidata": True},
        )
        for i in range(1, 6)
    ]
    eat = [
        Restaurant(
            f"f0000000-0000-4000-8000-0000000000a{i}",
            f"Far place to eat {i}",
            "restaurant",
            lat + 0.003 * i,
            east + 0.002,
            ("lunch", "dinner"),
            ("regional",),
        )
        for i in range(1, 3)
    ]
    return town, sights, eat


def test_a_distant_addition_reallocates_a_day_to_a_new_base() -> None:
    town, far_sights, far_eat = _far_world()
    cands, rests = CANDS + far_sights, RESTS + far_eat
    req = ph.request("city-large", 3, date(2027, 5, 1))
    plan, rp = generated(req, CANDS, RESTS)
    add = _addition(far_sights[0])
    inp = recalc_input(plan, rp, req, cands, rests, towns=[town])
    rev = recalc.add_place(inp, add, FixedTravelSource())
    _check(rp, rev, added=add.key, cands=cands, rests=rests)
    bases = [d.base_city_id for d in rev.plan.days]
    # The fullest day stays; the last day of the city's run becomes the new base.
    assert bases == [ph.SYNTHETIC_CITY_ID, ph.SYNTHETIC_CITY_ID, town.city_id]
    new_day = rev.plan.days[2]
    assert new_day.arrival is not None and new_day.arrival.mode == "drive"
    assert new_day.arrival.confidence == "estimated"
    assert add.key in {e.key for e in new_day.items}
    assert any(e.kind == "visit" and e.key != add.key for e in new_day.items)  # filled around it
    d = diff.compare(rp, rev.plan)
    assert [(b.day, b.new_name) for b in d.base_changes] == [(3, "Farburg")]
    assert d.travel_minutes_added > 0
    assert any(leg.day == 3 and leg.to_name == "Farburg" for leg in d.estimated_legs)
    codes = [n.code for n in rev.notes]
    assert "NEW_BASE_DAY" in codes and "INTER_CITY_TRAVEL" in codes and "BASE_CITY_DAYS" in codes


def test_a_distant_addition_on_a_one_day_trip_is_explained() -> None:
    town, far_sights, far_eat = _far_world()
    req = ph.request("city-large", 1)
    plan, rp = generated(req, CANDS, RESTS)
    inp = recalc_input(plan, rp, req, CANDS + far_sights, RESTS + far_eat, towns=[town])
    with pytest.raises(PlanningImpossible) as info:
        recalc.add_place(inp, _addition(far_sights[0]), FixedTravelSource())
    assert [i.code for i in info.value.issues] == ["NO_DAY_FOR_NEW_BASE"]
    assert info.value.issues[0].params["bases"] == "Synthetic City"


def test_a_distant_addition_without_a_town_is_explained() -> None:
    _, far_sights, _ = _far_world()
    req = ph.request("city-large", 3)
    plan, rp = generated(req, CANDS, RESTS)
    inp = recalc_input(plan, rp, req, CANDS, RESTS, towns=[])
    with pytest.raises(PlanningImpossible) as info:
        recalc.add_place(inp, _addition(far_sights[0]), FixedTravelSource())
    assert [i.code for i in info.value.issues] == ["NO_TOWN_NEAR_ADDITION"]


def test_days_with_locked_items_are_not_reallocated() -> None:
    town, far_sights, far_eat = _far_world()
    req = ph.request("city-large", 2)
    plan, rp = generated(req, CANDS, RESTS)
    locked = lock(rp, {d.visits[0].key for d in rp.days})
    inp = recalc_input(plan, locked, req, CANDS + far_sights, RESTS + far_eat, towns=[town])
    with pytest.raises(PlanningImpossible) as info:
        recalc.add_place(inp, _addition(far_sights[0]), FixedTravelSource())
    assert [i.code for i in info.value.issues] == ["DAY_HAS_FIXED_ITEMS", "DAY_HAS_FIXED_ITEMS"]
    assert {i.params["day"] for i in info.value.issues} == {1, 2}


# -- infeasible additions --------------------------------------------------------------------


def test_an_addition_longer_than_any_day_is_explained() -> None:
    req = ph.request("city-large", 2)
    plan, rp = generated(req, CANDS, RESTS)
    lat, lon = req.lat, req.lon
    with pytest.raises(PlanningImpossible) as info:
        recalc.add_place(
            recalc_input(plan, rp, req, CANDS, RESTS),
            _pin("Long walk", lat + 0.001, lon, minutes=900),
            FixedTravelSource(),
        )
    [issue] = info.value.issues
    assert issue.code == "ADDITION_LONGER_THAN_DAY" and issue.params["minutes"] == 900


def test_days_full_of_locked_items_name_the_items_that_cannot_move() -> None:
    req = ph.request("city-large", 2)
    plan, rp = generated(req, CANDS, RESTS)
    every = lock(rp, {e.key for d in rp.days for e in d.items})
    with pytest.raises(PlanningImpossible) as info:
        recalc.add_place(
            recalc_input(plan, every, req, CANDS, RESTS),
            _pin("Market", req.lat + 0.001, req.lon, minutes=240),
            FixedTravelSource(),
        )
    issues = info.value.issues
    assert [i.code for i in issues] == ["DAY_FULL_OF_FIXED_ITEMS"] * 2
    assert rp.days[0].items[0].name in str(issues[0].params["items"])


def test_a_place_already_in_the_plan_is_explained() -> None:
    req = ph.request("city-large", 2)
    plan, rp = generated(req, CANDS, RESTS)
    there = BY_ID[rp.days[1].visits[0].place_id or ""]
    with pytest.raises(PlanningImpossible) as info:
        recalc.add_place(
            recalc_input(plan, rp, req, CANDS, RESTS), _addition(there), FixedTravelSource()
        )
    assert [(i.code, i.params["day"]) for i in info.value.issues] == [("ALREADY_IN_PLAN", 2)]


# -- determinism and the validator ------------------------------------------------------------


def test_recalculation_is_deterministic() -> None:
    req = ph.request("city-large", 3)
    plan, rp = generated(req, CANDS, RESTS)
    add = _addition(_unplanned(rp)[5])
    a = recalc.add_place(recalc_input(plan, rp, req, CANDS, RESTS), add, FixedTravelSource())
    b = recalc.add_place(
        recalc_input(plan, rp, req, list(reversed(CANDS)), list(reversed(RESTS))),
        add,
        FixedTravelSource(),
    )
    assert a.plan == b.plan and a.notes == b.notes


def test_the_validator_catches_a_moved_locked_item() -> None:
    req = ph.request("city-large", 2)
    plan, rp = generated(req, CANDS, RESTS)
    first = rp.days[0].visits[0]
    locked = lock(rp, {first.key})
    add = _addition(_unplanned(rp)[0])
    rev = recalc.add_place(recalc_input(plan, locked, req, CANDS, RESTS), add, FixedTravelSource())
    day = rev.plan.days[0]
    shifted = tuple(
        replace(e, start_minute=e.start_minute + 1, end_minute=e.end_minute + 1)
        if e.key == first.key
        else e
        for e in day.items
    )
    broken = replace(
        rev,
        plan=recalc.RPlan(rev.plan.profile, (replace(day, items=shifted), *rev.plan.days[1:])),
        changed_days=tuple(sorted({1, *rev.changed_days})),
    )
    problems = validate_revision(
        locked,
        broken,
        added=add.key,
        removed=None,
        candidates=BY_ID,
        restaurants=R_BY_ID,
        config=DEFAULT_CONFIG,
    )
    assert "LOCKED_ITEM_MOVED" in {p.code for p in problems}


def test_the_validator_catches_a_dropped_addition_and_a_changed_unchanged_day() -> None:
    req = ph.request("city-large", 2)
    plan, rp = generated(req, CANDS, RESTS)
    add = _addition(_unplanned(rp)[0])
    rev = recalc.add_place(recalc_input(plan, rp, req, CANDS, RESTS), add, FixedTravelSource())
    unchanged = next(d for d in rev.plan.days if d.day_index not in rev.changed_days)
    tampered = replace(unchanged, items=unchanged.items[:-1])
    days = tuple(tampered if d is unchanged else d for d in rev.plan.days)
    problems = validate_revision(
        rp,
        replace(rev, plan=recalc.RPlan(rev.plan.profile, days)),
        added="user:missing",
        removed=None,
        candidates=BY_ID,
        restaurants=R_BY_ID,
        config=DEFAULT_CONFIG,
    )
    codes = {p.code for p in problems}
    assert {"ADDITION_MISSING", "UNCHANGED_DAY_DIFFERS"} <= codes


def test_recalculation_latency_is_within_the_kpi() -> None:
    import time

    req = ph.request("city-large", 7)
    plan, rp = generated(req, CANDS, RESTS)
    add = _addition(_unplanned(rp)[0])
    start = time.perf_counter()
    recalc.add_place(recalc_input(plan, rp, req, CANDS, RESTS), add, FixedTravelSource())
    assert time.perf_counter() - start < 1.0  # the KPI is 3 s for the whole request


def test_a_single_city_country_gets_no_new_base() -> None:
    town, far_sights, far_eat = _far_world()
    req = ph.request("city-large", 3)
    plan, rp = generated(req, CANDS, RESTS)
    inp = replace(
        recalc_input(plan, rp, req, CANDS + far_sights, RESTS + far_eat, towns=[town]),
        single_city=True,
    )
    with pytest.raises(PlanningImpossible) as info:
        recalc.add_place(inp, _addition(far_sights[0]), FixedTravelSource())
    assert [i.code for i in info.value.issues] == ["SINGLE_CITY_ONLY"]


# -- one day only (place suggestions, ADR 021) ---------------------------------------------------


def test_only_day_places_the_addition_on_that_day_and_the_best_matches_the_default() -> None:
    req = ph.request("city-large", 3, date(2027, 5, 1))
    plan, rp = generated(req, CANDS, RESTS)
    add = _addition(_unplanned(rp)[0])
    inp = recalc_input(plan, rp, req, CANDS, RESTS)
    default = recalc.add_place(inp, add, FixedTravelSource())
    per_day = {k: recalc.add_place(inp, add, FixedTravelSource(), only_day=k) for k in (1, 2, 3)}
    for k, rev in per_day.items():
        _check(rp, rev, added=add.key)
        day = next(d for d in rev.plan.days if any(e.key == add.key for e in d.items))
        assert day.day_index == k
    # The cheapest single day is the day the unrestricted recalculation chooses, at the same cost.
    best = min(per_day, key=lambda k: (per_day[k].cost, k))
    default_day = next(
        d.day_index for d in default.plan.days if any(e.key == add.key for e in d.items)
    )
    assert best == default_day and per_day[best].cost == default.cost
    assert per_day[best].plan == default.plan


def test_only_day_far_from_the_addition_is_explained() -> None:
    town, far_sights, far_eat = _far_world()
    cands, rests = CANDS + far_sights, RESTS + far_eat
    req = ph.request("city-large", 3, date(2027, 5, 1))
    plan, rp = generated(req, CANDS, RESTS)
    inp = recalc_input(plan, rp, req, cands, rests, towns=[town])
    add = _addition(far_sights[0])
    # Only the ends of the city's run can become a new base; day 2 is in the middle.
    with pytest.raises(PlanningImpossible) as exc:
        recalc.add_place(inp, add, FixedTravelSource(), only_day=2)
    assert [i.code for i in exc.value.issues] == ["DAY_NOT_NEAR_ADDITION"]
    rev = recalc.add_place(inp, add, FixedTravelSource(), only_day=1)
    assert rev.plan.days[0].base_city_id == town.city_id
