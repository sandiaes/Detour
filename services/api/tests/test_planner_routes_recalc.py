"""Adding, removing and stop edits on a synthetic three-stop trip (ADR 024, decisions 18 and 19)."""

from dataclasses import replace

import pytest

from detour_api.planner import recalc, stop_edits
from detour_api.planner.config import DEFAULT_CONFIG
from detour_api.planner.recalc import Addition, RecalcInput, RPlan, entry_key
from detour_api.planner.revision_validator import validate_revision
from detour_api.planner.travel import FixedTravelSource
from detour_api.planner.types import Plan, PlanningImpossible, PlanRequest
from tests.planner_helpers import candidates, route_request, towns
from tests.recalc_helpers import generated, lock, recalc_input

STOPS = [(990001, 2, "AT"), (990005, 1, "AT"), (990002, 2, "AT")]  # A, E, B


def _setup() -> tuple[PlanRequest, Plan, RPlan, RecalcInput]:
    req = route_request(STOPS)
    plan, rplan = generated(req, candidates("area"))
    inp = recalc_input(plan, rplan, req, candidates("area"))
    return req, plan, rplan, inp


def _unplanned_near(rplan: RPlan, city_id: int) -> Addition:
    town = next(t for t in towns("area") if t.city_id == city_id)
    planned = {e.place_id for d in rplan.days for e in d.items}
    c = min(
        (c for c in candidates("area") if c.place_id not in planned),
        key=lambda c: (abs(c.lat - town.lat) + abs(c.lon - town.lon), c.place_id),
    )
    return Addition(
        key=entry_key("visit", c.place_id, None),
        name=c.name,
        lat=c.lat,
        lon=c.lon,
        duration_minutes=60,
        duration_source="category_default",
        place_id=c.place_id,
        category=c.category,
    )


@pytest.mark.parametrize(("city_id", "days"), [(990001, {1, 2}), (990002, {4, 5})])
def test_an_addition_goes_on_its_own_stops_days(city_id: int, days: set[int]) -> None:
    _, _, rplan, inp = _setup()
    x = _unplanned_near(rplan, city_id)
    revision = recalc.add_place(inp, x, FixedTravelSource())
    day = next(d.day_index for d in revision.plan.days for e in d.items if e.key == x.key)
    assert day in days
    for k in sorted(days):
        only = recalc.add_place(inp, x, FixedTravelSource(), only_day=k)
        assert any(e.key == x.key for d in only.plan.days if d.day_index == k for e in d.items)


def test_a_place_far_from_every_stop_is_refused() -> None:
    _, _, _, inp = _setup()
    far = Addition(
        key="user:far",
        name="Far hut",
        lat=46.5,
        lon=10.0,
        duration_minutes=60,
        duration_source="user",
        user_place_id="far",
    )
    with pytest.raises(PlanningImpossible) as info:
        recalc.add_place(inp, far, FixedTravelSource())
    assert [i.code for i in info.value.issues] == ["OUTSIDE_STOPS"]


def test_a_stop_edit_keeps_unchanged_stops_and_fills_new_days() -> None:
    _, _, rplan, inp = _setup()
    old = [stop_edits.OldStop(c, d) for c, d, _ in STOPS]
    by_id = {t.city_id: t for t in towns("area")}
    # B first for three days, then A as before; E removed.
    new = [stop_edits.NewStop(by_id[990002], 3), stop_edits.NewStop(by_id[990001], 2)]
    assembly = stop_edits.assemble(rplan, old, new, None)
    assert not assembly.issues
    assert [d.base_city_id for d in assembly.plan.days] == [990002] * 3 + [990001] * 2
    assert assembly.plan.days[0].items == rplan.days[3].items  # B's first day kept
    assert assembly.plan.days[3].items == rplan.days[0].items  # A's first day kept
    assert assembly.to_fill == ((0, (3,)),)
    assert {e.key for e in assembly.removed} == {e.key for e in rplan.days[2].items}
    planned = frozenset(e.place_id or "" for d in assembly.plan.days for e in d.items)
    fills = dict(
        zip(
            (3,),
            stop_edits.fill_days(
                new[0],
                1,
                "essentials",
                inp.candidates,
                planned,
                FixedTravelSource(),
            ),
            strict=True,
        )
    )
    before, revision = stop_edits.relay(inp, assembly, fills, FixedTravelSource())
    assert revision.plan.days[2].visits, "the new B day is filled"
    assert revision.plan.days[0].arrival is None
    assert revision.plan.days[3].arrival is not None  # B to A now
    assert (
        validate_revision(
            before,
            revision,
            added=None,
            removed=None,
            candidates={c.place_id: c for c in inp.candidates},
            config=DEFAULT_CONFIG,
        )
        == []
    )


def test_a_locked_item_on_a_dropped_day_stops_a_stop_edit() -> None:
    _, _, rplan, _ = _setup()
    second = rplan.days[1]
    rplan = lock(rplan, {second.items[0].key})
    old = [stop_edits.OldStop(c, d) for c, d, _ in STOPS]
    by_id = {t.city_id: t for t in towns("area")}
    new = [
        stop_edits.NewStop(by_id[990001], 1),
        stop_edits.NewStop(by_id[990005], 1),
        stop_edits.NewStop(by_id[990002], 2),
    ]
    assembly = stop_edits.assemble(rplan, old, new, None)
    assert [i.code for i in assembly.issues] == ["LOCKED_ON_DROPPED_DAY"]


def test_removing_a_stop_lists_what_you_added_there() -> None:
    _, _, rplan, _ = _setup()
    third = rplan.days[2]
    mine = replace(third.items[0], origin="user")
    rplan = replace(
        rplan,
        days=tuple(
            replace(d, items=(mine, *d.items[1:])) if d.day_index == 3 else d for d in rplan.days
        ),
    )
    old = [stop_edits.OldStop(c, d) for c, d, _ in STOPS]
    by_id = {t.city_id: t for t in towns("area")}
    new = [stop_edits.NewStop(by_id[990001], 2), stop_edits.NewStop(by_id[990002], 2)]
    assembly = stop_edits.assemble(rplan, old, new, None)
    assert mine in assembly.removed
