"""The independent validator for recalculated plans (Phase 7, ADR 018).

Like ``validator.py`` it re-reads the result against the inputs without the recalculation's
scheduling code. A violation is a bug: the proposal is never shown (``PlanInvalid``).

Checked:

* the same days, in order, with the same dates; a day the recalculation did not change is
  identical to before;
* **locked items and restaurant or café stops never move** (ADR 026): each is on the same day, at
  the same start and end, with the same place and length; no restaurant or café stop is created;
* every item the user added is still in the plan (mandatory); the added place is in it once, with
  the reason ``ADDED_BY_YOU``; a removed place is gone;
* an item carried over keeps its place, name, point, length, origin and lock; a new visit is a
  sight the recalculation was given, with its category's default length;
* **the midday gap**: idle time before a sight that is not fixed is nothing or the gap (as in
  ``validator.py``), at most one a day;
* every item that is not fixed lies inside the day (after the day's inter-city drive) and ends by
  the profile's day end; items do not overlap, the gap holds the transfer, and every transfer and
  drive is exactly what the travel source returned (mode, minutes rounded up, seconds, metres,
  label);
* every day's base is a known base city, and a drive starts a day exactly when the base changes;
* reasons and notes have templates; the statistics match.
"""

from collections.abc import Mapping

from detour_api.planner.config import PlannerConfig
from detour_api.planner.durations import visit_minutes
from detour_api.planner.reasons import ITEM_TEMPLATES, NOTE_TEMPLATES, note_text
from detour_api.planner.recalc import Entry, Revision, RPlan
from detour_api.planner.types import BaseCity, Candidate, Leg
from detour_api.planner.validator import Violation
from detour_api.travel.types import Coord, TravelTime, distance_m

_CARRIED = (
    "kind",
    "name",
    "lat",
    "lon",
    "duration_minutes",
    "duration_source",
    "origin",
    "locked",
    "place_id",
    "user_place_id",
)


def _leg(
    leg: Leg,
    a: Coord,
    b: Coord,
    known: Mapping[tuple[Coord, Coord], TravelTime],
    config: PlannerConfig,
    day: int,
    pos: int | None,
    prefix: str,
) -> list[Violation]:
    out: list[Violation] = []
    mode = "walk" if distance_m(a, b) <= config.walk_max_m else "drive"
    if leg.mode != mode:
        out.append(Violation(f"{prefix}_MODE", day, pos))
    if leg.minutes != (leg.seconds + 59) // 60 or leg.seconds < 0 or leg.meters < 0:
        out.append(Violation(f"{prefix}_MINUTES", day, pos))
    given = known.get((a, b))
    if given is None or (given.seconds, given.meters, given.confidence) != (
        leg.seconds,
        leg.meters,
        leg.confidence,
    ):
        out.append(Violation(f"{prefix}_NOT_FROM_SOURCE", day, pos))
    return out


