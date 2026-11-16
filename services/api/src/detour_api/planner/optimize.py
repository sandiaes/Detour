"""Optimize a hand-made trip (ADR 029): a new order of the stops for the least travel.

The user's plan is searched, not planned again: the search starts from the current order and
accepts only **strictly improving** moves, so the proposal's travel is never higher than the
plan's. No randomness and no clock: the same plan and the same travel times give the same answer.

**Objective.** Total travel minutes (walking and driving, each leg rounded up to whole minutes) over
the whole plan. A leg joins two consecutive stops that both have a point; a free-time block has no
point, so no leg is counted across it. A **transport leg** the user entered (ADR 032) has no point
either: its own length is the travel of that stretch, so no computed leg is counted across it.

**Empty days stay empty, and a day with stops keeps at least one:** a day boundary has no travel, so
without this the search would spread a day's stops over the empty days of the trip.

**Moves** (first improvement, in index order): reverse a run of movable visits within a day (2-opt),
relocate a visit within its day or to another day, swap two visits. A move that changes a day is
kept only if the day can be laid out again (below).

**Who moves.** A *visit* the user has not fixed. A restaurant or café never changes day and keeps
its chosen start time or starts later, at most 60 minutes later and never after 21:00 (the stops
before it are laid out around it). A **locked** stop, a stop the user keeps in place and a
free-time block keep their day, start and end. A **transport leg** keeps its day, start and length,
and **no stop crosses it**: the stops before it stay before it and those after stay after it, each
side reordered on its own; a day with a leg keeps its own stops in the second scope (none move in
or out), because the two sides of a leg are usually in different places. A day with a leg of
unknown length is left as it is, like a day with an item that has no time. A visit on a place
trip that lies far from the trip's point keeps its day. On a multi-city trip a visit stays in the
days of its own city. In the first scope (``within_days``) nothing changes day.

**Laying a day out.** The day starts at its current first item's start (09:00 when the first item
is a restaurant, a block or the day is empty, or earlier); visits follow one another with their
travel time between them and keep their own lengths. A day may not end later than the later of the
planner's day window end, the day's own current end and the end of a restaurant at its latest
allowed start.

**Travel times.** The search uses what the source answers without calling out (cached times and
labelled estimates). Then the legs of the changed days are asked of the provider (if allowed), and
the search runs again with those times, at most ``FOLLOW_UP_FETCHES`` times; legs that stay
estimated are labelled. Nothing is invented.
"""

import itertools
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Literal

from detour_api.planner.config import DEFAULT_CONFIG, PlannerConfig
from detour_api.planner.travel import Cell, TravelLookup, minutes
from detour_api.planner.types import Leg
from detour_api.travel.types import Coord, distance_m

OPTIMIZE_VERSION = "optimize-1.0.0"

# A restaurant or café starts at most this long after the time the user chose, and never later than
# 21:00 (owner decisions of 2026-11-14).
RESTAURANT_SHIFT_MIN = 60
RESTAURANT_LATEST_START = 21 * 60
# On a place trip a visit further than this from the trip's point keeps its day (ADR 029).
FAR_STOP_M = 25_000
# More stops than this are refused: the search is quadratic in them.
MAX_STOPS = 200
DAY_END = 24 * 60
MAX_ROUNDS = 500
FOLLOW_UP_FETCHES = 2

Scope = Literal["within_days", "across_days"]


@dataclass(frozen=True)
class Stop:
    """One item of the plan, as the search sees it."""

    id: str
    kind: Literal["visit", "meal", "free_time", "transport"]
    name: str
    lat: float | None
    lon: float | None
    day: int  # the day it is on now
    start: int | None  # minute of the day; None only for an item the user left without a time
    end: int | None
    duration: int
    fixed: bool  # locked, or kept in place by the user: day, start and end stay
    allowed_days: frozenset[int]  # the days a visit may be on; only its own day otherwise

    @property
    def located(self) -> bool:
        return self.lat is not None and self.lon is not None

    @property
    def coord(self) -> Coord:
        assert self.lat is not None and self.lon is not None  # noqa: S101 - callers check located
        return Coord.from_degrees(self.lat, self.lon)

    @property
    def movable(self) -> bool:
        return self.kind == "visit" and not self.fixed


