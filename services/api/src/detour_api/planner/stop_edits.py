"""Editing the stops of a multi-city trip (ADR 024, decision 19), by repair, never by generating
the whole plan again.

``assemble`` puts the new day list together from the current plan:

* a stop that is kept (the same city, matched in order of appearance) keeps its days and their
  items, in its new place in the trip; only the day numbers and dates move;
* a stop with fewer days drops whole days from its end; a locked item on a dropped day stops the
  edit (``LOCKED_ON_DROPPED_DAY``: unlock it or keep the days), anything else on those days is
  listed as removed;
* a stop with more days, and a new stop, gets empty days at its end, which the caller fills
  (``StopFill``: the planner's visits and meals for the stop, or nothing in a manual plan);
* a removed stop drops its days and every item on them, including places the user added and
  locked items; they are listed (``STOP_REMOVED_ITEMS``) so nothing disappears silently.

The caller then lays out again every day whose base, previous base or items changed (the
recalculation's ``Work.fit``), so arrival legs follow the new order.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, timedelta

from detour_api.planner import engine
from detour_api.planner.config import DEFAULT_CONFIG, PlannerConfig
from detour_api.planner.recalc import (
    DEFAULT_RECALC,
    Entry,
    RDay,
    RecalcConfig,
    RecalcInput,
    Revision,
    RPlan,
    _finish,
    _Work,
    entry_key,
    revision_stats,
)
from detour_api.planner.sequencer import Sequencer
from detour_api.planner.travel import TravelSource
from detour_api.planner.types import (
    BaseCity,
    Candidate,
    Issue,
    Note,
    PlanningImpossible,
    PlanRequest,
    Restaurant,
)


@dataclass(frozen=True)
class OldStop:
    city_id: int
    days: int


@dataclass(frozen=True)
class NewStop:
    city: BaseCity
    days: int


@dataclass(frozen=True)
class Assembly:
    plan: RPlan
    # Day indices to lay out again (new, filled, moved or with a new previous base).
    relay: tuple[int, ...]
    # Indices of days the caller must fill, by new stop position (0-based): (stop, day indices).
    to_fill: tuple[tuple[int, tuple[int, ...]], ...]
    removed: tuple[Entry, ...]
    issues: tuple[Issue, ...] = ()
    # The new day index each kept old day moved to (old index -> new index).
    moved_days: dict[int, int] = field(default_factory=dict)


def assemble(
    plan: RPlan,
    old_stops: Sequence[OldStop],
    new_stops: Sequence[NewStop],
    start_date: date | None,
) -> Assembly:
    by_index = {d.day_index: d for d in plan.days}
    segments: list[list[RDay]] = []
    k = 1
    for s in old_stops:
        segments.append([by_index[i] for i in range(k, k + s.days) if i in by_index])
        k += s.days
    used = [False] * len(old_stops)

    days: list[RDay] = []
    relay: list[int] = []
    to_fill: list[tuple[int, tuple[int, ...]]] = []
    removed: list[Entry] = []
    issues: list[Issue] = []
    moved: dict[int, int] = {}
    for position, stop in enumerate(new_stops):
        match = next(
            (i for i, s in enumerate(old_stops) if not used[i] and s.city_id == stop.city.city_id),
            None,
        )
        kept: list[RDay] = []
        if match is not None:
            used[match] = True
            kept = segments[match][: stop.days]
            for dropped in segments[match][stop.days :]:
                locked = [e.name for e in dropped.items if e.locked]
                if locked:
                    issues.append(
                        Issue(
                            "LOCKED_ON_DROPPED_DAY",
                            {"day": dropped.day_index, "items": ", ".join(locked)},
                        )
                    )
                removed.extend(dropped.items)
        fill: list[int] = []
        for n in range(stop.days):
            index = len(days) + 1
            day_date = None if start_date is None else start_date + timedelta(days=index - 1)
            if n < len(kept):
                old = kept[n]
                moved[old.day_index] = index
                days.append(
                    RDay(
                        day_index=index,
                        date=day_date,
                        base_city_id=stop.city.city_id,
                        base_city_name=stop.city.name,
                        items=old.items,
                        arrival=old.arrival,
                        arrival_unknown=old.arrival_unknown,
                    )
                )
            else:
                fill.append(index)
                days.append(
                    RDay(
                        day_index=index,
                        date=day_date,
                        base_city_id=stop.city.city_id,
                        base_city_name=stop.city.name,
                        items=(),
                    )
                )
        if fill:
            to_fill.append((position, tuple(fill)))
    for i, seg in enumerate(segments):
        if not used[i]:
            for d in seg:
                removed.extend(d.items)

    # A day is laid out again if it is new, moved, or its previous day's base changed: its
    # arrival leg (or none) follows from the new order.
    old_prev_base = {
        d.day_index: (by_index[d.day_index - 1].base_city_id if d.day_index > 1 else None)
        for d in plan.days
    }
    reverse = {new: old for old, new in moved.items()}
    for d in days:
        old_index = reverse.get(d.day_index)
        prev_base = days[d.day_index - 2].base_city_id if d.day_index > 1 else None
        if (
            old_index is None
            or old_index != d.day_index
            or old_prev_base.get(old_index) != prev_base
        ):
            relay.append(d.day_index)
    return Assembly(
        plan=RPlan(plan.profile, tuple(days)),
        relay=tuple(relay),
        to_fill=tuple(to_fill),
        removed=tuple(removed),
        issues=tuple(issues),
        moved_days=moved,
    )


def fill_days(
    stop: NewStop,
    count: int,
    profile: str,
    candidates: Sequence[Candidate],
    restaurants: Sequence[Restaurant],
    exclude: frozenset[str],
    source: TravelSource,
    *,
    config: PlannerConfig = DEFAULT_CONFIG,
    sequencer: Sequencer | None = None,
) -> list[tuple[Entry, ...]]:
    """Visits and meals for ``count`` new days at a stop: the planner's own plan of the stop as a
    city, with the plan's profile, leaving out places the trip already has. Days it cannot fill
    stay empty (nothing is invented)."""
    pool = [c for c in candidates if c.place_id not in exclude]
    request = PlanRequest(
        destination_name=stop.city.name,
        lat=stop.city.lat,
        lon=stop.city.lon,
        days=count,
        start_date=None,
        data_version=None,
        kind="city",
        base_cities=(stop.city,),
    )
    try:
        generation = engine.generate(
            request, pool, source, restaurants=restaurants, config=config, sequencer=sequencer
        )
    except PlanningImpossible:
        return [() for _ in range(count)]
    plan = next((p for p in generation.plans if p.profile == profile), generation.plans[0])
    out: list[tuple[Entry, ...]] = []
    for day in plan.days:
        out.append(
            tuple(
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
                )
                for i in day.items
                if i.place_id not in exclude or i.kind == "meal"
            )
        )
    return out


def relay(
    inp: RecalcInput,
    assembly: Assembly,
    fills: Mapping[int, tuple[Entry, ...]],
    source: TravelSource,
    *,
    config: PlannerConfig = DEFAULT_CONFIG,
    rconfig: RecalcConfig = DEFAULT_RECALC,
    use_provider: bool = False,
    notes: Sequence[Note] = (),
) -> tuple[RPlan, Revision]:
    """The assembled plan with its filled days, and the revision after laying out again every day
    in ``assembly.relay`` (arrival legs follow the new order; a day that no longer fits loses its
    lowest-value engine visits, never a locked item or one the user added).

    Returns the assembled plan before the layout too: it is what the revision validator compares
    the result against (its day count is the new one)."""
    days = tuple(
        replace(d, items=fills[d.day_index]) if d.day_index in fills else d
        for d in assembly.plan.days
    )
    before = RPlan(assembly.plan.profile, days)
    work = _Work(replace(inp, plan=before), source, config, rconfig)
    specs = {}
    for k in assembly.relay:
        spec = work.spec_of(work.days[k])
        fitted = work.fit(spec)
        if fitted is None:
            raise PlanningImpossible(
                [Issue("ROUTED_TIMES_TOO_LONG", {"day": k, "name": "its items"})]
            )
        specs[k], work.days[k], _ = fitted
    _finish(work, specs, use_provider, None)
    plan = RPlan(before.profile, tuple(work.days[k] for k in sorted(work.days)))
    changed = tuple(sorted(k for k in work.days if work.days[k] != work.old.get(k)))
    revision = Revision(
        plan=plan,
        changed_days=tuple(sorted(set(changed) | set(assembly.relay))),
        notes=tuple(notes),
        stats=revision_stats(plan.days, config),
        bases=dict(work.bases),
        known_times=work.lookup.known(),
        cost=0,
    )
    return before, revision
