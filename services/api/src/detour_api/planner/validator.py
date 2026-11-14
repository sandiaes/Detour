"""The independent validator (architecture section 5.2, step 7).

It re-reads a finished plan against the engine's inputs and checks it **without the engine's
scheduling code**: times are re-added from the plan's own numbers, minutes are recomputed from
seconds, the mode rule and the duration table are applied again, the midday gap is checked, and
every transfer is compared with the value the travel source returned for that pair. A
violation is a bug in the engine: the plan is never shown (``PlanInvalid``).

Checked:

* the trip's days, in order, with the right dates;
* each day's base city: the destination city for a city trip, one of the area's towns for an
  area; an inter-city leg starts the day exactly when the base changes, from the previous base,
  with a mode, minutes and value as for any transfer;
* every visit is a candidate the engine was given (no manufactured attraction), with that
  candidate's name, point and category, at most once per plan; durations are the category
  defaults;
* **a generated plan holds sights only** (ADR 026): any other kind of item is a violation;
* **the midday gap**: the idle time between two consecutive stops (what is left after the
  transfer) is either nothing or the gap, at most one a day: it lasts at least the gap's length and
  ends no earlier than the gap's earliest start plus its length;
* ``end = start + duration``; every item lies inside the day window, after the inter-city leg, and
  ends by the profile's day end (**day length respected**);
* items do not overlap, and the gap between two items holds the transfer;
* a transfer joins every pair of consecutive items and only those; its mode follows the walking
  threshold, its minutes are its seconds rounded up, and its seconds, metres and label are exactly
  what the travel source returned (no invented travel time);
* every item has at least one reason, and every reason and note has a fixed template;
* the statistics match the plan.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta

from detour_api.planner.config import PlannerConfig
from detour_api.planner.durations import visit_minutes
from detour_api.planner.reasons import ITEM_TEMPLATES, NOTE_TEMPLATES, note_text
from detour_api.planner.types import Candidate, Generation, Leg, Plan, PlanRequest
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


def _check_leg(
    leg: Leg,
    a: Coord,
    b: Coord,
    known_times: Mapping[tuple[Coord, Coord], TravelTime],
    config: PlannerConfig,
    day: int,
    pos: int | None,
    prefix: str,
) -> list[Violation]:
    out: list[Violation] = []
    mode = "walk" if distance_m(a, b) <= config.walk_max_m else "drive"
    if leg.mode != mode:
        out.append(Violation(f"{prefix}_MODE", day, pos, f"{leg.mode} != {mode}"))
    if leg.minutes != (leg.seconds + 59) // 60 or leg.seconds < 0 or leg.meters < 0:
        out.append(Violation(f"{prefix}_MINUTES", day, pos))
    given = known_times.get((a, b))
    if given is None or (given.seconds, given.meters, given.confidence) != (
        leg.seconds,
        leg.meters,
        leg.confidence,
    ):
        out.append(Violation(f"{prefix}_NOT_FROM_SOURCE", day, pos))
    return out


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
    bases = {b.city_id: b for b in request.base_cities}
    # A multi-city trip (ADR 024): the stops, in the user's order, each for its days.
    route_bases: list[int] = []
    rail = set(config.single_city_countries)
    country: dict[int, str | None] = {}
    if request.kind == "route":
        bases = {st.city.city_id: st.city for st in request.stops}
        country = {st.city.city_id: st.country_iso2 for st in request.stops}
        route_bases = [st.city.city_id for st in request.stops for _ in range(st.days)]
        if len(route_bases) != request.days:
            out.append(Violation("STOP_DAYS", detail=f"{len(route_bases)} != {request.days}"))

    if len(plan.days) != request.days:
        out.append(Violation("DAY_COUNT", detail=f"{len(plan.days)} != {request.days}"))
    seen_visits: set[str] = set()
    gap = config.midday_gap
    visits = visit_min = 0
    travel_min = travel_sec = routed = estimated = with_visits = intercity = 0
    previous_base: int | None = None
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

        # Base city and the inter-city leg.
        if request.kind == "city":
            expected_base = request.base_cities[0].city_id if request.base_cities else None
            if day.base_city_id != expected_base:
                out.append(Violation("WRONG_BASE", d, detail=str(day.base_city_id)))
        elif day.base_city_id not in bases:
            out.append(Violation("UNKNOWN_BASE", d, detail=str(day.base_city_id)))
        elif day.base_city_name != bases[day.base_city_id].name:
            out.append(Violation("BASE_NAME_MISMATCH", d))
        if route_bases and (
            expected_index > len(route_bases) or day.base_city_id != route_bases[expected_index - 1]
        ):
            out.append(Violation("ROUTE_ORDER", d, detail=str(day.base_city_id)))
        moved = expected_index > 1 and day.base_city_id != previous_base
        day_start = config.day_start_minute
        rail_leg = moved and (
            country.get(day.base_city_id or 0) in rail or country.get(previous_base or 0) in rail
        )
        if day.arrival_unknown and day.arrival is not None:
            out.append(Violation("ARRIVAL_BOTH_KNOWN_AND_UNKNOWN", d))
        if moved != (day.arrival is not None or day.arrival_unknown):
            out.append(Violation("ARRIVAL_MISMATCH", d))
        elif day.arrival_unknown != rail_leg:
            # Only a leg into or out of a country travelled by rail has no time; any other leg
            # between stops is driven and has one (ADR 024, decisions 9 and 10).
            out.append(Violation("UNKNOWN_LEG_MISMATCH", d))
        elif day.arrival is not None:
            arr = day.arrival
            intercity += 1
            travel_min += arr.minutes
            travel_sec += arr.seconds
            routed += arr.confidence == "routed"
            estimated += arr.confidence != "routed"
            prev_city = bases.get(previous_base) if previous_base is not None else None
            this_city = bases.get(day.base_city_id) if day.base_city_id is not None else None
            if prev_city is None or this_city is None:
                out.append(Violation("ARRIVAL_WITHOUT_BASES", d))
            else:
                out.extend(
                    _check_leg(
                        arr,
                        prev_city.coord,
                        this_city.coord,
                        known_times,
                        config,
                        d,
                        None,
                        "ARRIVAL",
                    )
                )
            day_start += arr.minutes
        previous_base = day.base_city_id

        day_visits = [i for i in day.items if i.kind == "visit"]
        if day_visits:
            with_visits += 1
        elif day.items:
            out.append(Violation("ITEMS_WITHOUT_VISITS", d))
        idle_stretches = 0
        for pos, item in enumerate(day.items, start=1):
            if item.end_minute - item.start_minute != item.duration_minutes:
                out.append(Violation("END_NOT_START_PLUS_DURATION", d, pos))
            if item.start_minute < day_start:
                out.append(Violation("BEFORE_DAY_START", d, pos, str(item.start_minute)))
            if item.end_minute > day_end:
                out.append(Violation("AFTER_DAY_END", d, pos, str(item.end_minute)))
            if not item.reasons:
                out.append(Violation("MISSING_REASON", d, pos))
            for code in item.reasons:
                if code not in ITEM_TEMPLATES:
                    out.append(Violation("UNKNOWN_REASON", d, pos, code))

            if item.kind == "visit":
                visits += 1
                visit_min += item.duration_minutes
                c = candidates.get(item.place_id)
                if c is None:
                    out.append(Violation("UNKNOWN_PLACE", d, pos, item.place_id))
                else:
                    if (item.name, item.lat, item.lon, item.category) != (
                        c.name,
                        c.lat,
                        c.lon,
                        c.category,
                    ):
                        out.append(Violation("SNAPSHOT_MISMATCH", d, pos, item.place_id))
                    if item.duration_minutes != visit_minutes(c.category):
                        out.append(
                            Violation("DURATION_NOT_DEFAULT", d, pos, str(item.duration_minutes))
                        )
                    stop = bases.get(day.base_city_id or 0) if route_bases else None
                    if (
                        stop is not None
                        and round(distance_m(stop.coord, c.coord)) > profile.radius_m
                    ):
                        out.append(Violation("VISIT_OUTSIDE_STOP", d, pos, item.place_id))
                if item.place_id in seen_visits:
                    out.append(Violation("DUPLICATE_VISIT", d, pos, item.place_id))
                seen_visits.add(item.place_id)
            else:
                out.append(Violation("NOT_A_SIGHT", d, pos, item.kind))

            last = pos == len(day.items)
            leg = item.transfer
            if last:
                if leg is not None:
                    out.append(Violation("TRANSFER_AFTER_LAST_ITEM", d, pos))
                continue
            nxt = day.items[pos]
            if leg is None:
                out.append(Violation("MISSING_TRANSFER", d, pos))
                continue
            travel_min += leg.minutes
            travel_sec += leg.seconds
            routed += leg.confidence == "routed"
            estimated += leg.confidence != "routed"
            a = Coord.from_degrees(item.lat, item.lon)
            b = Coord.from_degrees(nxt.lat, nxt.lon)
            out.extend(_check_leg(leg, a, b, known_times, config, d, pos, "TRANSFER"))
            needs = item.end_minute + leg.minutes
            if nxt.start_minute < needs:
                out.append(
                    Violation(
                        "OVERLAP",
                        d,
                        pos,
                        f"next starts {nxt.start_minute}, needs {needs}",
                    )
                )
            elif nxt.start_minute > needs:
                idle = nxt.start_minute - needs
                idle_stretches += 1
                if idle < gap.minutes or nxt.start_minute < gap.earliest_start + gap.minutes:
                    out.append(Violation("IDLE_NOT_THE_GAP", d, pos, f"{idle} minutes"))
        if idle_stretches > 1:
            out.append(Violation("MORE_THAN_ONE_GAP", d, detail=str(idle_stretches)))

    for note in plan.notes:
        problem = _check_note(note.code, note.params)
        if problem:
            out.append(Violation("BAD_NOTE", detail=problem))

    s = plan.stats
    meals = meal_min = 0
    planned = visit_min + meal_min + travel_min
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
        meals,
        meal_min,
        intercity,
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
        s.meals,
        s.meal_minutes,
        s.intercity_legs,
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
        first, second = generation.plans
        a, b = first.place_ids(), second.place_ids()
        union = len(a | b)
        same_allocation = first.allocation() == second.allocation()
        if not a or not b:
            out.append(Violation("EMPTY_VARIANT"))
        elif same_allocation and len(a & b) * config.max_jaccard_den > (
            config.max_jaccard_num * union
        ):
            out.append(Violation("NOT_DISTINCT", detail=f"{len(a & b)}/{union}"))
        elif len(b) * 100 < config.min_second_variant_pct * len(a):
            out.append(Violation("SECOND_VARIANT_TOO_SMALL", detail=f"{len(b)} of {len(a)}"))
    for note in generation.notes:
        problem = _check_note(note.code, note.params)
        if problem:
            out.append(Violation("BAD_NOTE", detail=problem))
    return out
