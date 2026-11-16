"""The independent check of an Optimize proposal (ADR 029, rule 16).

It does not use the search's own helpers: it reads the stops as they were and the days as they would
become, and returns one text per rule broken. A proposal with any is never offered.
"""

from collections.abc import Sequence
from itertools import pairwise

from detour_api.planner.optimize import (
    RESTAURANT_LATEST_START,
    RESTAURANT_SHIFT_MIN,
    Outcome,
    Rules,
    Stop,
)


def validate(
    stops: Sequence[Stop], days: Sequence[int], outcome: Outcome, rules: Rules | None = None
) -> list[str]:
    rules = rules or Rules()
    problems: list[str] = []
    by_id = {s.id: s for s in stops}
    placed = [(d, p) for d in days for p in outcome.days.get(d, ())]

    ids = [p.id for _, p in placed]
    if sorted(ids) != sorted(by_id):
        problems.append("a stop was lost, added or duplicated")
        return problems

    for day, p in placed:
        s = by_id[p.id]
        if p.day != day:
            problems.append(f"{s.name}: stored on day {p.day} but listed on day {day}")
        if s.fixed and (day != s.day or p.start != s.start or p.end != s.end):
            problems.append(f"{s.name}: a stop that stays in place moved")
        if s.kind == "meal":
            if day != s.day:
                problems.append(f"{s.name}: a restaurant or café changed day")
            if s.start is not None and not (
                s.start - RESTAURANT_SHIFT_MIN <= p.start <= s.start + RESTAURANT_SHIFT_MIN
            ):
                problems.append(f"{s.name}: more than 60 minutes from the chosen time")
            if p.start > RESTAURANT_LATEST_START:
                problems.append(f"{s.name}: starts after 21:00")
        if s.kind == "transport" and (day != s.day or p.start != s.start):
            problems.append(f"{s.name}: a transport leg moved")
        if s.kind == "visit" and day not in s.allowed_days:
            problems.append(f"{s.name}: moved to a day it may not be on")
        if p.end - p.start != (
            s.duration
            if s.kind not in ("free_time", "transport")
            else (s.end or 0) - (s.start or 0)
        ):
            problems.append(f"{s.name}: its length changed")

    for day in days:
        items = outcome.days.get(day, ())
        # No stop crosses a transport leg the user entered (ADR 032).
        before = [s.id for s in stops if s.day == day]
        after = [p.id for p in items]
        common = set(before) & set(after)
        was = {k: v for k, v in _legs_before(by_id, before).items() if k in common}
        now = {k: v for k, v in _legs_before(by_id, after).items() if k in common}
        if was != now:
            problems.append(f"day {day}: a stop crossed a transport leg")
        if day not in outcome.changed_days:
            continue  # a day that is not changed keeps the user's own times
        for a, b in pairwise(items):
            leg = a.leg.minutes if a.leg is not None else 0
            if b.start < a.end + leg:
                problems.append(
                    f"day {day}: {by_id[b.id].name} starts before the travel to it ends"
                )
        if items:
            limit = _limit(stops, day, rules)
            if items[-1].end > limit:
                problems.append(f"day {day}: ends later than the day may")

    if outcome.travel_after > outcome.travel_before:
        problems.append("the proposal travels more than the plan")
    legs = sum(p.leg.minutes for _, p in placed if p.leg is not None) + sum(
        p.head.minutes for _, p in placed if p.head is not None
    )
    if legs != outcome.travel_after:
        problems.append("the proposal's travel total does not match its legs")
    return problems


def _legs_before(by_id: dict[str, Stop], ids: Sequence[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    legs = 0
    for i in ids:
        if by_id[i].kind == "transport":
            legs += 1
        out[i] = legs
    return out


def _limit(stops: Sequence[Stop], day: int, rules: Rules) -> int:
    ends = [rules.window_end]
    for s in stops:
        if s.day != day:
            continue
        if s.end is not None:
            ends.append(s.end)
        if s.kind == "meal" and s.start is not None:
            ends.append(min(s.start + RESTAURANT_SHIFT_MIN, RESTAURANT_LATEST_START) + s.duration)
    return max(ends)