@dataclass(frozen=True)
class Laid:
    """A stop in its place in the proposal, with the leg to the next stop of its day."""

    id: str
    day: int
    start: int
    end: int
    leg: Leg | None
    # From the day's stay to this stop, on the first stop of the day with a place (ADR 030).
    head: Leg | None = None


@dataclass(frozen=True)
class Outcome:
    days: dict[int, tuple[Laid, ...]]  # every day, in the proposal
    before: dict[int, tuple[Laid, ...]]  # every day as it is now, with the same travel source
    changed_days: tuple[int, ...]
    travel_before: int  # minutes
    travel_after: int
    meters_before: int
    meters_after: int
    estimated_before: int  # legs that are estimates
    estimated_after: int


@dataclass(frozen=True)
class Rules:
    """What the planner's configuration contributes to the search."""

    day_start: int = DEFAULT_CONFIG.day_start_minute
    window_end: int = DEFAULT_CONFIG.day_window_end_minute


def rules_of(config: PlannerConfig) -> Rules:
    return Rules(config.day_start_minute, config.day_window_end_minute)


# -- building the stops --------------------------------------------------------------------------


@dataclass(frozen=True)
class CityPoint:
    city_id: int
    lat: float
    lon: float


@dataclass(frozen=True)
class DayInfo:
    index: int
    base_city_id: int | None


def build_stops(
    items: Sequence[dict[str, object]],
    days: Sequence[DayInfo],
    *,
    scope: Scope,
    fixed_ids: Iterable[str],
    cities: Sequence[CityPoint] = (),
    place_point: tuple[float, float] | None = None,
) -> tuple[list[Stop], int]:
    """Stops from stored items (``plan_state`` rows), in plan order, and how many visits keep their
    day because they are far from a place trip's point. Items are ``plan_state`` item dicts with a
    ``day`` index added by the caller."""
    keep = set(fixed_ids)
    # A day with an item that has no time is left exactly as it is; so is a day with a transport
    # leg of unknown length (ADR 032): nothing says when the stops after it can start.
    frozen = {
        int(str(i["day"]))
        for i in items
        if i["start_minute"] is None or (i["type"] == "transport" and i["duration_minutes"] is None)
    }
    # A day with a transport leg keeps its own stops (ADR 032).
    leg_days = {int(str(i["day"])) for i in items if i["type"] == "transport"}
    stops: list[Stop] = []
    far = 0
    for r in items:
        day = int(str(r["day"]))
        lat = r["lat"]
        lon = r["lon"]
        kind = str(r["type"])
        start = r["start_minute"]
        end = r["end_minute"]
        assert kind in ("visit", "meal", "free_time", "transport")  # noqa: S101
        fixed = (
            bool(r["locked"])
            or str(r["id"]) in keep
            or kind in ("free_time", "transport")
            or day in frozen
        )
        if kind == "transport" and start is not None and end is None:
            # A night train arrives the next day: it takes the rest of its day.
            end = DAY_END
        allowed = frozenset({day})
        if (
            kind == "visit"
            and not fixed
            and scope == "across_days"
            and lat is not None
            and day not in leg_days
        ):
            point = Coord.from_degrees(float(str(lat)), float(str(lon)))
            allowed = _allowed_days(point, day, days, cities, place_point) - (
                (frozen | leg_days) - {day}
            )
            if (
                place_point is not None
                and not cities
                and distance_m(point, Coord.from_degrees(*place_point)) > FAR_STOP_M
            ):
                far += 1
        minutes_ = r["duration_minutes"]
        stops.append(
            Stop(
                id=str(r["id"]),
                kind=kind,  # type: ignore[arg-type]
                name=str(r["display_name"]),
                lat=None if lat is None else float(str(lat)),
                lon=None if lon is None else float(str(lon)),
                day=day,
                start=None if start is None else int(str(start)),
                end=None if end is None else int(str(end)),
                duration=int(str(minutes_)) if minutes_ is not None else 0,
                fixed=fixed,
                allowed_days=allowed,
            )
        )
    return stops, far


