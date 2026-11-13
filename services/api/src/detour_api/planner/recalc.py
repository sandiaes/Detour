"""Recalculation after the user adds or removes a place (Phase 7, ADR 018; architecture 5.4).

The plan the user has is repaired, not planned again: only the days that must change do change,
and among the ways to absorb an addition the one with the lowest **stability cost** wins.

    stability cost = travel_weight x added travel minutes (transfers and inter-city drives)
                   + move_day_cost              per existing visit that changes day
                   + value + drop_extra_cost    per existing visit left out
                   + retime_cost                per existing item whose start time changes

All integers; ties go to the earlier day, then the earlier position. No randomness, no clock.

**Items that never move.** A ``locked`` item keeps its day, its start and its end (a fixed block
that the day is laid out around), and is never removed. Items the user added (``origin = user``)
are mandatory: a recalculation never leaves one out. A meal the user added stays where it is.

**Adding a place** (it becomes a mandatory visit, reason ``ADDED_BY_YOU``):

* Near a base city of the plan (within ``new_base_min_m``): it is inserted into a day at that
  base, at the cheapest position. If the day no longer fits, its lowest-value engine visits are
  taken out one by one; each is moved to another day at the same base if it fits there without
  pushing anything else out, else it is left out. Every day at that base is tried.
* Far from every base: one day is re-allocated to a **new base city**, the nearest town to the
  place (ADR 016's inter-city legs then start that day and the next). The day comes from a base
  that has at least two days, at the start or end of its run, so the bases' runs stay
  consecutive and no city disappears. The new day holds the place plus the sights the heuristic
  sequencer picks around the new base. The old day's visits move to other days at their base if
  they fit, else they are left out. Days with locked items or items the user added are not
  re-allocated.

**Removing a place** takes the visit out of its day and lays the day out again (its meals follow).
Undoing an addition exactly is the job of versioning (``repo/changes.py``), not of this module.

**Meals move with the day** and stay at imported places to eat (ADR 016): a changed day's meals
are laid out again in their windows, keeping the place to eat the day had for that meal when it is
still within reach, else choosing one as the engine does.

**Travel times:** cached times and labelled estimates while choosing; then the changed days' legs
are asked of the travel source with the provider allowed (if ``use_provider``), the days are laid
out again, and a day that no longer fits loses its lowest-value engine visit. If a mandatory item
no longer fits, the recalculation is refused with the reason.

When nothing works, ``PlanningImpossible`` carries one issue per conflicting constraint (which day,
which items cannot move). Nothing is ever left out without appearing in the result.
"""

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Literal

from detour_api.planner import scoring
from detour_api.planner.config import DEFAULT_CONFIG, MealType, PlannerConfig, Profile
from detour_api.planner.durations import visit_minutes
from detour_api.planner.meals import Choice, RestaurantIndex, choose, detour_m
from detour_api.planner.reasons import ITEM_TEMPLATES
from detour_api.planner.sequencer import HeuristicSequencer, Sequencer, SequencingProblem
from detour_api.planner.travel import Cell, TravelLookup, TravelSource, minutes
from detour_api.planner.types import (
    BaseCity,
    Candidate,
    Issue,
    Leg,
    Note,
    NoteParams,
    PlanningImpossible,
    PlanStats,
    Restaurant,
)
from detour_api.travel.types import Coord, TravelTime, distance_m

RECALC_VERSION = "recalc-1.1.0"
FOLLOW_UP_FETCHES = 2
# How many of the cheapest insertion positions (by added travel) are laid out in full.
POSITIONS_TRIED = 4

_REASON_ORDER = {code: i for i, code in enumerate(ITEM_TEMPLATES)}
_WINDOW_REASON = {
    "breakfast": "BREAKFAST_WINDOW",
    "lunch": "LUNCH_WINDOW",
    "snack": "SNACK_WINDOW",
    "dinner": "DINNER_WINDOW",
}
# Notes a recalculation replaces (they describe the plan's current shape or the last change).
REPLACED_NOTES = frozenset(
    {
        "ESTIMATED_TRANSFERS",
        "INTER_CITY_TRAVEL",
        "BASE_CITY",
        "BASE_CITY_DAYS",
        "PLACE_ADDED",
        "PLACE_REMOVED",
        "PLAN_RESTORED",
        "NEW_BASE_DAY",
        "VISITS_MOVED",
        "VISITS_DROPPED",
        "RESTAURANT_ADDED",
        "MEAL_REPLACED",
    }
)


@dataclass(frozen=True)
class RecalcConfig:
    """Recalculation settings (planning choices, not facts). Part of the configuration version
    stored on a recalculated itinerary."""

    version: str = "2026-11-13.2"
    # An addition farther than this (straight line) from every base city of the plan gets a day
    # at a new base. The same distance ADR 016 keeps between bases.
    new_base_min_m: int = 20_000
    # The new base is the nearest gazetteer town within this distance of the addition.
    new_base_town_m: int = 25_000
    # Stability cost, in value units (a 50-point sight is worth 500; a minute of travel costs the
    # profile's travel weight, 10 for Essentials).
    move_day_cost: int = 300
    drop_extra_cost: int = 200
    retime_cost: int = 5
    # The sequencer value given to the added place on a new base day, so it is always planned.
    pinned_value: int = 1_000_000_000

    # -- adding a restaurant (Phase 8, ADR 019; restaurant_slots.py) -----------------------------
    # How many slots are suggested.
    slot_suggestions: int = 3
    # Location: the straight-line detour from the neighbouring items costs one unit per this many
    # metres (so 400 m costs 20, two minutes of Essentials travel).
    slot_detour_m_per_unit: int = 20
    # Other items that start at another time: retime_cost each, plus this per minute of shift.
    slot_shift_minute_cost: int = 1
    # Waiting at the restaurant for the meal window to open, per minute.
    slot_wait_minute_cost: int = 2
    # The new meal replaces a meal the plan has (the engine's meal of that type is lost).
    slot_replace_meal_cost: int = 200
    # Its cuisine is already in a meal of this day or the days either side.
    slot_cuisine_repeat_cost: int = 150
    # The meals the place serves are unknown (it is judged by place and timing alone).
    slot_meal_unknown_cost: int = 100


