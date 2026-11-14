"""Laying out a day: its visits in order from the day's start, with one unplanned midday gap
(architecture section 5.2, step 5; ADR 026, which replaced the meals of ADR 016).

A generated day holds sights only. Between two stops the traveller walks or drives the transfer;
the **midday gap** (``PlannerConfig.midday_gap``) is idle time on top of that, not an item: the next
stop starts later than the transfer needs. ``gap_start`` is the one rule for where it goes; the
recalculation (``recalc.py``) uses the same function, so a changed day keeps the same shape.

The gap is placed before a stop when the traveller reaches that stop at or after the gap's earliest
start (and no later than its latest start), or when doing the stop first would push the gap's start
past its latest start. It is never placed before the first stop of a day (there is nothing to rest
from) or after the last (nothing follows), and a day whose route reaches the window after its latest
start has no gap: the day began too late for one.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from detour_api.planner.config import MiddayGap, PlannerConfig, Profile
from detour_api.planner.durations import visit_minutes
from detour_api.planner.travel import Cell, TravelLookup, minutes
from detour_api.planner.types import Candidate
from detour_api.travel.types import Coord, TravelTime


def gap_start(gap: MiddayGap, arrive: int, next_minutes: int) -> int | None:
    """When the midday gap starts if it goes before a stop the traveller reaches at ``arrive``
    (the stop takes ``next_minutes``); None to do the stop first."""
    if arrive > gap.latest_start:
        return None
    if arrive >= gap.earliest_start:
        return arrive
    if max(arrive + next_minutes, gap.earliest_start) > gap.latest_start:
        return gap.earliest_start
    return None


@dataclass(frozen=True)
class Slot:
    place_id: str
    coord: Coord
    start: int
    end: int


@dataclass(frozen=True)
class DayLayout:
    """A day laid out: its visits in time order, and the transfer between each pair of consecutive
    visits (``legs[i]`` joins ``slots[i]`` and ``slots[i + 1]``)."""

    slots: tuple[Slot, ...]
    legs: tuple[TravelTime, ...]
    cells: tuple[Cell, ...]


def lay_out_day(
    route: Sequence[str],
    visits: Mapping[str, Candidate],
    lookup: TravelLookup,
    config: PlannerConfig,
    profile: Profile,
    start: int,
) -> DayLayout | None:
    """The day, or None when it does not fit (a visit past the day's end). ``start`` is the day's
    start, later than 09:00 on a day that begins with a drive to a new base city."""
    if not route:
        return DayLayout((), (), ())
    day_end = min(profile.day_end_minute, config.day_window_end_minute)
    gap = config.midday_gap
    pending = True
    slots: list[Slot] = []
    legs: list[TravelTime] = []
    cells: list[Cell] = []
    clock = start
    prev: Coord | None = None
    for pid in route:
        v = visits[pid]
        length = visit_minutes(v.category)
        arrive = clock
        if prev is not None:
            t = lookup.get(prev, v.coord)
            legs.append(t)
            cells.append((prev, v.coord))
            arrive = clock + minutes(t.seconds)
            if pending:
                begun = gap_start(gap, arrive, length)
                if arrive > gap.latest_start:
                    pending = False
                elif begun is not None:
                    pending = False
                    arrive = begun + gap.minutes
        end = arrive + length
        if end > day_end:
            return None
        slots.append(Slot(pid, v.coord, arrive, end))
        clock, prev = end, v.coord
    return DayLayout(tuple(slots), tuple(legs), tuple(cells))
