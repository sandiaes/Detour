"""The difference between two versions of a plan, as the app previews it (Phase 7, ADR 018).

Visits are matched by their place (``place:<id>`` or ``user:<id>``; a place is visited once per
plan). Meals are matched by day, meal type and place: a meal that changes its place to eat is one
removed and one added meal. The same function compares a proposal with the current plan (the
preview) and two stored versions (the tests check that what is applied is what was previewed).
"""

from collections.abc import Iterable
from dataclasses import dataclass

from detour_api.planner.recalc import Entry, RDay, RPlan


@dataclass(frozen=True)
class DiffItem:
    day: int
    key: str
    kind: str
    name: str
    start_minute: int
    end_minute: int
    origin: str


@dataclass(frozen=True)
class DiffMove:
    key: str
    kind: str
    name: str
    from_day: int
    to_day: int
    old_start_minute: int
    new_start_minute: int


@dataclass(frozen=True)
class DiffRetime:
    key: str
    kind: str
    name: str
    day: int
    old_start_minute: int
    new_start_minute: int


@dataclass(frozen=True)
class DiffBase:
    day: int
    old_name: str | None
    new_name: str | None


@dataclass(frozen=True)
class DiffLeg:
    """An estimated travel time in a changed day of the new plan."""

    day: int
    from_name: str
    to_name: str
    mode: str
    minutes: int


@dataclass(frozen=True)
class PlanDiff:
    added: tuple[DiffItem, ...]
    removed: tuple[DiffItem, ...]
    moved: tuple[DiffMove, ...]
    retimed: tuple[DiffRetime, ...]
    base_changes: tuple[DiffBase, ...]
    days_changed: tuple[int, ...]
    travel_minutes_before: int
    travel_minutes_after: int
    estimated_legs: tuple[DiffLeg, ...]

    @property
    def travel_minutes_added(self) -> int:
        return self.travel_minutes_after - self.travel_minutes_before


def _item(day: int, e: Entry) -> DiffItem:
    return DiffItem(day, e.key, e.kind, e.name, e.start_minute, e.end_minute, e.origin)


def _travel(days: Iterable[RDay]) -> int:
    total = 0
    for d in days:
        total += sum(e.transfer.minutes for e in d.items if e.transfer is not None)
        total += d.arrival.minutes if d.arrival is not None else 0
    return total


def _visits(plan: RPlan) -> dict[str, tuple[int, Entry]]:
    return {e.key: (d.day_index, e) for d in plan.days for e in d.items if e.kind == "visit"}


def _meals(plan: RPlan) -> dict[tuple[int, str], Entry]:
    return {(d.day_index, e.key): e for d in plan.days for e in d.items if e.kind == "meal"}


def _same_day(a: RDay, b: RDay) -> bool:
    return (
        a.base_city_id == b.base_city_id
        and a.arrival == b.arrival
        and [(e.key, e.start_minute, e.end_minute, e.transfer) for e in a.items]
        == [(e.key, e.start_minute, e.end_minute, e.transfer) for e in b.items]
    )


def compare(old: RPlan, new: RPlan) -> PlanDiff:
    added: list[DiffItem] = []
    removed: list[DiffItem] = []
    moved: list[DiffMove] = []
    retimed: list[DiffRetime] = []

    ov, nv = _visits(old), _visits(new)
    for key in sorted(set(ov) | set(nv)):
        if key not in nv:
            removed.append(_item(*ov[key]))
        elif key not in ov:
            added.append(_item(*nv[key]))
        else:
            (od, oe), (nd, ne) = ov[key], nv[key]
            if od != nd:
                moved.append(
                    DiffMove(key, "visit", ne.name, od, nd, oe.start_minute, ne.start_minute)
                )
            elif oe.start_minute != ne.start_minute:
                retimed.append(
                    DiffRetime(key, "visit", ne.name, nd, oe.start_minute, ne.start_minute)
                )
    om, nm = _meals(old), _meals(new)
    for mk in sorted(set(om) | set(nm)):
        day = mk[0]
        if mk not in nm:
            removed.append(_item(day, om[mk]))
        elif mk not in om:
            added.append(_item(day, nm[mk]))
        elif om[mk].start_minute != nm[mk].start_minute:
            e = nm[mk]
            retimed.append(
                DiffRetime(e.key, "meal", e.name, day, om[mk].start_minute, e.start_minute)
            )

    old_days = {d.day_index: d for d in old.days}
    bases: list[DiffBase] = []
    changed: list[int] = []
    for d in new.days:
        o = old_days.get(d.day_index)
        if o is None or not _same_day(o, d):
            changed.append(d.day_index)
        if o is not None and o.base_city_id != d.base_city_id:
            bases.append(DiffBase(d.day_index, o.base_city_name, d.base_city_name))

    estimated: list[DiffLeg] = []
    prev_base: RDay | None = None
    for d in new.days:
        if d.day_index in changed:
            if d.arrival is not None and d.arrival.confidence != "routed":
                estimated.append(
                    DiffLeg(
                        d.day_index,
                        (prev_base.base_city_name if prev_base else None) or "",
                        d.base_city_name or "",
                        d.arrival.mode,
                        d.arrival.minutes,
                    )
                )
            for a, b in zip(d.items, d.items[1:], strict=False):
                if a.transfer is not None and a.transfer.confidence != "routed":
                    estimated.append(
                        DiffLeg(d.day_index, a.name, b.name, a.transfer.mode, a.transfer.minutes)
                    )
        prev_base = d

    order = lambda i: (i.day, i.start_minute, i.key)  # noqa: E731
    return PlanDiff(
        added=tuple(sorted(added, key=order)),
        removed=tuple(sorted(removed, key=order)),
        moved=tuple(sorted(moved, key=lambda m: (m.to_day, m.new_start_minute, m.key))),
        retimed=tuple(sorted(retimed, key=lambda r: (r.day, r.new_start_minute, r.key))),
        base_changes=tuple(bases),
        days_changed=tuple(changed),
        travel_minutes_before=_travel(old.days),
        travel_minutes_after=_travel(new.days),
        estimated_legs=tuple(estimated),
    )