def validate_revision(
    old: RPlan,
    revision: Revision,
    *,
    added: str | None,
    removed: str | None,
    candidates: Mapping[str, Candidate],
    config: PlannerConfig,
) -> list[Violation]:
    new = revision.plan
    known = revision.known_times
    bases: Mapping[int, BaseCity] = revision.bases
    out: list[Violation] = []
    profile = config.profile(new.profile)  # type: ignore[arg-type]
    day_end = min(profile.day_end_minute, config.day_window_end_minute)
    if len(new.days) != len(old.days):
        return [Violation("DAY_COUNT")]

    old_entries: dict[tuple[int, str], Entry] = {}
    old_by_key: dict[str, Entry] = {}
    for d in old.days:
        for e in d.items:
            old_entries[(d.day_index, e.key)] = e
            old_by_key.setdefault(e.key, e)
    new_keys = [e.key for d in new.days for e in d.items if e.kind == "visit"]
    if len(new_keys) != len(set(new_keys)):
        out.append(Violation("DUPLICATE_VISIT"))
    present = set(new_keys) | {e.key for d in new.days for e in d.items}

    # Locked items never move; items the user added are never left out.
    for d in old.days:
        for e in d.items:
            if e.key == removed:
                continue
            if e.fixed:
                same = [
                    n
                    for nd in new.days
                    if nd.day_index == d.day_index
                    for n in nd.items
                    if n.key == e.key
                ]
                if (
                    not same
                    or (same[0].start_minute, same[0].end_minute)
                    != (
                        e.start_minute,
                        e.end_minute,
                    )
                    or same[0].duration_minutes != e.duration_minutes
                ):
                    out.append(Violation("LOCKED_ITEM_MOVED", d.day_index, detail=e.key))
            elif e.origin == "user" and e.key not in present:
                out.append(Violation("MANDATORY_ITEM_MISSING", d.day_index, detail=e.key))
    if added is not None:
        hits = [e for d in new.days for e in d.items if e.key == added]
        if len(hits) != 1 or "ADDED_BY_YOU" not in hits[0].reasons or hits[0].origin != "user":
            out.append(Violation("ADDITION_MISSING", detail=added))
    if removed is not None and removed in present:
        out.append(Violation("REMOVED_STILL_PRESENT", detail=removed))

    old_days = {d.day_index: d for d in old.days}
    previous_base: int | None = None
    gap = config.midday_gap
    for expected, day in enumerate(new.days, start=1):
        k = day.day_index
        before = old_days.get(k)
        if k != expected or before is None or day.date != before.date:
            out.append(Violation("DAY_ORDER", k))
            continue
        if day.base_city_id is None or day.base_city_id not in bases:
            out.append(Violation("UNKNOWN_BASE", k, detail=str(day.base_city_id)))
        moved_base = expected > 1 and day.base_city_id != previous_base
        if moved_base != (day.arrival is not None or day.arrival_unknown):
            out.append(Violation("ARRIVAL_MISMATCH", k))
        if day.arrival_unknown and day.arrival is not None:
            out.append(Violation("ARRIVAL_BOTH_KNOWN_AND_UNKNOWN", k))
        if k not in revision.changed_days:
            if day != before:
                out.append(Violation("UNCHANGED_DAY_DIFFERS", k))
            previous_base = day.base_city_id
            continue

        day_start = config.day_start_minute
        if day.arrival is not None:
            if previous_base in bases and day.base_city_id in bases:
                a = bases[previous_base].coord  # type: ignore[index]
                b = bases[day.base_city_id].coord  # type: ignore[index]
                out.extend(_leg(day.arrival, a, b, known, config, k, None, "ARRIVAL"))
            day_start += day.arrival.minutes
        previous_base = day.base_city_id

        idle_stretches = 0
        for pos, e in enumerate(day.items, start=1):
            if e.end_minute - e.start_minute != e.duration_minutes:
                out.append(Violation("END_NOT_START_PLUS_DURATION", k, pos))
            if not e.reasons or any(r not in ITEM_TEMPLATES for r in e.reasons):
                out.append(Violation("BAD_REASONS", k, pos))
            carried = old_by_key.get(e.key)
            if carried is not None and (e.kind == "visit" or e.fixed):
                if any(getattr(carried, f) != getattr(e, f) for f in _CARRIED):
                    out.append(Violation("CARRIED_ITEM_CHANGED", k, pos, e.key))
            elif e.kind == "visit" and e.key != added:
                c = candidates.get(e.place_id or "")
                if c is None or e.origin != "engine":
                    out.append(Violation("UNKNOWN_PLACE", k, pos, e.key))
                elif (e.name, e.lat, e.lon, e.category) != (c.name, c.lat, c.lon, c.category) or (
                    e.duration_minutes != visit_minutes(c.category)
                ):
                    out.append(Violation("SNAPSHOT_MISMATCH", k, pos, e.key))
            if e.kind == "meal" and carried is None:
                out.append(Violation("MEAL_CREATED", k, pos, e.key))
            if not e.fixed:
                if e.start_minute < day_start:
                    out.append(Violation("BEFORE_DAY_START", k, pos))
                if e.end_minute > day_end:
                    out.append(Violation("AFTER_DAY_END", k, pos))
            if pos == len(day.items):
                if e.transfer is not None:
                    out.append(Violation("TRANSFER_AFTER_LAST_ITEM", k, pos))
                continue
            nxt = day.items[pos]
            if e.transfer is None:
                out.append(Violation("MISSING_TRANSFER", k, pos))
                continue
            out.extend(_leg(e.transfer, e.coord, nxt.coord, known, config, k, pos, "TRANSFER"))
            needs = e.end_minute + e.transfer.minutes
            if nxt.start_minute < needs:
                out.append(Violation("OVERLAP", k, pos))
            elif nxt.start_minute > needs and not nxt.fixed:
                idle = nxt.start_minute - needs
                idle_stretches += 1
                if idle < gap.minutes or nxt.start_minute < gap.earliest_start + gap.minutes:
                    out.append(Violation("IDLE_NOT_THE_GAP", k, pos, f"{idle} minutes"))
        if idle_stretches > 1:
            out.append(Violation("MORE_THAN_ONE_GAP", k, detail=str(idle_stretches)))

    for note in revision.notes:
        if note.code not in NOTE_TEMPLATES:
            out.append(Violation("BAD_NOTE", detail=note.code))
            continue
        try:
            note_text(note.code, note.params)
        except (KeyError, IndexError, ValueError):
            out.append(Violation("BAD_NOTE", detail=note.code))

    s = revision.stats
    visits = sum(len(d.visits) for d in new.days)
    meals = sum(1 for d in new.days for e in d.items if e.kind == "meal")
    travel = sum(
        sum(e.transfer.minutes for e in d.items if e.transfer is not None)
        + (d.arrival.minutes if d.arrival is not None else 0)
        for d in new.days
    )
    if (s.visits, s.meals, s.travel_minutes) != (visits, meals, travel):
        out.append(Violation("STATS_MISMATCH"))
    return out