def _allowed_days(
    here: Coord,
    day: int,
    days: Sequence[DayInfo],
    cities: Sequence[CityPoint],
    place_point: tuple[float, float] | None,
) -> frozenset[int]:
    if cities:  # a multi-city trip: the days of the stop's own city, its nearest stop (ADR 024)
        own = min(
            cities, key=lambda c: (distance_m(here, Coord.from_degrees(c.lat, c.lon)), c.city_id)
        )
        return frozenset(d.index for d in days if d.base_city_id == own.city_id) | {day}
    if place_point is not None and distance_m(here, Coord.from_degrees(*place_point)) > FAR_STOP_M:
        return frozenset({day})  # a place trip: far from the point, it keeps its day (ADR 029)
    return frozenset(d.index for d in days)


# -- the search ---------------------------------------------------------------------------------


class _Search:
    def __init__(
        self,
        stops: Sequence[Stop],
        days: Sequence[int],
        scope: Scope,
        lookup: TravelLookup,
        rules: Rules,
        anchors: dict[int, Coord] | None = None,
    ) -> None:
        self.stops = stops
        self.anchors = anchors or {}
        self.days = tuple(days)
        self.scope = scope
        self.lookup = lookup
        self.rules = rules
        self.orders: dict[int, list[int]] = {d: [] for d in self.days}
        for i, s in enumerate(stops):
            self.orders[s.day].append(i)
        self.original = {d: tuple(v) for d, v in self.orders.items()}
        # Which side of the day's transport legs each stop is on (ADR 032): moves keep it.
        self.side = {i: s for v in self.original.values() for i, s in _sides(stops, v).items()}
        self._leg_memo: dict[tuple[int, int], int] = {}
        self._fit_memo: dict[tuple[int, tuple[int, ...]], bool] = {}
        # A day's own limit: the later of the window end, its current end and a restaurant's end at
        # its latest start.
        self.limit = {d: self._limit(d) for d in self.days}
        self.start = {d: self._day_start(d) for d in self.days}

    # -- numbers

    def _limit(self, day: int) -> int:
        ends = [self.rules.window_end]
        for i in self.original[day]:
            s = self.stops[i]
            if s.end is not None:
                ends.append(s.end)
            if s.kind == "meal" and s.start is not None:
                ends.append(
                    min(s.start + RESTAURANT_SHIFT_MIN, RESTAURANT_LATEST_START) + s.duration
                )
        return max(ends)

    def _day_start(self, day: int) -> int:
        order = self.original[day]
        if not order:
            return self.rules.day_start
        first = self.stops[order[0]]
        if first.start is None:
            return self.rules.day_start
        if first.kind == "visit" and not first.fixed:
            return first.start
        return min(first.start, self.rules.day_start)

    def leg(self, a: int, b: int) -> int:
        """Minutes from stop ``a`` to stop ``b``; 0 when either has no point."""
        key = (a, b)
        found = self._leg_memo.get(key)
        if found is None:
            sa, sb = self.stops[a], self.stops[b]
            if not (sa.located and sb.located):
                found = 0
            else:
                found = minutes(self.lookup.get(sa.coord, sb.coord).seconds)
            self._leg_memo[key] = found
        return found

    def head(self, day: int, i: int) -> int:
        """Minutes from the day's stay to stop ``i``; 0 without a stay or a point (ADR 030)."""
        anchor = self.anchors.get(day)
        s = self.stops[i]
        if anchor is None or not s.located:
            return 0
        return minutes(self.lookup.get(anchor, s.coord).seconds)

    def _head_fn(self, day: int) -> Callable[[int], int] | None:
        if day not in self.anchors:
            return None

        def head(i: int) -> int:
            return self.head(day, i)

        return head

    def first_located(self, order: Sequence[int]) -> int | None:
        return next((i for i in order if self.stops[i].located), None)

    def travel(self, order: Sequence[int], day: int) -> int:
        """The day's travel: between its stops, and from its stay to its first stop with a place.
        There is no leg back to the stay at the end of the day (owner, 2026-11-15)."""
        total = sum(self.leg(a, b) for a, b in itertools.pairwise(order))
        first = self.first_located(order)
        return total if first is None else total + self.head(day, first)

    def total(self) -> int:
        return sum(self.travel(o, d) for d, o in self.orders.items())

    def fits(self, day: int, order: Sequence[int]) -> bool:
        key = (day, tuple(order))
        found = self._fit_memo.get(key)
        if found is None:
            found = (
                lay_out(
                    self.stops,
                    order,
                    self.start[day],
                    self.limit[day],
                    self.leg,
                    self._head_fn(day),
                )
                is not None
            )
            self._fit_memo[key] = found
        return found

    def keeps_sides(self, order: Sequence[int]) -> bool:
        return _sides(self.stops, order) == {i: self.side[i] for i in order}

    # -- moves

    def run(self) -> None:
        for _ in range(MAX_ROUNDS):
            if not (self._two_opt() or self._relocate() or self._swap()):
                return

    def _commit(self, new: dict[int, list[int]]) -> None:
        self.orders.update(new)

    def _two_opt(self) -> bool:
        for d in self.days:
            order = self.orders[d]
            for i in range(len(order)):
                if not self.stops[order[i]].movable:
                    continue
                for j in range(i + 1, len(order)):
                    if not self.stops[order[j]].movable:
                        break
                    cand = order[:i] + order[i : j + 1][::-1] + order[j + 1 :]
                    if self.travel(cand, d) < self.travel(order, d) and self.fits(d, cand):
                        self._commit({d: cand})
                        return True
        return False

    def _relocate(self) -> bool:
        for d in self.days:
            order = self.orders[d]
            for pos, v in enumerate(order):
                s = self.stops[v]
                if not s.movable:
                    continue
                rest = order[:pos] + order[pos + 1 :]
                for dd in self.days:
                    if dd not in s.allowed_days:
                        continue
                    if dd != d and (
                        self.scope == "within_days"
                        or not self.original[dd]  # an empty day stays empty
                        or not rest  # a day with stops never becomes empty
                    ):
                        continue
                    target = rest if dd == d else self.orders[dd]
                    for p in range(len(target) + 1):
                        if dd == d and p == pos:
                            continue
                        cand = [*target[:p], v, *target[p:]]
                        if dd == d:
                            if not self.keeps_sides(cand):
                                continue
                            before = self.travel(order, d)
                            after = self.travel(cand, d)
                            if after < before and self.fits(d, cand):
                                self._commit({d: cand})
                                return True
                        else:
                            before = self.travel(order, d) + self.travel(self.orders[dd], dd)
                            after = self.travel(rest, d) + self.travel(cand, dd)
                            if after < before and self.fits(d, rest) and self.fits(dd, cand):
                                self._commit({d: rest, dd: cand})
                                return True
        return False

    def _swap(self) -> bool:
        flat = [(d, p, v) for d in self.days for p, v in enumerate(self.orders[d])]
        for (d1, p1, v1), (d2, p2, v2) in itertools.combinations(flat, 2):
            s1, s2 = self.stops[v1], self.stops[v2]
            if not (s1.movable and s2.movable):
                continue
            if d1 == d2:
                order = self.orders[d1]
                cand = list(order)
                cand[p1], cand[p2] = v2, v1
                if (
                    self.keeps_sides(cand)
                    and self.travel(cand, d1) < self.travel(order, d1)
                    and self.fits(d1, cand)
                ):
                    self._commit({d1: cand})
                    return True
                continue
            if self.scope == "within_days":
                continue
            if d2 not in s1.allowed_days or d1 not in s2.allowed_days:
                continue
            a, b = list(self.orders[d1]), list(self.orders[d2])
            a[p1], b[p2] = v2, v1
            before = self.travel(self.orders[d1], d1) + self.travel(self.orders[d2], d2)
            after = self.travel(a, d1) + self.travel(b, d2)
            if after < before and self.fits(d1, a) and self.fits(d2, b):
                self._commit({d1: a, d2: b})
                return True
        return False