DEFAULT_RECALC = RecalcConfig()


def config_version(config: PlannerConfig, rconfig: RecalcConfig) -> str:
    return f"{config.version}+recalc-{rconfig.version}"


# -- the plan as the recalculation sees it -------------------------------------------------------


def entry_key(kind: str, place_id: str | None, user_place_id: str | None) -> str:
    """Identity of a place in a plan: a visit is ``place:<id>`` or ``user:<id>``; a meal adds the
    ``meal:`` prefix (a place to eat may be used on more than one day)."""
    ref = f"place:{place_id}" if place_id is not None else f"user:{user_place_id}"
    return ref if kind == "visit" else f"meal:{ref}"


@dataclass(frozen=True)
class Entry:
    """A timed visit or meal of a plan."""

    key: str
    kind: Literal["visit", "meal"]
    name: str
    lat: float
    lon: float
    start_minute: int
    end_minute: int
    duration_minutes: int
    duration_source: Literal["category_default", "user"]
    origin: Literal["engine", "user"]
    locked: bool
    reasons: tuple[str, ...]
    transfer: Leg | None = None  # to the next item of the day
    place_id: str | None = None
    user_place_id: str | None = None
    # Visits: the attraction's category (None for a user place or when unknown). Meals: venue.
    category: str | None = None
    meal_type: MealType | None = None
    cuisines: tuple[str, ...] | None = None
    item_id: str | None = None  # the stored item it continues; None for a new one
    # A meal the user is adding (Phase 8, ADR 019) whose time the layout still has to find: it
    # starts when its window opens or when the traveller arrives, whichever is later. Never stored:
    # the layout's result is a fixed meal.
    floating: bool = False

    @property
    def coord(self) -> Coord:
        return Coord.from_degrees(self.lat, self.lon)

    @property
    def fixed(self) -> bool:
        """Keeps its day and its times: a locked item, or a meal the user added."""
        return self.locked or (self.kind == "meal" and self.origin == "user" and not self.floating)

    @property
    def mandatory(self) -> bool:
        return self.origin == "user" or self.locked


@dataclass(frozen=True)
class RDay:
    day_index: int
    date: date | None
    base_city_id: int | None
    base_city_name: str | None
    items: tuple[Entry, ...]
    arrival: Leg | None = None

    @property
    def visits(self) -> tuple[Entry, ...]:
        return tuple(e for e in self.items if e.kind == "visit")


@dataclass(frozen=True)
class RPlan:
    profile: str
    days: tuple[RDay, ...]

    def find(self, key: str) -> tuple[RDay, Entry] | None:
        for d in self.days:
            for e in d.items:
                if e.key == key:
                    return d, e
        return None


@dataclass(frozen=True)
class Addition:
    """The place the user adds: an imported attraction or one of the user's own places."""

    key: str
    name: str
    lat: float
    lon: float
    duration_minutes: int
    duration_source: Literal["category_default", "user"]
    place_id: str | None = None
    user_place_id: str | None = None
    category: str | None = None

    @property
    def coord(self) -> Coord:
        return Coord.from_degrees(self.lat, self.lon)

    def entry(self) -> Entry:
        return Entry(
            key=self.key,
            kind="visit",
            name=self.name,
            lat=self.lat,
            lon=self.lon,
            start_minute=0,
            end_minute=0,
            duration_minutes=self.duration_minutes,
            duration_source=self.duration_source,
            origin="user",
            locked=False,
            reasons=("ADDED_BY_YOU",),
            place_id=self.place_id,
            user_place_id=self.user_place_id,
            category=self.category,
        )


@dataclass(frozen=True)
class RecalcInput:
    plan: RPlan
    notes: tuple[Note, ...]  # the plan's current notes
    bases: Mapping[int, BaseCity]  # every base city of the plan, by id
    candidates: Sequence[Candidate]  # sights around the bases (and the addition)
    restaurants: Sequence[Restaurant]
    towns: Sequence[BaseCity] = ()  # possible new bases near the addition
    # A country planned as single-city trips (Japan, app plan D4): no new base cities.
    single_city: bool = False


@dataclass(frozen=True)
class Revision:
    plan: RPlan
    changed_days: tuple[int, ...]
    notes: tuple[Note, ...]
    stats: PlanStats
    bases: Mapping[int, BaseCity]  # including a new base
    known_times: Mapping[Cell, TravelTime] = field(default_factory=dict)


# -- the working state ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Spec:
    """A day to lay out: its visits and fixed items in order (engine meals are placed by the
    layout), its base, the inter-city leg that starts it, and the places to eat it had."""

    index: int
    base_id: int | None
    base_name: str | None
    arrival_cell: Cell | None
    seq: tuple[Entry, ...]
    preferred: Mapping[str, str]


@dataclass(frozen=True)
class _Option:
    cost: int
    order: tuple[int, ...]
    specs: Mapping[int, _Spec]
    days: Mapping[int, RDay]  # every day the option changed, laid out
    moved: int
    dropped: int


