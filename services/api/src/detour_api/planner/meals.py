"""Meals: choosing a place to eat for a meal, and laying out a day with its visits and meals
(architecture section 5.2, step 5; ADR 016).

**Meal windows** are fixed by meal type (``PlannerConfig.meal_windows``) and a meal's length by
meal type and venue type (``meal_minutes_by_venue``). Opening hours are not known (ADR 003), so a
window is a planning choice, not a fact about a place.

**Choosing a place to eat** uses the imported data only (``geo.restaurant_profile``): the place
must list the meal type (derived from its venue type by the import's fixed rule), and is looked for
within growing straight-line rings around the visits before and after the meal
(``meal_search_m``). Places not yet used in the plan come first: only if none lies within the last
ring may a place used on an earlier day be chosen again (reason ``PLACE_REPEATED``); a place is
never used twice on one day. Within the first ring that has any, the place with the smallest cost
wins, ties by place id:

    cost = detour in metres (prev -> place -> next, minus prev -> next)
         + cuisine_repeat_penalty_m   if one of its cuisines is already in the plan
         + unknown_cuisine_penalty_m  if the data states no cuisine

There are no prices, ratings or opening hours. No suitable place within the last ring means the
meal is not planned; the engine says so in a note. A place is never invented.

**Laying out a day** walks the day's visits in order from the day's start and puts each pending
meal in front of the next visit when either the meal's window has opened by the time the next visit
would start, or doing that visit first would leave no time to reach the meal before its window
closes. A meal starts at its window's start at the earliest (waiting is free time). If a meal can no
longer end inside its window, or the day runs past its end, the layout fails and the engine drops
the day's lowest-value visit and lays it out again.
"""

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from detour_api.planner.config import MealType, PlannerConfig, Profile
from detour_api.planner.durations import visit_minutes
from detour_api.planner.travel import Cell, TravelLookup, minutes
from detour_api.planner.types import Candidate, Restaurant
from detour_api.travel.types import Coord, TravelTime, distance_m

_CELL_DEGREES = 0.01
_M_PER_DEGREE = 111_320.0


def _cell(coord: Coord) -> tuple[int, int]:
    return (math.floor(coord.lat / _CELL_DEGREES), math.floor(coord.lon / _CELL_DEGREES))


class RestaurantIndex:
    """The places to eat of a generation, in a grid of 0.01-degree cells for nearby lookups."""

    def __init__(self, restaurants: Iterable[Restaurant]) -> None:
        self.by_id: dict[str, Restaurant] = {}
        self._grid: dict[tuple[int, int], list[Restaurant]] = defaultdict(list)
        for r in sorted(restaurants, key=lambda r: r.place_id):
            if r.place_id in self.by_id:
                raise ValueError(f"duplicate restaurant id {r.place_id}")
            self.by_id[r.place_id] = r
            self._grid[_cell(r.coord)].append(r)

    def __len__(self) -> int:
        return len(self.by_id)

    def near(self, point: Coord, radius_m: int) -> list[Restaurant]:
        """Places within ``radius_m`` (straight line) of the point, in place-id order."""
        clat, clon = _cell(point)
        dlat = math.ceil(radius_m / (_M_PER_DEGREE * _CELL_DEGREES))
        cos = max(math.cos(math.radians(point.lat)), 0.01)
        dlon = math.ceil(radius_m / (_M_PER_DEGREE * cos * _CELL_DEGREES))
        out: list[Restaurant] = []
        for i in range(clat - dlat, clat + dlat + 1):
            for j in range(clon - dlon, clon + dlon + 1):
                for r in self._grid.get((i, j), ()):
                    if distance_m(point, r.coord) <= radius_m:
                        out.append(r)
        out.sort(key=lambda r: r.place_id)
        return out


@dataclass(frozen=True)
class Choice:
    restaurant: Restaurant
    detour_m: int
    ring: int  # index into meal_search_m: 0 is the nearest ring
    repeated: bool = False  # used on an earlier day of the plan


def detour_m(prev: Coord | None, place: Coord, nxt: Coord | None) -> int:
    if prev is not None and nxt is not None:
        extra = distance_m(prev, place) + distance_m(place, nxt) - distance_m(prev, nxt)
        return max(0, round(extra))
    anchor = prev if prev is not None else nxt
    assert anchor is not None  # noqa: S101 - callers pass at least one anchor
    return round(distance_m(anchor, place))


def choose(
    index: RestaurantIndex,
    meal_type: str,
    prev: Coord | None,
    nxt: Coord | None,
    used: frozenset[str] | set[str],
    seen_cuisines: frozenset[str] | set[str],
    config: PlannerConfig,
    today: frozenset[str] | set[str] = frozenset(),
) -> Choice | None:
    """The place to eat for a meal between two points (either may be missing, not both).
    ``used``: places of earlier days of the plan; ``today``: places of this day (never again)."""
    anchors = [c for c in (prev, nxt) if c is not None]
    if not anchors:
        return None
    for allow_repeat in (False, True):
        for ring, radius in enumerate(config.meal_search_m):
            found: dict[str, Restaurant] = {}
            for anchor in anchors:
                for r in index.near(anchor, radius):
                    found[r.place_id] = r
            best: tuple[int, str, Choice] | None = None
            for pid in sorted(found):
                r = found[pid]
                if pid in today or meal_type not in r.meal_types:
                    continue
                if pid in used and not allow_repeat:
                    continue
                extra = detour_m(prev, r.coord, nxt)
                cost = extra
                if r.cuisines is None:
                    cost += config.unknown_cuisine_penalty_m
                elif seen_cuisines.intersection(r.cuisines):
                    cost += config.cuisine_repeat_penalty_m
                if best is None or (cost, pid) < best[:2]:
                    best = (cost, pid, Choice(r, extra, ring, pid in used))
            if best is not None:
                return best[2]
    return None