def _sides(stops: Sequence[Stop], order: Sequence[int]) -> dict[int, int]:
    """For each stop of a day's order: how many transport legs come before it."""
    out: dict[int, int] = {}
    legs = 0
    for i in order:
        if stops[i].kind == "transport":
            legs += 1
        out[i] = legs
    return out


def lay_out(
    stops: Sequence[Stop],
    order: Sequence[int],
    day_start: int,
    limit: int,
    leg: Callable[[int, int], int],
    head: Callable[[int], int] | None = None,
) -> list[tuple[int, int]] | None:
    """Start and end of every stop of a day in the given order, or None if the day cannot be laid
    out: a block or a locked stop would start too early, a restaurant would start later than 60
    minutes after its chosen time or after 21:00, or the day ends after ``limit``. ``head`` gives
    the minutes from the day's stay to a stop: the first stop starts that long after the day."""
    out: list[tuple[int, int]] = []
    cursor = day_start
    prev: int | None = None
    for i in order:
        s = stops[i]
        if prev is not None:
            earliest = cursor + leg(prev, i)
        else:  # the first stop: the day starts at the stay (ADR 030)
            earliest = cursor + (head(i) if head is not None and s.located else 0)
        if s.fixed or s.kind in ("free_time", "transport"):
            assert s.start is not None and s.end is not None  # noqa: S101
            if s.start < earliest:
                return None
            start, end = s.start, s.end
        elif s.kind == "meal":
            assert s.start is not None  # noqa: S101
            start = max(s.start, earliest)
            if start > min(s.start + RESTAURANT_SHIFT_MIN, RESTAURANT_LATEST_START):
                return None
            end = start + s.duration
        else:
            start = earliest
            end = start + s.duration
        out.append((start, end))
        cursor = end
        prev = i
    if out and out[-1][1] > limit:
        return None
    return out