class _Work:
    def __init__(
        self,
        inp: RecalcInput,
        source: TravelSource,
        config: PlannerConfig,
        rconfig: RecalcConfig,
    ) -> None:
        self.inp = inp
        self.config = config
        self.rconfig = rconfig
        self.profile: Profile = config.profile(inp.plan.profile)  # type: ignore[arg-type]
        self.lookup = TravelLookup(source, config.walk_max_m)
        self.cands = {c.place_id: c for c in inp.candidates}
        plan_restaurants = {r.place_id: r for r in inp.restaurants}
        self.index = RestaurantIndex(plan_restaurants.values())
        self.bases: dict[int, BaseCity] = dict(inp.bases)
        self.days: dict[int, RDay] = {d.day_index: d for d in inp.plan.days}
        self.old = {d.day_index: d for d in inp.plan.days}
        self._seed()

    # -- travel ----------------------------------------------------------------------------

    def _seed(self) -> None:
        """The stored transfers and drives are what the travel source returned when the plan was
        made: an unchanged pair keeps its value."""
        known: dict[Cell, TravelTime] = {}
        prev_base: int | None = None
        for d in self.inp.plan.days:
            for a, b in zip(d.items, d.items[1:], strict=False):
                if a.transfer is not None:
                    known[(a.coord, b.coord)] = _time_of(a.transfer)
            if d.arrival is not None and prev_base in self.bases and d.base_city_id in self.bases:
                from_city, to_city = self.bases[prev_base], self.bases[d.base_city_id]
                known[(from_city.coord, to_city.coord)] = _time_of(d.arrival)
            prev_base = d.base_city_id
        self.lookup.seed(known)

    def mins(self, a: Coord, b: Coord) -> int:
        return 0 if a == b else minutes(self.lookup.get(a, b).seconds)

    def leg(self, a: Coord, b: Coord) -> Leg:
        t = self.lookup.get(a, b)
        return Leg(
            mode=self.lookup.mode(a, b),
            seconds=t.seconds,
            meters=t.meters,
            minutes=minutes(t.seconds),
            confidence=t.confidence,
            estimate_reason=t.reason,
        )

    def arrival_cell(self, prev_base: int | None, base: int | None) -> Cell | None:
        if prev_base is None or base is None or prev_base == base:
            return None
        return (self.bases[prev_base].coord, self.bases[base].coord)

    # -- values ----------------------------------------------------------------------------

    def value(self, e: Entry) -> int:
        c = self.cands.get(e.place_id or "")
        return 0 if c is None else scoring.base_value(c, self.config) * self.config.value_scale

    def removable(self, e: Entry) -> bool:
        return e.kind == "visit" and not e.mandatory

    # -- meal context ------------------------------------------------------------------------

    def _meal_places(self, days: Iterable[RDay]) -> set[str]:
        return {e.place_id for d in days for e in d.items if e.kind == "meal" and e.place_id}

    def context(self, index: int) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
        """(places to eat on earlier days, on any other day, cuisines of earlier days)."""
        before = [d for i, d in sorted(self.days.items()) if i < index]
        others = [d for i, d in self.days.items() if i != index]
        seen = {c for d in before for e in d.items if e.kind == "meal" for c in (e.cuisines or ())}
        return (
            frozenset(self._meal_places(before)),
            frozenset(self._meal_places(others)),
            frozenset(seen),
        )

    def spec_of(self, day: RDay) -> _Spec:
        prev = self.days.get(day.day_index - 1)
        return _Spec(
            index=day.day_index,
            base_id=day.base_city_id,
            base_name=day.base_city_name,
            arrival_cell=self.arrival_cell(
                None if prev is None else prev.base_city_id, day.base_city_id
            ),
            seq=tuple(e for e in day.items if e.kind == "visit" or e.fixed),
            preferred={
                e.meal_type: e.place_id
                for e in day.items
                if e.kind == "meal" and not e.fixed and e.meal_type and e.place_id
            },
        )

    # -- laying out a day --------------------------------------------------------------------

    def _choose(
        self,
        meal: MealType,
        prev: Coord | None,
        nxt: Coord | None,
        preferred: str | None,
        used_other: frozenset[str],
        today: set[str],
        seen: set[str],
    ) -> Choice | None:
        anchors = [c for c in (prev, nxt) if c is not None]
        if not anchors:
            return None
        r = self.index.by_id.get(preferred or "")
        if r is not None and r.place_id not in today and meal in r.meal_types:
            near = min(distance_m(a, r.coord) for a in anchors)
            for ring, radius in enumerate(self.config.meal_search_m):
                if near <= radius:
                    return Choice(r, detour_m(prev, r.coord, nxt), ring)
        return choose(self.index, meal, prev, nxt, used_other, seen, self.config, today)

    def _end_after(self, e: Entry, arrive: int) -> int:
        """When ``e`` would end if the traveller reaches it at ``arrive``."""
        if e.fixed:
            return e.end_minute
        if e.floating:
            return max(arrive, self.config.meal_window(e.meal_type or "").start_minute) + (
                e.duration_minutes
            )
        return arrive + e.duration_minutes

    def lay_out(self, spec: _Spec) -> RDay | None:
        """The day with its meals in their windows and its transfers, or None if it does not fit
        (a fixed item that cannot be reached in time, a meal outside its window, a visit past the
        day's end)."""
        config, profile = self.config, self.profile
        used_before, used_other, seen_before = self.context(spec.index)
        arrival = None if spec.arrival_cell is None else self.leg(*spec.arrival_cell)
        day_start = config.day_start_minute + (arrival.minutes if arrival else 0)
        day_end = min(profile.day_end_minute, config.day_window_end_minute)
        seq = spec.seq
        has_visits = any(e.kind == "visit" for e in seq)
        fixed_meals = {e.meal_type for e in seq if e.kind == "meal"}
        pending: list[MealType] = []
        if has_visits:
            for meal in profile.meals:
                w = config.meal_window(meal)
                latest = min(w.end_minute, day_end)
                if meal in fixed_meals:
                    continue
                if max(day_start, w.start_minute) + config.meal_minutes(meal, None) <= latest:
                    pending.append(meal)

        slots: list[Entry] = []
        today = {e.place_id for e in seq if e.kind == "meal" and e.place_id}
        seen = set(seen_before)
        clock = day_start
        prev: Coord | None = None
        i = 0
        deferred: MealType | None = None
        while i < len(seq) or pending:
            if pending and pending[0] != deferred:
                meal = pending[0]
                w = config.meal_window(meal)
                latest = min(w.end_minute, day_end)
                e = seq[i] if i < len(seq) else None
                now = e is None
                if e is not None:
                    arrive = clock if prev is None else clock + self.mins(prev, e.coord)
                    if e.fixed:
                        arrive = max(arrive, e.start_minute)
                    if arrive >= w.start_minute:
                        now = True
                    else:
                        end_e = self._end_after(e, arrive)
                        after = seq[i + 1].coord if i + 1 < len(seq) else None
                        probe = self._choose(
                            meal, e.coord, after, spec.preferred.get(meal), used_other, today, seen
                        )
                        if probe is None:
                            reach = config.meal_allowance_minutes
                            length = config.meal_minutes(meal, None)
                        else:
                            reach = self.mins(e.coord, probe.restaurant.coord)
                            length = config.meal_minutes(meal, probe.restaurant.venue_type)
                        if max(end_e + reach, w.start_minute) + length > latest:
                            now = True
                if now:
                    choice = self._choose(
                        meal,
                        prev,
                        None if e is None else e.coord,
                        spec.preferred.get(meal),
                        used_other,
                        today,
                        seen,
                    )
                    if choice is None:
                        pending.pop(0)
                        continue
                    r = choice.restaurant
                    reach_r = clock if prev is None else clock + self.mins(prev, r.coord)
                    start = max(reach_r, w.start_minute)
                    length = config.meal_minutes(meal, r.venue_type)
                    end = start + length
                    if end > latest:
                        return None
                    if (
                        e is not None
                        and e.fixed
                        and end + self.mins(r.coord, e.coord) > (e.start_minute)
                    ):
                        # No time to eat before the fixed item: eat after it if the window allows.
                        if max(e.end_minute, w.start_minute) + length <= latest:
                            deferred = meal
                            continue
                        return None
                    pending.pop(0)
                    deferred = None
                    reasons = [_WINDOW_REASON[meal], "VENUE_SUITS_MEAL"]
                    reasons.append("ON_THE_WAY" if choice.ring == 0 else "NEAREST_SUITABLE")
                    if r.place_id in used_before:
                        reasons.append("PLACE_REPEATED")
                    if r.cuisines is None:
                        reasons.append("CUISINE_NOT_SPECIFIED")
                    elif not seen.issuperset(r.cuisines):
                        reasons.append("NEW_CUISINE")
                    slots.append(
                        Entry(
                            key=entry_key("meal", r.place_id, None),
                            kind="meal",
                            name=r.name,
                            lat=r.lat,
                            lon=r.lon,
                            start_minute=start,
                            end_minute=end,
                            duration_minutes=length,
                            duration_source="category_default",
                            origin="engine",
                            locked=False,
                            reasons=_ordered(reasons),
                            place_id=r.place_id,
                            category=r.venue_type,
                            meal_type=meal,
                            cuisines=r.cuisines,
                            item_id=_old_meal_id(self.old.get(spec.index), meal, r.place_id),
                        )
                    )
                    today.add(r.place_id)
                    seen.update(r.cuisines or ())
                    clock, prev = end, r.coord
                    continue
            if i >= len(seq):
                # Only a deferred meal is left and nothing follows to defer it past.
                deferred = None
                continue
            e = seq[i]
            arrive = clock if prev is None else clock + self.mins(prev, e.coord)
            if e.fixed:
                if prev is not None and arrive > e.start_minute:
                    return None
                start, end = e.start_minute, e.end_minute
            elif e.floating:
                # A meal being added: in its window, and inside the day.
                fw = config.meal_window(e.meal_type or "")
                start = max(arrive, fw.start_minute)
                end = start + e.duration_minutes
                if end > min(fw.end_minute, day_end):
                    return None
            else:
                start = arrive
                end = start + e.duration_minutes
                if end > day_end:
                    return None
            if e.kind == "meal":
                seen.update(e.cuisines or ())
            slots.append(replace(e, start_minute=start, end_minute=end))
            clock, prev = end, e.coord
            i += 1
            deferred = None

        # Transfers between consecutive items, and the reasons that depend on them.
        out: list[Entry] = []
        for n, slot in enumerate(slots):
            leg = self.leg(slot.coord, slots[n + 1].coord) if n + 1 < len(slots) else None
            reasons = list(slot.reasons)
            if slot.kind == "visit":
                reasons = [r for r in reasons if r != "NEAR_PREVIOUS_ITEM"]
                before = out[-1] if out else None
                if (
                    before is not None
                    and before.kind == "visit"
                    and before.transfer is not None
                    and before.transfer.minutes <= config.near_previous_minutes
                ):
                    reasons.append("NEAR_PREVIOUS_ITEM")
                if not reasons:
                    reasons.append("NAMED_SIGHT")
            out.append(replace(slot, transfer=leg, reasons=_ordered(reasons)))
        old = self.old.get(spec.index)
        return RDay(
            day_index=spec.index,
            date=None if old is None else old.date,
            base_city_id=spec.base_id,
            base_city_name=spec.base_name,
            items=tuple(out),
            arrival=arrival,
        )

    def fit(
        self, spec: _Spec, keep: frozenset[str] = frozenset()
    ) -> tuple[_Spec, RDay, list[Entry]] | None:
        """Lay the day out, leaving out its lowest-value engine visits (never ``keep``) until it
        fits. None if it cannot fit with every removable visit left out."""
        dropped: list[Entry] = []
        while True:
            laid = self.lay_out(spec)
            if laid is not None:
                return spec, laid, dropped
            removable = [e for e in spec.seq if self.removable(e) and e.key not in keep]
            if not removable:
                return None
            drop = min(removable, key=lambda e: (self.value(e), e.key))
            dropped.append(drop)
            spec = replace(spec, seq=tuple(e for e in spec.seq if e is not drop))

    def positions(self, spec: _Spec, e: Entry) -> list[int]:
        """Insertion positions, cheapest added travel first (ties by position)."""
        seq = spec.seq
        out: list[tuple[int, int]] = []
        for p in range(len(seq) + 1):
            a = seq[p - 1].coord if p > 0 else None
            b = seq[p].coord if p < len(seq) else None
            delta = 0
            if a is not None:
                delta += self.mins(a, e.coord)
            if b is not None:
                delta += self.mins(e.coord, b)
            if a is not None and b is not None:
                delta -= self.mins(a, b)
            out.append((delta, p))
        return [p for _, p in sorted(out)[:POSITIONS_TRIED]]

    def insert(
        self, spec: _Spec, e: Entry, *, allow_drops: bool
    ) -> tuple[int, _Spec, RDay, list[Entry]] | None:
        """The cheapest insertion of e into the day: (cost, spec, laid day, visits left out)."""
        best: tuple[tuple[int, int], _Spec, RDay, list[Entry]] | None = None
        weight = self.profile.travel_weight
        for p in self.positions(spec, e):
            trial = replace(spec, seq=(*spec.seq[:p], e, *spec.seq[p:]))
            if allow_drops:
                fitted = self.fit(trial, keep=frozenset({e.key}))
                if fitted is None:
                    continue
                trial, laid, dropped = fitted
            else:
                laid_or_none = self.lay_out(trial)
                if laid_or_none is None:
                    continue
                laid, dropped = laid_or_none, []
            cost = weight * _travel(laid) + sum(
                self.value(d) + self.rconfig.drop_extra_cost for d in dropped
            )
            if best is None or (cost, p) < best[0]:
                best = ((cost, p), trial, laid, dropped)
        if best is None:
            return None
        return best[0][0], best[1], best[2], best[3]

    def rehome(
        self, lost: Sequence[Entry], days: Sequence[int], specs: dict[int, _Spec]
    ) -> tuple[int, int]:
        """Move visits a changed day lost to other days (only where they fit without pushing
        anything out). Updates ``specs`` and the working days; (moved, dropped)."""
        moved = dropped = 0
        for e in sorted(lost, key=lambda e: (-self.value(e), e.key)):
            best: tuple[tuple[int, int], int, _Spec, RDay] | None = None
            for k in days:
                spec = specs.get(k) or self.spec_of(self.days[k])
                before = _travel(self.days[k])
                found = self.insert(spec, e, allow_drops=False)
                if found is None:
                    continue
                cost = found[0] - self.profile.travel_weight * before
                if best is None or (cost, k) < best[0]:
                    best = ((cost, k), k, found[1], found[2])
            if best is None:
                dropped += 1
                continue
            _, k, spec, laid = best
            specs[k] = spec
            self.days[k] = laid
            moved += 1
        return moved, dropped

    # -- the cost of an option --------------------------------------------------------------

    def option_cost(self, specs: Mapping[int, _Spec], moved: int, dropped_value: int) -> int:
        weight = self.profile.travel_weight
        travel_delta = sum(_travel(self.days[k]) - _travel(self.old[k]) for k in specs)
        retimed = 0
        for k in specs:
            old = {e.key: e.start_minute for e in self.old[k].items}
            retimed += sum(
                1 for e in self.days[k].items if e.key in old and old[e.key] != e.start_minute
            )
        return (
            weight * travel_delta
            + self.rconfig.move_day_cost * moved
            + dropped_value
            + self.rconfig.retime_cost * retimed
        )

    def snapshot(self) -> dict[int, RDay]:
        return dict(self.days)

    def restore(self, days: dict[int, RDay]) -> None:
        self.days = dict(days)


