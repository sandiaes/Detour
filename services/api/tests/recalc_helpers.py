"""Helpers for the recalculation tests: an engine plan as the recalculation sees it."""

from collections.abc import Sequence

from detour_api.planner import engine
from detour_api.planner.recalc import Entry, RDay, RecalcInput, RPlan, entry_key
from detour_api.planner.travel import FixedTravelSource
from detour_api.planner.types import BaseCity, Candidate, Plan, PlanRequest, Restaurant


def as_rplan(plan: Plan) -> RPlan:
    days = []
    for d in plan.days:
        items = tuple(
            Entry(
                key=entry_key(i.kind, i.place_id, None),
                kind=i.kind,
                name=i.name,
                lat=i.lat,
                lon=i.lon,
                start_minute=i.start_minute,
                end_minute=i.end_minute,
                duration_minutes=i.duration_minutes,
                duration_source="category_default",
                origin="engine",
                locked=False,
                reasons=i.reasons,
                transfer=i.transfer,
                place_id=i.place_id,
                category=i.category,
                meal_type=i.meal_type,
                cuisines=i.cuisines,
                item_id=f"item-{d.day_index}-{n}",
            )
            for n, i in enumerate(d.items)
        )
        days.append(RDay(d.day_index, d.date, d.base_city_id, d.base_city_name, items, d.arrival))
    return RPlan(plan.profile, tuple(days))


def generated(
    request: PlanRequest,
    candidates: Sequence[Candidate],
    restaurants: Sequence[Restaurant],
    profile: str = "essentials",
) -> tuple[Plan, RPlan]:
    gen = engine.generate(request, candidates, FixedTravelSource(), restaurants=restaurants)
    plan = next(p for p in gen.plans if p.profile == profile)
    return plan, as_rplan(plan)


def recalc_input(
    plan: Plan,
    rplan: RPlan,
    request: PlanRequest,
    candidates: Sequence[Candidate],
    restaurants: Sequence[Restaurant],
    towns: Sequence[BaseCity] = (),
) -> RecalcInput:
    bases = {b.city_id: b for b in request.base_cities}
    return RecalcInput(
        plan=rplan,
        notes=plan.notes,
        bases=bases,
        candidates=tuple(candidates),
        restaurants=tuple(restaurants),
        towns=tuple(towns),
    )


def lock(rplan: RPlan, keys: set[str]) -> RPlan:
    from dataclasses import replace

    return RPlan(
        rplan.profile,
        tuple(
            replace(d, items=tuple(replace(e, locked=e.key in keys) for e in d.items))
            for d in rplan.days
        ),
    )
