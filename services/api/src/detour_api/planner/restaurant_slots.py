"""Adding a restaurant: scoring every day and meal slot, and placing it (Phase 8, ADR 019;
architecture section 5.4).

The restaurant is a **meal the user adds** (origin ``user``). Once placed it keeps its day and
times like any meal the user added (ADR 018), and the rest of the day is laid out around it. While
its slot is being found it is *floating*: the layout (``recalc._Work.lay_out``) starts it when its
meal window opens or when the traveller arrives, whichever is later, and refuses the layout if the
meal would end after its window (ADR 016) or after the day's end. So a suggestion that exists
always respects both, and the revision validator checks them again.

**Slots.** Every day with visits, and every meal type the place serves (all four when the place's
meal types are unknown), is a slot. In each slot the floating meal goes into the day between two
neighbouring items (visits, or meals the user fixed); of those positions the four with the least
added travel that can plausibly fit in time are laid out in full, and the cheapest wins. A day that
already has an engine meal of the slot's type loses it: the new meal replaces it. A meal the user
fixed, or a locked one, is never replaced, so that slot is not offered. No visit is ever left out
to make room (the slot is simply not offered), and visits never change day.

**Cost** (integers, lower is better; planning choices, not facts; ``RecalcConfig``):

    travel weight x added travel minutes of the day (transfers, as laid out; never below zero:
        dropping the replaced meal's own legs is not a reward for a far restaurant)
    + straight-line detour in metres // slot_detour_m_per_unit      (location)
    + retime_cost per other item that starts at another time + slot_shift_minute_cost per minute
    + slot_wait_minute_cost per minute of waiting for the window to open
    + slot_replace_meal_cost                         if it replaces a meal the plan has
    + slot_cuisine_repeat_cost                       if a cuisine repeats on this or a nearby day
    + slot_meal_unknown_cost                         if the meals the place serves are unknown

Ties go to the earlier day, then the earlier start, then the meal order. The best position of each
(day, meal type) is one candidate; the cheapest ``slot_suggestions`` candidates are returned, each
with its reasons (codes rendered by fixed templates), the estimated detour, and which items move.
There are no opening hours, reservations, prices or ratings.

Travel while scoring comes from the cache and labelled estimates only (no provider call); the
preview that follows asks the provider for the changed day's legs, like every recalculation.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from typing import Literal

from detour_api.planner.config import DEFAULT_CONFIG, MEAL_TYPES, MealType, PlannerConfig
from detour_api.planner.meals import detour_m
from detour_api.planner.recalc import (
    _WINDOW_REASON,
    DEFAULT_RECALC,
    POSITIONS_TRIED,
    Entry,
    RDay,
    RecalcConfig,
    RecalcInput,
    Revision,
    _finish,
    _Option,
    _ordered,
    _revision,
    _Spec,
    _travel,
    _Work,
    entry_key,
)
from detour_api.planner.travel import TravelSource
from detour_api.planner.types import Issue, Note, NoteParams, PlanningImpossible
from detour_api.travel.types import Coord, distance_m

MealBasis = Literal["venue", "you", "unknown"]


@dataclass(frozen=True)
class Dining:
    """The restaurant being added: an imported place to eat, or one of the user's own.

    ``meal_types`` is what the place serves: derived from the venue type by the import's fixed rule
    for an imported place (``basis`` ``venue``), given by the user for their own place (``you``),
    or ``None`` when unknown (``unknown``). ``cuisines`` is ``None`` when none was stated. There is
    no venue type for a place of the user's own."""

    name: str
    lat: float
    lon: float
    venue_type: str | None = None
    cuisines: tuple[str, ...] | None = None
    meal_types: tuple[str, ...] | None = None
    place_id: str | None = None
    user_place_id: str | None = None

    @property
    def key(self) -> str:
        return entry_key("meal", self.place_id, self.user_place_id)

    @property
    def coord(self) -> Coord:
        return Coord.from_degrees(self.lat, self.lon)

    @property
    def basis(self) -> MealBasis:
        if self.meal_types is None:
            return "unknown"
        return "venue" if self.place_id is not None else "you"

    def serves(self, meal: str) -> bool:
        return self.meal_types is None or meal in self.meal_types

    def entry(
        self, meal: MealType, config: PlannerConfig, *, floating: bool, reasons: Iterable[str]
    ) -> Entry:
        length = config.meal_minutes(meal, self.venue_type)
        return Entry(
            key=self.key,
            kind="meal",
            name=self.name,
            lat=self.lat,
            lon=self.lon,
            start_minute=0,
            end_minute=0,
            duration_minutes=length,
            duration_source="category_default",
            origin="user",
            locked=False,
            reasons=_ordered(reasons),
            place_id=self.place_id,
            user_place_id=self.user_place_id,
            category=self.venue_type,
            meal_type=meal,
            cuisines=self.cuisines,
            floating=floating,
        )


