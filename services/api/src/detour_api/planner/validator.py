"""The independent validator (architecture section 5.2, step 7).

It re-reads a finished plan against the engine's inputs and checks it **without the engine's
scheduling code**: times are re-added from the plan's own numbers, minutes are recomputed from
seconds, the mode rule and the duration table are applied again, and every transfer is compared
with the value the travel source returned for that pair. A violation is a bug in the engine: the
plan is never shown (``PlanInvalid``).

Checked:

* the trip's days, in order, with the right dates;
* every visit is a candidate the engine was given (no manufactured attraction), with that
  candidate's name, point and category, and at most once per plan;
* durations are the category defaults; ``end = start + duration``;
* every item lies inside the day window and the profile's day end;
* items do not overlap, and the gap between two visits holds the transfer;
* a transfer joins every pair of consecutive visits and only those; its mode follows the walking
  threshold, its minutes are its seconds rounded up, and its seconds, metres and label are exactly
  what the travel source returned (no invented travel time);
* every visit has at least one reason, and every reason and note has a fixed template;
* the statistics match the plan.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta

from detour_api.planner.config import PlannerConfig
from detour_api.planner.durations import visit_minutes
from detour_api.planner.reasons import ITEM_TEMPLATES, NOTE_TEMPLATES, note_text
from detour_api.planner.types import Candidate, Generation, Plan, PlanRequest
from detour_api.travel.types import Coord, TravelTime, distance_m


@dataclass(frozen=True)
class Violation:
    code: str
    day: int | None = None
    position: int | None = None
    detail: str = ""


def _check_note(code: str, params: Mapping[str, object]) -> str | None:
    if code not in NOTE_TEMPLATES:
        return f"unknown note {code}"
    try:
        note_text(code, params)
    except (KeyError, IndexError, ValueError) as exc:
        return f"note {code} does not render: {exc}"
    return None


def validate_plan(
    plan: Plan,
    request: PlanRequest,
    candidates: Mapping[str, Candidate],
    known_times: Mapping[tuple[Coord, Coord], TravelTime],
    config: PlannerConfig,
) -> list[Violation]:
    out: list[Violation] = []
    try:
        profile = config.profile(plan.profile)
    except KeyError:
        return [Violation("UNKNOWN_PROFILE", detail=plan.profile)]
    day_end = min(profile.day_end_minute, config.day_window_end_minute)

    if len(plan.days) != request.days:
        out.append(Violation("DAY_COUNT", detail=f"{len(plan.days)} != {request.days}"))
    seen: set[str] = set()
    visits = visit_min = travel_min = travel_sec = routed = estimated = with_visits = 0
    for expected_index, day in enumerate(plan.days, start=1):
        d = day.day_index
        if d != expected_index:
            out.append(Violation("DAY_ORDER", d, detail=f"expected {expected_index}"))
        expected_date = (
            None
            if request.start_date is None
            else request.start_date + timedelta(days=expected_index - 1)
        )
        if day.date != expected_date:
            out.append(Violation("DAY_DATE", d, detail=f"{day.date} != {expected_date}"))
        if day.visits:
            with_visits += 1
        for pos, v in enumerate(day.visits, start=1):
            visits += 1
            c = candidates.get(v.place_id)
            if c is None:
                out.append(Violation("UNKNOWN_PLACE", d, pos, v.place_id))
                continue
            if (v.name, v.lat, v.lon, v.category) != (c.name, c.lat, c.lon, c.category):
                out.append(Violation("SNAPSHOT_MISMATCH", d, pos, v.place_id))
            if v.place_id in seen:
                out.append(Violation("DUPLICATE_VISIT", d, pos, v.place_id))
            seen.add(v.place_id)

            if v.duration_minutes != visit_minutes(c.category):
                out.append(Violation("DURATION_NOT_DEFAULT", d, pos, str(v.duration_minutes)))
            visit_min += v.duration_minutes
            if v.end_minute - v.start_minute != v.duration_minutes:
                out.append(Violation("END_NOT_START_PLUS_DURATION", d, pos))
            if v.start_minute < config.day_start_minute:
                out.append(Violation("BEFORE_DAY_START", d, pos, str(v.start_minute)))
            if v.end_minute > day_end:
                out.append(Violation("AFTER_DAY_END", d, pos, str(v.end_minute)))

            if not v.reasons:
                out.append(Violation("MISSING_REASON", d, pos))
            for code in v.reasons:
                if code not in ITEM_TEMPLATES:
                    out.append(Violation("UNKNOWN_REASON", d, pos, code))

            last = pos == len(day.visits)
            leg = v.transfer
            if last:
                if leg is not None:
                    out.append(Violation("TRANSFER_AFTER_LAST_VISIT", d, pos))
                continue
            nxt = day.visits[pos]
            if leg is None:
                out.append(Violation("MISSING_TRANSFER", d, pos))
                continue
            travel_min += leg.minutes
            travel_sec += leg.seconds
            if leg.confidence == "routed":
                routed += 1
            else:
                estimated += 1
            a = Coord.from_degrees(v.lat, v.lon)
            b = Coord.from_degrees(nxt.lat, nxt.lon)
            mode = "walk" if distance_m(a, b) <= config.walk_max_m else "drive"
            if leg.mode != mode:
                out.append(Violation("TRANSFER_MODE", d, pos, f"{leg.mode} != {mode}"))
            if leg.minutes != (leg.seconds + 59) // 60 or leg.seconds < 0 or leg.meters < 0:
                out.append(Violation("TRANSFER_MINUTES", d, pos))
            given = known_times.get((a, b))
            if given is None or (given.seconds, given.meters, given.confidence) != (
                leg.seconds,
                leg.meters,
                leg.confidence,
            ):
                out.append(Violation("TRANSFER_NOT_FROM_SOURCE", d, pos))
            if nxt.start_minute < v.end_minute + leg.minutes:
                out.append(
                    Violation(
                        "OVERLAP",
                        d,
                        pos,
                        f"next starts {nxt.start_minute}, needs {v.end_minute + leg.minutes}",
                    )
                )

    for note in plan.notes:
        problem = _check_note(note.code, note.params)
        if problem:
            out.append(Violation("BAD_NOTE", detail=problem))

    s = plan.stats
    planned = visit_min + travel_min
    window = request.days * (config.day_window_end_minute - config.day_start_minute)
    expected = (
        visits,
        with_visits,
        visit_min,
        travel_min,
        travel_sec,
        routed,
        estimated,
        planned * 1000 // window if window else 0,
        travel_min * 1000 // planned if planned else 0,
    )
    actual = (
        s.visits,
        s.days_with_visits,
        s.visit_minutes,
        s.travel_minutes,
        s.travel_seconds,
        s.routed_transfers,
        s.estimated_transfers,
        s.day_utilisation_permille,
        s.travel_share_permille,
    )
    if expected != actual:
        out.append(Violation("STATS_MISMATCH", detail=f"{actual} != {expected}"))
    return out


def validate_generation(generation: Generation, config: PlannerConfig) -> list[Violation]:
    out: list[Violation] = []
    if not generation.engine_version or not generation.config_version:
        out.append(Violation("MISSING_VERSION"))
    if not 1 <= len(generation.plans) <= 2:
        out.append(Violation("PLAN_COUNT", detail=str(len(generation.plans))))
    profiles = [p.profile for p in generation.plans]
    if len(set(profiles)) != len(profiles):
        out.append(Violation("DUPLICATE_PROFILE"))
    if generation.distinct != (len(generation.plans) == 2):
        out.append(Violation("DISTINCT_FLAG"))
    if len(generation.plans) == 2:
        a, b = (p.place_ids() for p in generation.plans)
        union = len(a | b)
        if not a or not b:
            out.append(Violation("EMPTY_VARIANT"))
        elif len(a & b) * config.max_jaccard_den > config.max_jaccard_num * union:
            out.append(Violation("NOT_DISTINCT", detail=f"{len(a & b)}/{union}"))
        elif len(b) * 100 < config.min_second_variant_pct * len(a):
            out.append(Violation("SECOND_VARIANT_TOO_SMALL", detail=f"{len(b)} of {len(a)}"))
    for note in generation.notes:
        problem = _check_note(note.code, note.params)
        if problem:
            out.append(Violation("BAD_NOTE", detail=problem))
    return out