# -- the whole run -------------------------------------------------------------------------------


def _cells(
    stops: Sequence[Stop], orders: dict[int, Sequence[int]], anchors: dict[int, Coord]
) -> list[Cell]:
    cells = [
        (stops[a].coord, stops[b].coord)
        for order in orders.values()
        for a, b in itertools.pairwise(order)
        if stops[a].located and stops[b].located
    ]
    for day, order in orders.items():
        first = next((i for i in order if stops[i].located), None)
        if first is not None and day in anchors:
            cells.append((anchors[day], stops[first].coord))
    return cells


def _all_cells(stops: Sequence[Stop], scope: Scope, anchors: dict[int, Coord]) -> list[Cell]:
    located = [s for s in stops if s.located]
    cells = [
        (a.coord, b.coord)
        for a, b in itertools.permutations(located, 2)
        if scope == "across_days" or a.day == b.day
    ]
    for day, anchor in anchors.items():
        cells.extend((anchor, s.coord) for s in located if scope == "across_days" or s.day == day)
    return cells


@dataclass
class _Totals:
    minutes: int = 0
    meters: int = 0
    estimated: int = 0
    legs: dict[int, tuple[Laid, ...]] = field(default_factory=dict)


def optimize(
    stops: Sequence[Stop],
    days: Sequence[int],
    *,
    scope: Scope,
    lookup: TravelLookup,
    use_provider: bool,
    rules: Rules | None = None,
    anchors: dict[int, Coord] | None = None,
) -> Outcome:
    """Search for a shorter order. ``changed_days`` is empty when nothing improves. ``anchors`` is
    where each day starts (the traveller's stay, ADR 030): the leg from it to the day's first stop
    counts in the travel and the day starts that much later."""
    rules = rules or Rules()
    anchors = anchors or {}
    if steps_exceed(stops):
        raise ValueError("too many stops")
    lookup.fetch(_all_cells(stops, scope, anchors), use_provider=False)
    search = _Search(stops, days, scope, lookup, rules, anchors)
    for round_ in range(FOLLOW_UP_FETCHES + 1):
        search.run()
        changed = [d for d in search.days if tuple(search.orders[d]) != search.original[d]]
        if not changed or not use_provider or round_ == FOLLOW_UP_FETCHES:
            break
        # Both the proposed order and the current one of the changed days, so the saving compares
        # routed times with routed times.
        cells = _cells(stops, {d: search.orders[d] for d in changed}, anchors) + _cells(
            stops, {d: search.original[d] for d in changed}, anchors
        )
        missing = [c for c in sorted(set(cells)) if not lookup.answered(*c)]
        if not missing:
            break
        lookup.fetch(missing, use_provider=True)
        # The original order again, with the new times.
        search = _Search(stops, days, scope, lookup, rules, anchors)
    return _outcome(stops, search)