@dataclass(frozen=True)
class Reason:
    code: str
    params: NoteParams = field(default_factory=dict)


@dataclass(frozen=True)
class Shift:
    """Another item of the day that starts at another time because of the new meal."""

    kind: Literal["visit", "meal"]
    name: str
    old_start_minute: int
    new_start_minute: int


@dataclass(frozen=True)
class Suggestion:
    day_index: int
    meal_type: MealType
    # The visit (or fixed meal) the new meal follows; None: first of the day.
    after_item_id: str | None
    after_name: str | None
    before_name: str | None
    start_minute: int
    end_minute: int
    cost: int
    travel_minutes_added: int
    detour_m: int
    estimated: bool  # a travel time next to the new meal is a straight-line estimate
    replaces: str | None  # the engine meal of this type the new meal replaces
    shifts: tuple[Shift, ...]
    reasons: tuple[Reason, ...]


@dataclass(frozen=True)
class SlotResult:
    suggestions: tuple[Suggestion, ...]
    slots_considered: int  # (day, meal type) pairs that could be tried
    issues: tuple[Issue, ...]  # why there is nothing to suggest, when there is nothing


def _fmt(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def _trial_seq(spec: _Spec, e: Entry, gap: int) -> _Spec:
    return replace(spec, seq=(*spec.seq[:gap], e, *spec.seq[gap:]))


def _plausible_gaps(spec: _Spec, config: PlannerConfig, meal: MealType, length: int) -> list[int]:
    """Gaps where the meal could be in time, judged from the times the plan has now: the item
    before it ends early enough to leave the meal inside its window, and the item after it does
    not end before the window opens. Only a pruning step: the layout decides."""
    w = config.meal_window(meal)
    out: list[int] = []
    seq = spec.seq
    for g in range(len(seq) + 1):
        before = seq[g - 1] if g > 0 else None
        after = seq[g] if g < len(seq) else None
        if before is not None and before.end_minute > w.end_minute - length:
            continue
        if after is not None and after.end_minute < w.start_minute:
            continue
        out.append(g)
    return out


def _evaluate(
    work: _Work,
    spec: _Spec,
    dining: Dining,
    meal: MealType,
    rconfig: RecalcConfig,
) -> tuple[int, _Spec, RDay, Entry, int] | None:
    """The best position of the new meal in this day for this meal type, or None when the meal
    cannot be placed: (cost, trial spec, laid day, the meal entry as laid out, gap)."""
    config = work.config
    probe = dining.entry(meal, config, floating=True, reasons=())
    length = probe.duration_minutes
    gaps = _plausible_gaps(spec, config, meal, length)
    if not gaps:
        return None
    # The cheapest gaps by added travel, ties by position (``positions`` knows nothing of time).
    scored: list[tuple[int, int]] = []
    for g in gaps:
        a = spec.seq[g - 1].coord if g > 0 else None
        b = spec.seq[g].coord if g < len(spec.seq) else None
        delta = 0
        if a is not None:
            delta += work.mins(a, dining.coord)
        if b is not None:
            delta += work.mins(dining.coord, b)
        if a is not None and b is not None:
            delta -= work.mins(a, b)
        scored.append((delta, g))
    tried = [g for _, g in sorted(scored)[:POSITIONS_TRIED]]
    old_day = work.days[spec.index]
    best: tuple[tuple[int, int], _Spec, RDay, Entry] | None = None
    for g in tried:
        trial = _trial_seq(spec, probe, g)
        laid = work.lay_out(trial)
        if laid is None:
            continue
        placed = next(e for e in laid.items if e.key == dining.key)
        cost = _cost(work, old_day, laid, placed, dining, meal, rconfig)
        if best is None or (cost, g) < best[0]:
            best = ((cost, g), trial, laid, placed)
    if best is None:
        return None
    return best[0][0], best[1], best[2], best[3], best[0][1]


def _replaced(day: RDay, meal: MealType) -> Entry | None:
    """The meal of this type the day has now (an engine meal: user and locked meals are filtered
    out before)."""
    return next((e for e in day.items if e.kind == "meal" and e.meal_type == meal), None)


def _shifts(old: RDay, new: RDay, new_key: str) -> list[Shift]:
    before = {e.key: e for e in old.items}
    out: list[Shift] = []
    for e in new.items:
        if e.key == new_key:
            continue
        o = before.get(e.key)
        if o is not None and o.start_minute != e.start_minute:
            out.append(Shift(e.kind, e.name, o.start_minute, e.start_minute))
    return out


def _wait(laid: RDay, placed: Entry, day_start: int) -> int:
    """Minutes the traveller waits at the restaurant for its window to open."""
    items = laid.items
    n = next(i for i, e in enumerate(items) if e is placed)
    if n == 0:
        arrive = day_start
    else:
        prev = items[n - 1]
        arrive = prev.end_minute + (prev.transfer.minutes if prev.transfer else 0)
    return max(0, placed.start_minute - arrive)


def _cost(
    work: _Work,
    old: RDay,
    laid: RDay,
    placed: Entry,
    dining: Dining,
    meal: MealType,
    rconfig: RecalcConfig,
) -> int:
    weight = work.profile.travel_weight
    items = laid.items
    n = next(i for i, e in enumerate(items) if e is placed)
    prev = items[n - 1] if n > 0 else None
    nxt = items[n + 1] if n + 1 < len(items) else None
    shifts = _shifts(old, laid, placed.key)
    day_start = work.config.day_start_minute + (laid.arrival.minutes if laid.arrival else 0)
    cost = weight * max(0, _travel(laid) - _travel(old))
    cost += (
        detour_m(
            None if prev is None else prev.coord, dining.coord, None if nxt is None else nxt.coord
        )
        // rconfig.slot_detour_m_per_unit
    )
    cost += rconfig.retime_cost * len(shifts)
    cost += rconfig.slot_shift_minute_cost * sum(
        abs(s.new_start_minute - s.old_start_minute) for s in shifts
    )
    cost += rconfig.slot_wait_minute_cost * _wait(laid, placed, day_start)
    if _replaced(old, meal) is not None:
        cost += rconfig.slot_replace_meal_cost
    if dining.cuisines and _cuisine_repeats(work, laid, placed):
        cost += rconfig.slot_cuisine_repeat_cost
    if dining.meal_types is None:
        cost += rconfig.slot_meal_unknown_cost
    return cost


def _nearby_meals(work: _Work, laid: RDay, placed: Entry) -> list[Entry]:
    """Meals of the same day and of the days either side (the stretch variety is judged over)."""
    out: list[Entry] = [e for e in laid.items if e.kind == "meal" and e is not placed]
    for k in (laid.day_index - 1, laid.day_index + 1):
        day = work.days.get(k)
        if day is not None:
            out += [e for e in day.items if e.kind == "meal"]
    return out


def _cuisine_repeats(work: _Work, laid: RDay, placed: Entry) -> list[str]:
    mine = set(placed.cuisines or ())
    seen = {c for e in _nearby_meals(work, laid, placed) for c in (e.cuisines or ())}
    return sorted(mine & seen)


def _reasons(
    work: _Work,
    old: RDay,
    laid: RDay,
    placed: Entry,
    dining: Dining,
    meal: MealType,
    shifts: list[Shift],
    added_travel: int,
    estimated: bool,
    replaces: Entry | None,
    day_start: int,
) -> tuple[Reason, ...]:
    config = work.config
    w = config.meal_window(meal)
    items = laid.items
    n = next(i for i, e in enumerate(items) if e is placed)
    prev = items[n - 1] if n > 0 else None
    nxt = items[n + 1] if n + 1 < len(items) else None
    out: list[Reason] = [
        Reason(
            "SLOT_WINDOW",
            {
                "meal": meal,
                "window_start": _fmt(w.start_minute),
                "window_end": _fmt(w.end_minute),
                "start": _fmt(placed.start_minute),
                "end": _fmt(placed.end_minute),
            },
        )
    ]
    if dining.basis == "venue":
        out.append(
            Reason("SLOT_SERVES_MEAL_VENUE", {"meal": meal, "venue": dining.venue_type or ""})
        )
    elif dining.basis == "you":
        out.append(Reason("SLOT_SERVES_MEAL_YOU", {"meal": meal}))
    else:
        out.append(Reason("SLOT_MEAL_UNKNOWN", {"meal": meal}))
    if prev is not None and prev.transfer is not None:
        out.append(
            Reason("SLOT_NEAR_PREVIOUS", {"minutes": prev.transfer.minutes, "name": prev.name})
        )
    if nxt is not None and placed.transfer is not None:
        out.append(Reason("SLOT_NEAR_NEXT", {"minutes": placed.transfer.minutes, "name": nxt.name}))
    if nxt is None:
        out.append(Reason("SLOT_END_OF_DAY"))
    out.append(
        Reason(
            "SLOT_TRAVEL",
            {
                "day": laid.day_index,
                "minutes": added_travel,
                "label": "estimated" if estimated else "routed",
            },
        )
    )
    if replaces is not None:
        out.append(Reason("SLOT_REPLACES", {"name": replaces.name, "meal": meal}))
    else:
        out.append(Reason("SLOT_EMPTY", {"meal": meal}))
    wait = _wait(laid, placed, day_start)
    if wait > 0:
        out.append(Reason("SLOT_WAIT", {"minutes": wait}))
    if shifts:
        out.append(
            Reason(
                "SLOT_SHIFTS",
                {
                    "count": len(shifts),
                    "minutes": sum(abs(s.new_start_minute - s.old_start_minute) for s in shifts),
                },
            )
        )
    else:
        out.append(Reason("SLOT_NO_SHIFT"))
    if dining.cuisines is None:
        out.append(Reason("SLOT_CUISINE_UNKNOWN"))
    else:
        repeats = _cuisine_repeats(work, laid, placed)
        if repeats:
            out.append(Reason("SLOT_CUISINE_REPEAT", {"cuisines": ", ".join(repeats)}))
        else:
            out.append(Reason("SLOT_CUISINE_NEW", {"cuisines": ", ".join(dining.cuisines)}))
    return tuple(out)


def _blocked(day: RDay, meal: MealType) -> bool:
    """A meal the user fixed, or a locked one, keeps its slot."""
    return any(e.kind == "meal" and e.meal_type == meal and e.fixed for e in day.items)


def _legs_estimated(prev: Entry | None, placed: Entry) -> bool:
    legs = []
    if prev is not None and prev.transfer is not None:
        legs.append(prev.transfer)
    if placed.transfer is not None:
        legs.append(placed.transfer)
    return any(leg.confidence != "routed" for leg in legs)


def _prefetch(work: _Work, dining: Dining) -> None:
    """Cached travel times between the restaurant and every item of the plan (no provider)."""
    cells = []
    for d in work.days.values():
        for e in d.items:
            cells += [(e.coord, dining.coord), (dining.coord, e.coord)]
    work.lookup.fetch(cells, use_provider=False)


def _check(inp: RecalcInput, dining: Dining) -> None:
    found = inp.plan.find(dining.key)
    if found is not None:
        raise PlanningImpossible(
            [Issue("ALREADY_IN_PLAN", {"name": dining.name, "day": found[0].day_index})]
        )


def suggest(
    inp: RecalcInput,
    dining: Dining,
    source: TravelSource,
    *,
    day: int | None = None,
    meal: MealType | None = None,
    config: PlannerConfig = DEFAULT_CONFIG,
    rconfig: RecalcConfig = DEFAULT_RECALC,
) -> SlotResult:
    """Up to ``rconfig.slot_suggestions`` slots, best first (see the module docstring)."""
    _check(inp, dining)
    if meal is not None and not dining.serves(meal):
        raise PlanningImpossible(
            [
                Issue(
                    "RESTAURANT_DOES_NOT_SERVE_MEAL",
                    {
                        "name": dining.name,
                        "meal": meal,
                        "served": ", ".join(dining.meal_types or ()),
                    },
                )
            ]
        )
    work = _Work(inp, source, config, rconfig)
    _prefetch(work, dining)
    meals: list[MealType] = (
        [meal] if meal is not None else [m for m in MEAL_TYPES if dining.serves(m)]
    )
    days = sorted(work.days) if day is None else [day]
    found: list[tuple[tuple[int, int, int, int], Suggestion]] = []
    considered = 0
    issues: list[Issue] = []
    for k in days:
        current = work.days.get(k)
        if current is None or not current.visits:
            if day is not None:
                issues.append(Issue("DAY_HAS_NO_VISITS", {"day": k}))
            continue
        spec = work.spec_of(current)
        day_start = config.day_start_minute + (current.arrival.minutes if current.arrival else 0)
        for m in meals:
            if _blocked(current, m):
                continue
            considered += 1
            result = _evaluate(work, spec, dining, m, rconfig)
            if result is None:
                continue
            cost, _, laid, placed, gap = result
            n = next(i for i, e in enumerate(laid.items) if e is placed)
            prev = laid.items[n - 1] if n > 0 else None
            nxt = laid.items[n + 1] if n + 1 < len(laid.items) else None
            shifts = _shifts(current, laid, placed.key)
            replaces = _replaced(current, m)
            added = _travel(laid) - _travel(current)
            estimated = _legs_estimated(prev, placed)
            after = spec.seq[gap - 1] if gap > 0 else None
            suggestion = Suggestion(
                day_index=k,
                meal_type=m,
                after_item_id=None if after is None else after.item_id,
                after_name=None if prev is None else prev.name,
                before_name=None if nxt is None else nxt.name,
                start_minute=placed.start_minute,
                end_minute=placed.end_minute,
                cost=cost,
                travel_minutes_added=added,
                detour_m=detour_m(
                    None if prev is None else prev.coord,
                    dining.coord,
                    None if nxt is None else nxt.coord,
                ),
                estimated=estimated,
                replaces=None if replaces is None else replaces.name,
                shifts=tuple(sorted(shifts, key=lambda s: (s.new_start_minute, s.name))),
                reasons=_reasons(
                    work,
                    current,
                    laid,
                    placed,
                    dining,
                    m,
                    shifts,
                    added,
                    estimated,
                    replaces,
                    day_start,
                ),
            )
            found.append(((cost, k, placed.start_minute, MEAL_TYPES.index(m)), suggestion))
    found.sort(key=lambda f: f[0])
    top = tuple(s for _, s in found[: rconfig.slot_suggestions])
    if not top:
        issues.append(Issue("NO_SLOT_FITS", {"name": dining.name}))
    return SlotResult(top, considered, () if top else tuple(issues))


def add_restaurant(
    inp: RecalcInput,
    dining: Dining,
    day: int,
    meal: MealType,
    after_item_id: str | None,
    source: TravelSource,
    *,
    config: PlannerConfig = DEFAULT_CONFIG,
    rconfig: RecalcConfig = DEFAULT_RECALC,
    use_provider: bool = False,
) -> Revision:
    """Put the restaurant into the given slot: the meal of this type after the given item of the
    day (None: first). The day is laid out again with the new meal inside its window; nothing else
    changes day. Travel times of the changed day are asked of the provider when allowed, like
    every recalculation (a day that then no longer fits loses its lowest-value visit, which the
    diff shows)."""
    _check(inp, dining)
    if not dining.serves(meal):
        raise PlanningImpossible(
            [
                Issue(
                    "RESTAURANT_DOES_NOT_SERVE_MEAL",
                    {
                        "name": dining.name,
                        "meal": meal,
                        "served": ", ".join(dining.meal_types or ()),
                    },
                )
            ]
        )
    work = _Work(inp, source, config, rconfig)
    current = work.days.get(day)
    if current is None or not current.visits:
        raise PlanningImpossible([Issue("DAY_HAS_NO_VISITS", {"day": day})])
    fixed = next(
        (e for e in current.items if e.kind == "meal" and e.meal_type == meal and e.fixed), None
    )
    if fixed is not None:
        raise PlanningImpossible(
            [Issue("MEAL_SLOT_TAKEN", {"day": day, "name": fixed.name, "meal": meal})]
        )
    spec = work.spec_of(current)
    if after_item_id is None:
        gap = 0
    else:
        at = next((i for i, e in enumerate(spec.seq) if e.item_id == after_item_id), None)
        if at is None:
            raise PlanningImpossible([Issue("SLOT_NOT_FOUND", {"day": day, "meal": meal})])
        gap = at + 1
    _prefetch(work, dining)
    reasons = [_WINDOW_REASON[meal], "ADDED_BY_YOU"]
    reasons.append(
        {
            "venue": "VENUE_SUITS_MEAL",
            "you": "MEAL_SERVED_PER_YOU",
            "unknown": "MEAL_TYPE_NOT_SPECIFIED",
        }[dining.basis]
    )
    replaced = _replaced(current, meal)
    if dining.cuisines is None:
        reasons.append(
            "CUISINE_NOT_SPECIFIED"
            if dining.user_place_id is None
            else "CUISINE_NOT_SPECIFIED_BY_YOU"
        )
    else:
        # "Adds a cuisine this plan does not have yet": true only if no other meal has one of its
        # cuisines (the meal it replaces leaves the plan).
        others = {
            c
            for d in work.days.values()
            for e in d.items
            if e.kind == "meal" and e is not replaced
            for c in (e.cuisines or ())
        }
        if not others.intersection(dining.cuisines):
            reasons.append("NEW_CUISINE")
    floating = dining.entry(meal, config, floating=True, reasons=reasons)
    trial = _trial_seq(spec, floating, gap)
    laid = work.lay_out(trial)
    if laid is None:
        raise PlanningImpossible(
            [
                Issue(
                    "MEAL_DOES_NOT_FIT",
                    {
                        "day": day,
                        "name": dining.name,
                        "meal": meal,
                        "window_start": _fmt(config.meal_window(meal).start_minute),
                        "window_end": _fmt(config.meal_window(meal).end_minute),
                    },
                )
            ]
        )
    work.days[day] = laid
    _finish(work, {day: trial}, use_provider, floating)
    # The meal now has its time and keeps it, like every meal the user added.
    laid_day = work.days[day]
    close = _close_to(laid_day, dining, config)
    work.days[day] = replace(
        laid_day,
        items=tuple(
            replace(e, floating=False, reasons=_ordered((*e.reasons, *(("ON_THE_WAY",) * close))))
            if e.key == dining.key
            else e
            for e in laid_day.items
        ),
    )
    notes = [Note("RESTAURANT_ADDED", {"name": dining.name, "meal": meal, "day": day})]
    if replaced is not None:
        notes.append(Note("MEAL_REPLACED", {"name": replaced.name, "meal": meal, "day": day}))
    option = _Option(0, (day,), {day: trial}, {day: work.days[day]}, 0, 0)
    return _revision(work, option, notes)


def _close_to(laid: RDay, dining: Dining, config: PlannerConfig) -> bool:
    """Close to the items either side of it: the straight-line detour is within the first ring
    (the engine's ON_THE_WAY, ADR 016)."""
    items = laid.items
    n = next(i for i, e in enumerate(items) if e.key == dining.key)
    prev = items[n - 1].coord if n > 0 else None
    nxt = items[n + 1].coord if n + 1 < len(items) else None
    if prev is None and nxt is None:
        return False
    anchors = [c for c in (prev, nxt) if c is not None]
    return min(distance_m(a, dining.coord) for a in anchors) <= config.meal_search_m[0]