def _time_of(leg: Leg) -> TravelTime:
    return TravelTime(
        leg.seconds,
        leg.meters,
        leg.confidence,
        "cache",
        None if leg.confidence == "routed" else (leg.estimate_reason or "provider_not_asked"),
    )


def _old_meal_id(day: RDay | None, meal: str, place_id: str) -> str | None:
    if day is None:
        return None
    for e in day.items:
        if e.kind == "meal" and e.meal_type == meal and e.place_id == place_id and not e.fixed:
            return e.item_id
    return None


def _ordered(reasons: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(set(reasons), key=lambda c: _REASON_ORDER.get(c, len(_REASON_ORDER))))


def _travel(day: RDay) -> int:
    total = sum(e.transfer.minutes for e in day.items if e.transfer is not None)
    return total + (day.arrival.minutes if day.arrival is not None else 0)


def _km(meters: float) -> int:
    return int(meters // 1000)


def _names(entries: Iterable[Entry]) -> str:
    return ", ".join(e.name for e in entries) or "none"


# -- adding a place ------------------------------------------------------------------------------


def add_place(
    inp: RecalcInput,
    addition: Addition,
    source: TravelSource,
    *,
    config: PlannerConfig = DEFAULT_CONFIG,
    rconfig: RecalcConfig = DEFAULT_RECALC,
    sequencer: Sequencer | None = None,
    use_provider: bool = False,
) -> Revision:
    found = inp.plan.find(addition.key)
    if found is not None:
        raise PlanningImpossible(
            [Issue("ALREADY_IN_PLAN", {"name": addition.name, "day": found[0].day_index})]
        )
    work = _Work(inp, source, config, rconfig)
    x = addition.entry()
    longest = config.day_minutes(work.profile) - config.meal_reserve(work.profile)
    if x.duration_minutes > longest:
        raise PlanningImpossible(
            [
                Issue(
                    "ADDITION_LONGER_THAN_DAY",
                    {"name": x.name, "minutes": x.duration_minutes, "day_minutes": longest},
                )
            ]
        )

    distances = {
        bid: distance_m(addition.coord, b.coord)
        for bid, b in work.bases.items()
        if any(d.base_city_id == bid for d in inp.plan.days)
    }
    nearest = min(distances.values()) if distances else math.inf
    notes: list[Note] = []
    if nearest <= rconfig.new_base_min_m:
        near_bases = {b for b, d in distances.items() if d <= rconfig.new_base_min_m}
        days = [d.day_index for d in inp.plan.days if d.base_city_id in near_bases]
        option = _same_base(work, x, days)
    else:
        if inp.single_city:
            raise PlanningImpossible(
                [Issue("SINGLE_CITY_ONLY", {"name": x.name, "km": _km(nearest)})]
            )
        town = _nearest_town(addition, inp.towns, rconfig)
        if town is None:
            raise PlanningImpossible(
                [
                    Issue(
                        "NO_TOWN_NEAR_ADDITION",
                        {
                            "name": x.name,
                            "km": _km(nearest),
                            "radius_km": _km(rconfig.new_base_town_m),
                        },
                    )
                ]
            )
        if town.city_id in work.bases and any(
            d.base_city_id == town.city_id for d in inp.plan.days
        ):
            days = [d.day_index for d in inp.plan.days if d.base_city_id == town.city_id]
            option = _same_base(work, x, days)
        else:
            work.bases[town.city_id] = town
            option = _new_base(work, x, town, nearest, sequencer or HeuristicSequencer())
            day = option.order[0]
            notes.append(
                Note(
                    "NEW_BASE_DAY",
                    {
                        "day": day,
                        "name": town.name,
                        "km": _km(
                            min(distance_m(town.coord, work.bases[b].coord) for b in distances)
                        ),
                        "place": x.name,
                    },
                )
            )
    _finish(work, option.specs, use_provider, x)
    day_of_x = next(d.day_index for d in work.days.values() for e in d.items if e.key == x.key)
    notes.insert(0, Note("PLACE_ADDED", {"name": x.name, "day": day_of_x}))
    return _revision(work, option, notes)


def _nearest_town(
    addition: Addition, towns: Sequence[BaseCity], rconfig: RecalcConfig
) -> BaseCity | None:
    within = [
        (distance_m(addition.coord, t.coord), t.city_id, t)
        for t in towns
        if distance_m(addition.coord, t.coord) <= rconfig.new_base_town_m
    ]
    return min(within, key=lambda w: (w[0], w[1]))[2] if within else None


def _same_base(work: _Work, x: Entry, days: Sequence[int]) -> _Option:
    """Insert x into one of ``days`` (all at bases near it), choosing the day by stability cost."""
    best: _Option | None = None
    issues: list[Issue] = []
    start = work.snapshot()
    for k in days:
        work.restore(start)
        spec = work.spec_of(work.days[k])
        found = work.insert(spec, x, allow_drops=True)
        if found is None:
            fixed = [e for e in spec.seq if e.mandatory]
            params: NoteParams = {"day": k, "name": x.name, "minutes": x.duration_minutes}
            if fixed:
                params["items"] = _names(fixed)
            code = "DAY_FULL_OF_FIXED_ITEMS" if fixed else "DAY_TOO_SHORT_FOR_ADDITION"
            issues.append(Issue(code, params))
            continue
        _, new_spec, laid, lost = found
        specs = {k: new_spec}
        work.days[k] = laid
        moved, dropped = work.rehome(lost, [d for d in days if d != k], specs)
        kept = {e.key for d in work.days.values() for e in d.items}
        dropped_value = sum(
            work.value(e) + work.rconfig.drop_extra_cost for e in lost if e.key not in kept
        )
        cost = work.option_cost(specs, moved, dropped_value)
        changed = {d: work.days[d] for d in specs}
        option = _Option(cost, (k,), dict(specs), changed, moved, dropped)
        if best is None or (cost, k) < (best.cost, best.order[0]):
            best = option
    if best is None:
        raise PlanningImpossible(issues)
    work.restore(start)
    work.days.update(best.days)
    return best


def _new_base(
    work: _Work, x: Entry, town: BaseCity, nearest: float, sequencer: Sequencer
) -> _Option:
    """Give one day to a new base city near x: the first or last day of a base's run of at least
    two days. The options are ranked by stability cost."""
    plan = work.inp.plan
    runs: list[tuple[int | None, list[int]]] = []
    for d in plan.days:
        if runs and runs[-1][0] == d.base_city_id:
            runs[-1][1].append(d.day_index)
        else:
            runs.append((d.base_city_id, [d.day_index]))
    candidates_days: list[tuple[int, list[int]]] = []  # (day, the other days of its run)
    issues: list[Issue] = []
    for _, run in runs:
        if len(run) < 2:
            continue
        for k in sorted({run[0], run[-1]}):
            fixed = [e for e in work.days[k].items if e.mandatory]
            if fixed:
                issues.append(Issue("DAY_HAS_FIXED_ITEMS", {"day": k, "items": _names(fixed)}))
                continue
            candidates_days.append((k, [d for d in run if d != k]))
    if not candidates_days and not issues:
        names = ", ".join(f"{plan.days[run[0] - 1].base_city_name}" for _, run in runs)
        raise PlanningImpossible(
            [
                Issue(
                    "NO_DAY_FOR_NEW_BASE",
                    {"name": x.name, "km": _km(nearest), "bases": names},
                )
            ]
        )
    start = work.snapshot()
    best: _Option | None = None
    for k, rest in candidates_days:
        work.restore(start)
        result = _try_new_base_day(work, x, town, k, rest, sequencer)
        if isinstance(result, Issue):
            issues.append(result)
            continue
        if best is None or (result.cost, k) < (best.cost, best.order[0]):
            best = result
    if best is None:
        raise PlanningImpossible(issues)
    work.restore(start)
    work.days.update(best.days)
    return best


def _try_new_base_day(
    work: _Work, x: Entry, town: BaseCity, k: int, rest: list[int], sequencer: Sequencer
) -> "_Option | Issue":
    config, profile = work.config, work.profile
    old_day = work.days[k]
    prev = work.days.get(k - 1)
    arrival_cell = work.arrival_cell(None if prev is None else prev.base_city_id, town.city_id)
    drive = 0 if arrival_cell is None else work.mins(*arrival_cell)
    limit = max(0, config.visit_budget(profile) - drive)
    if x.duration_minutes > limit:
        return Issue(
            "DRIVE_LEAVES_NO_TIME",
            {
                "day": k,
                "drive_minutes": drive,
                "base": town.name,
                "name": x.name,
                "minutes": x.duration_minutes,
            },
        )
    # The new day: x plus the sights the sequencer picks around the new base.
    in_plan = {e.place_id for d in work.days.values() for e in d.items if e.place_id}
    pool = scoring.score(
        [c for c in work.inp.candidates if c.place_id not in in_plan and c.place_id != x.place_id],
        town.coord,
        profile,
        config,
        config.max_candidates(1),
    )
    nodes: list[tuple[str, Entry, int]] = [(x.key, x, work.rconfig.pinned_value)]
    for s in pool:
        c = s.candidate
        reasons = scoring.static_reasons(c, s.distance_m, config) or ["NAMED_SIGHT"]
        nodes.append(
            (
                entry_key("visit", c.place_id, None),
                Entry(
                    key=entry_key("visit", c.place_id, None),
                    kind="visit",
                    name=c.name,
                    lat=c.lat,
                    lon=c.lon,
                    start_minute=0,
                    end_minute=0,
                    duration_minutes=visit_minutes(c.category),
                    duration_source="category_default",
                    origin="engine",
                    locked=False,
                    reasons=_ordered(reasons),
                    place_id=c.place_id,
                    category=c.category,
                ),
                s.value,
            )
        )
    nodes.sort(key=lambda n: n[0])
    coords = [n[1].coord for n in nodes]
    work.lookup.fetch(((a, b) for a in coords for b in coords if a != b), use_provider=False)
    problem = SequencingProblem(
        ids=tuple(n[0] for n in nodes),
        value=tuple(n[2] for n in nodes),
        duration=tuple(n[1].duration_minutes for n in nodes),
        travel=tuple(tuple(work.mins(a, b) for b in coords) for a in coords),
        days=1,
        day_minutes=limit,
        travel_weight=profile.travel_weight,
    )
    route = sequencer.solve(problem)[0]
    seq = tuple(nodes[i][1] for i in route)
    spec = _Spec(k, town.city_id, town.name, arrival_cell, seq, {})
    fitted = work.fit(spec, keep=frozenset({x.key}))
    if fitted is None:
        return Issue(
            "DRIVE_LEAVES_NO_TIME",
            {
                "day": k,
                "drive_minutes": drive,
                "base": town.name,
                "name": x.name,
                "minutes": x.duration_minutes,
            },
        )
    spec, laid, _ = fitted
    work.days[k] = laid
    specs: dict[int, _Spec] = {k: spec}
    dropped_value = 0
    dropped = 0
    # The next day starts with a drive from the new base (or no longer from the old one).
    nxt = work.days.get(k + 1)
    if nxt is not None:
        nspec = work.spec_of(nxt)
        fitted_next = work.fit(nspec)
        if fitted_next is None:
            fixed = [e for e in nspec.seq if e.mandatory]
            return Issue(
                "DAY_FULL_OF_FIXED_ITEMS",
                {
                    "day": k + 1,
                    "name": x.name,
                    "minutes": x.duration_minutes,
                    "items": _names(fixed),
                },
            )
        nspec, nlaid, nlost = fitted_next
        specs[k + 1] = nspec
        work.days[k + 1] = nlaid
        dropped += len(nlost)
        dropped_value += sum(work.value(e) + work.rconfig.drop_extra_cost for e in nlost)
    lost = list(old_day.visits)
    moved, lost_dropped = work.rehome(lost, rest, specs)
    kept = {e.key for d in work.days.values() for e in d.items}
    dropped += lost_dropped
    dropped_value += sum(
        work.value(e) + work.rconfig.drop_extra_cost for e in lost if e.key not in kept
    )
    cost = work.option_cost(specs, moved, dropped_value)
    return _Option(cost, (k,), dict(specs), {d: work.days[d] for d in specs}, moved, dropped)


# -- removing a place ----------------------------------------------------------------------------


def remove_place(
    inp: RecalcInput,
    key: str,
    source: TravelSource,
    *,
    config: PlannerConfig = DEFAULT_CONFIG,
    rconfig: RecalcConfig = DEFAULT_RECALC,
    use_provider: bool = False,
) -> Revision:
    found = inp.plan.find(key)
    if found is None:
        raise ValueError(f"{key} is not in the plan")
    day, entry = found
    if entry.kind != "visit":
        raise PlanningImpossible([Issue("NOT_A_VISIT", {"name": entry.name})])
    if entry.locked:
        raise PlanningImpossible([Issue("ITEM_LOCKED", {"name": entry.name})])
    work = _Work(inp, source, config, rconfig)
    spec = work.spec_of(day)
    spec = replace(spec, seq=tuple(e for e in spec.seq if e.key != key))
    fitted = work.fit(spec)
    if fitted is None:  # taking a visit out cannot make the fixed items collide
        raise PlanningImpossible(
            [Issue("ROUTED_TIMES_TOO_LONG", {"day": day.day_index, "name": entry.name})]
        )
    spec, laid, _ = fitted
    work.days[day.day_index] = laid
    option = _Option(0, (day.day_index,), {day.day_index: spec}, {day.day_index: laid}, 0, 0)
    _finish(work, option.specs, use_provider, None)
    notes = [Note("PLACE_REMOVED", {"name": entry.name, "day": day.day_index})]
    return _revision(work, option, notes)


# -- routing, notes, statistics --------------------------------------------------------------------


def _day_cells(day: RDay, arrival_cell: Cell | None) -> list[Cell]:
    cells = [(a.coord, b.coord) for a, b in zip(day.items, day.items[1:], strict=False)]
    if arrival_cell is not None:
        cells.append(arrival_cell)
    return cells


def _finish(
    work: _Work, specs: dict[int, _Spec] | Mapping[int, _Spec], use_provider: bool, x: Entry | None
) -> None:
    """Ask the provider for the changed days' legs, then lay them out again with those times.
    A day that no longer fits loses its lowest-value engine visits; a mandatory item never."""
    specs = dict(specs)
    if use_provider:
        for _ in range(1 + FOLLOW_UP_FETCHES):
            missing = sorted(
                {
                    cell
                    for k, spec in specs.items()
                    for cell in _day_cells(work.days[k], spec.arrival_cell)
                    if not work.lookup.answered(*cell)
                }
            )
            if not missing:
                break
            work.lookup.fetch(missing, use_provider=True)
            for k in sorted(specs):
                laid = work.lay_out(specs[k])
                if laid is not None:
                    work.days[k] = laid
    for k in sorted(specs):
        fitted = work.fit(specs[k])
        if fitted is None:
            name = x.name if x is not None else "its items"
            raise PlanningImpossible([Issue("ROUTED_TIMES_TOO_LONG", {"day": k, "name": name})])
        specs[k], work.days[k], _ = fitted


def _revision(work: _Work, option: _Option, notes: list[Note]) -> Revision:
    config = work.config
    days = tuple(work.days[k] for k in sorted(work.days))
    plan = RPlan(work.inp.plan.profile, days)
    old_keys = {e.key for d in work.inp.plan.days for e in d.visits}
    new_by_day = {e.key: d.day_index for d in days for e in d.visits}
    old_by_day = {e.key: d.day_index for d in work.inp.plan.days for e in d.visits}
    moved = sum(1 for k, d in new_by_day.items() if k in old_by_day and old_by_day[k] != d)
    dropped = sum(1 for k in old_keys if k not in new_by_day)
    removed_key = next((n.params.get("name") for n in notes if n.code == "PLACE_REMOVED"), None)
    if removed_key is not None:
        dropped -= 1  # the visit the user removed is not "left out to make room"
    if moved:
        notes.append(Note("VISITS_MOVED", {"count": moved}))
    if dropped > 0:
        notes.append(Note("VISITS_DROPPED", {"count": dropped}))
    stats = revision_stats(days, config)
    base_ids = [d.base_city_id for d in days]
    distinct_bases = list(dict.fromkeys(base_ids))
    if len(distinct_bases) > 1:
        for bid in distinct_bases:
            base = work.bases.get(bid) if bid is not None else None
            if base is None:
                continue
            sights = sum(
                1
                for c in work.inp.candidates
                if distance_m(base.coord, c.coord) <= config.base_sight_radius_m
            )
            notes.append(
                Note(
                    "BASE_CITY_DAYS",
                    {
                        "name": base.name,
                        "days": base_ids.count(bid),
                        "sights": sights,
                        "radius_km": _km(config.base_sight_radius_m),
                    },
                )
            )
        prev: RDay | None = None
        for d in days:
            if d.arrival is not None and prev is not None:
                notes.append(
                    Note(
                        "INTER_CITY_TRAVEL",
                        {
                            "day": d.day_index,
                            "minutes": d.arrival.minutes,
                            "from_name": prev.base_city_name or "",
                            "to_name": d.base_city_name or "",
                            "label": d.arrival.confidence,
                        },
                    )
                )
            prev = d
    if stats.estimated_transfers:
        notes.append(
            Note(
                "ESTIMATED_TRANSFERS",
                {
                    "estimated": stats.estimated_transfers,
                    "transfers": stats.routed_transfers + stats.estimated_transfers,
                },
            )
        )
    kept = [n for n in work.inp.notes if n.code not in REPLACED_NOTES]
    changed = tuple(sorted(k for k in work.days if work.days[k] != work.old.get(k)))
    return Revision(
        plan=plan,
        changed_days=changed,
        notes=tuple(notes) + tuple(kept),
        stats=stats,
        bases=dict(work.bases),
        known_times=work.lookup.known(),
    )


def revision_stats(days: Iterable[RDay], config: PlannerConfig) -> PlanStats:
    """The engine's statistics (types.PlanStats) for a plan that may hold items the user added."""
    visit_min = meal_min = travel_min = travel_sec = routed = est = 0
    visits = meals = with_visits = intercity = count = 0
    for d in days:
        count += 1
        if d.visits:
            with_visits += 1
        legs = [e.transfer for e in d.items if e.transfer is not None]
        if d.arrival is not None:
            intercity += 1
            legs.append(d.arrival)
        for e in d.items:
            if e.kind == "visit":
                visits += 1
                visit_min += e.duration_minutes
            else:
                meals += 1
                meal_min += e.duration_minutes
        for leg in legs:
            travel_min += leg.minutes
            travel_sec += leg.seconds
            if leg.confidence == "routed":
                routed += 1
            else:
                est += 1
    planned = visit_min + meal_min + travel_min
    window = count * (config.day_window_end_minute - config.day_start_minute)
    return PlanStats(
        visits=visits,
        days_with_visits=with_visits,
        visit_minutes=visit_min,
        travel_minutes=travel_min,
        travel_seconds=travel_sec,
        routed_transfers=routed,
        estimated_transfers=est,
        day_utilisation_permille=planned * 1000 // window if window else 0,
        travel_share_permille=travel_min * 1000 // planned if planned else 0,
        meals=meals,
        meal_minutes=meal_min,
        intercity_legs=intercity,
    )