def _outcome(stops: Sequence[Stop], search: _Search) -> Outcome:
    changed = tuple(d for d in search.days if tuple(search.orders[d]) != search.original[d])
    before = _lay_all(stops, search, {d: list(v) for d, v in search.original.items()}, set())
    after = _lay_all(stops, search, search.orders, set(changed))
    return Outcome(
        days=after.legs,
        before=before.legs,
        changed_days=changed,
        travel_before=before.minutes,
        travel_after=after.minutes,
        meters_before=before.meters,
        meters_after=after.meters,
        estimated_before=before.estimated,
        estimated_after=after.estimated,
    )


def _lay_all(
    stops: Sequence[Stop], search: _Search, orders: dict[int, list[int]], relay: set[int]
) -> _Totals:
    """Every day with its legs. Days in ``relay`` get new times; the others keep the stored ones."""
    totals = _Totals()
    for d in search.days:
        order = orders[d]
        if d in relay:
            times = lay_out(
                stops,
                order,
                search.start[d],
                search.limit[d],
                search.leg,
                search._head_fn(d),
            )
            assert times is not None  # noqa: S101 - the search only keeps days that fit
        else:
            times = [(stops[i].start or 0, stops[i].end or 0) for i in order]
        laid: list[Laid] = []
        first = search.first_located(order)
        for n, i in enumerate(order):
            head: Leg | None = None
            if i == first and d in search.anchors:
                origin = search.anchors[d]
                t = search.lookup.get(origin, stops[i].coord)
                head = Leg(
                    mode=search.lookup.mode(origin, stops[i].coord),
                    seconds=t.seconds,
                    meters=t.meters,
                    minutes=minutes(t.seconds),
                    confidence=t.confidence,
                    estimate_reason=t.reason,
                )
                totals.minutes += head.minutes
                totals.meters += t.meters
                totals.estimated += 0 if t.confidence == "routed" else 1
            leg: Leg | None = None
            if n + 1 < len(order) and stops[i].located and stops[order[n + 1]].located:
                a, b = stops[i], stops[order[n + 1]]
                t = search.lookup.get(a.coord, b.coord)
                mins = minutes(t.seconds)
                leg = Leg(
                    mode=search.lookup.mode(a.coord, b.coord),
                    seconds=t.seconds,
                    meters=t.meters,
                    minutes=mins,
                    confidence=t.confidence,
                    estimate_reason=t.reason,
                )
                totals.minutes += mins
                totals.meters += t.meters
                totals.estimated += 0 if t.confidence == "routed" else 1
            laid.append(Laid(stops[i].id, d, times[n][0], times[n][1], leg, head))
        totals.legs[d] = tuple(laid)
    return totals


def steps_exceed(stops: Sequence[Stop]) -> bool:
    return len([s for s in stops if s.kind not in ("free_time", "transport")]) > MAX_STOPS


def long_walks(outcome: Outcome, walk_max_m: int) -> int:
    """Walks over ``walk_max_m`` in the proposal: without a car Optimize walks every leg, and the
    preview names these (owner decision of 2026-11-16, ADR 032)."""
    return sum(
        1
        for laid in outcome.days.values()
        for p in laid
        for leg in (p.leg, p.head)
        if leg is not None and leg.mode == "walk" and leg.meters > walk_max_m
    )


__all__ = [
    "FAR_STOP_M",
    "MAX_STOPS",
    "OPTIMIZE_VERSION",
    "CityPoint",
    "DayInfo",
    "Laid",
    "Outcome",
    "Rules",
    "Scope",
    "Stop",
    "build_stops",
    "lay_out",
    "long_walks",
    "optimize",
    "rules_of",
    "steps_exceed",
]