@dataclass(frozen=True)
class Slot:
    kind: Literal["visit", "meal"]
    place_id: str
    coord: Coord
    start: int
    end: int
    meal_type: MealType | None = None
    choice: Choice | None = None
    # Meals: the cuisines the plan had before this meal (for the NEW_CUISINE reason).
    seen_before: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class DayLayout:
    """A day laid out: its visits and meals in time order, and the transfer between each pair of
    consecutive slots (``legs[i]`` joins ``slots[i]`` and ``slots[i + 1]``)."""

    slots: tuple[Slot, ...]
    legs: tuple[TravelTime, ...]
    cells: tuple[Cell, ...]
    meals_without_place: int
    meals_during_travel: int
    used: frozenset[str]
    seen: frozenset[str]


def lay_out_day(
    route: Sequence[str],
    visits: Mapping[str, Candidate],
    index: RestaurantIndex,
    lookup: TravelLookup,
    config: PlannerConfig,
    profile: Profile,
    start: int,
    used: frozenset[str],
    seen: frozenset[str],
) -> DayLayout | None:
    """The day with its meals, or None when it does not fit (a meal outside its window, or the
    day past its end). ``start`` is the day's start, later than 09:00 on a day that begins with a
    drive to a new base city."""
    if not route:
        return DayLayout((), (), (), 0, 0, used, seen)
    day_end = min(profile.day_end_minute, config.day_window_end_minute)

    pending: list[MealType] = []
    during_travel = 0
    for meal in profile.meals:
        window = config.meal_window(meal)
        latest_end = min(window.end_minute, day_end)
        if max(start, window.start_minute) + config.meal_minutes(meal, None) > latest_end:
            # Only a late start (the drive to a new base city) can do this.
            during_travel += 1
        else:
            pending.append(meal)

    today: set[str] = set()
    seen_now = set(seen)
    slots: list[Slot] = []
    legs: list[TravelTime] = []
    cells: list[Cell] = []
    without_place = 0
    clock = start
    prev: Coord | None = None

    def go(to: Coord) -> int:
        """Add the transfer from the previous slot; the arrival time."""
        if prev is None:
            return clock
        t = lookup.get(prev, to)
        legs.append(t)
        cells.append((prev, to))
        return clock + minutes(t.seconds)

    i = 0
    while i < len(route) or pending:
        if pending:
            meal = pending[0]
            window = config.meal_window(meal)
            latest_end = min(window.end_minute, day_end)
            nxt = visits[route[i]].coord if i < len(route) else None
            now = nxt is None
            if nxt is not None:
                arrive = clock if prev is None else clock + minutes(lookup.get(prev, nxt).seconds)
                if arrive >= window.start_minute:
                    now = True
                else:
                    end_next = arrive + visit_minutes(visits[route[i]].category)
                    after = visits[route[i + 1]].coord if i + 1 < len(route) else None
                    probe = choose(index, meal, nxt, after, used, seen_now, config, today)
                    if probe is None:
                        reach = config.meal_allowance_minutes
                        length = config.meal_minutes(meal, None)
                    else:
                        reach = minutes(lookup.get(nxt, probe.restaurant.coord).seconds)
                        length = config.meal_minutes(meal, probe.restaurant.venue_type)
                    if max(end_next + reach, window.start_minute) + length > latest_end:
                        now = True
            if now:
                pending.pop(0)
                choice = choose(index, meal, prev, nxt, used, seen_now, config, today)
                if choice is None:
                    without_place += 1
                    continue
                r = choice.restaurant
                meal_start = max(go(r.coord), window.start_minute)
                meal_end = meal_start + config.meal_minutes(meal, r.venue_type)
                if meal_end > latest_end:
                    return None
                slots.append(
                    Slot(
                        "meal",
                        r.place_id,
                        r.coord,
                        meal_start,
                        meal_end,
                        meal,
                        choice,
                        frozenset(seen_now),
                    )
                )
                today.add(r.place_id)
                seen_now.update(r.cuisines or ())
                clock, prev = meal_end, r.coord
                continue
        v = visits[route[i]]
        visit_start = go(v.coord)
        visit_end = visit_start + visit_minutes(v.category)
        slots.append(Slot("visit", v.place_id, v.coord, visit_start, visit_end))
        clock, prev = visit_end, v.coord
        i += 1
    if clock > day_end:
        return None
    return DayLayout(
        tuple(slots),
        tuple(legs),
        tuple(cells),
        without_place,
        during_travel,
        frozenset(used | today),
        frozenset(seen_now),
    )
