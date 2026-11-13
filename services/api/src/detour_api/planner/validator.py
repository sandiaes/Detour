"""The independent validator (architecture section 5.2, step 7).

It re-reads a finished plan against the engine's inputs and checks it **without the engine's
scheduling code**: times are re-added from the plan's own numbers, minutes are recomputed from
seconds, the mode rule, the duration table, the meal windows and the meal lengths are applied
again, and every transfer is compared with the value the travel source returned for that pair. A
violation is a bug in the engine: the plan is never shown (``PlanInvalid``).

Checked:

* the trip's days, in order, with the right dates;
* each day's base city: the destination city for a city trip, one of the area's towns for an
  area; an inter-city leg starts the day exactly when the base changes, from the previous base,
  with a mode, minutes and value as for any transfer;
* every visit is a candidate the engine was given (no manufactured attraction), with that
  candidate's name, point and category, at most once per plan; durations are the category
  defaults;
* every meal is at a place to eat the engine was given, with its name, point, venue type and
  cuisines; the place lists the meal type; the meal type is one of the profile's, at most once a
  day; a place is used at most once a day, and again on a later day only with the reason
  ``PLACE_REPEATED``; the length follows the meal-length table; **the meal starts
  and ends inside its meal window**; meals only on days with visits;
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
from detour_api.planner.types import Candidate, Generation, Leg, Plan, PlanRequest, Restaurant
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
    restaurants: Mapping[str, Restaurant],
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

    if len(plan.days) != request.days:
        out.append(Violation("DAY_COUNT", detail=f"{len(plan.days)} != {request.days}"))
    seen_visits: set[str] = set()
    seen_meal_places: set[str] = set()  # on earlier days
    visits = visit_min = meal_min = meals = 0
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
        moved = expected_index > 1 and day.base_city_id != previous_base
        day_start = config.day_start_minute
        if moved != (day.arrival is not None):
            out.append(Violation("ARRIVAL_MISMATCH", d))
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
            out.append(Violation("MEALS_WITHOUT_VISITS", d))
        meal_types_today: set[str] = set()
        meal_places_today: set[str] = set()
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
                if item.meal_type is not None or item.cuisines is not None:
                    out.append(Violation("VISIT_WITH_MEAL_FIELDS", d, pos))
                if item.place_id in seen_visits:
                    out.append(Violation("DUPLICATE_VISIT", d, pos, item.place_id))
                seen_visits.add(item.place_id)
            else:
                meals += 1
                meal_min += item.duration_minutes
                r = restaurants.get(item.place_id)
                meal = item.meal_type
                if r is None:
                    out.append(Violation("UNKNOWN_RESTAURANT", d, pos, item.place_id))
                elif (item.name, item.lat, item.lon, item.category, item.cuisines) != (
                    r.name,
                    r.lat,
                    r.lon,
                    r.venue_type,
                    r.cuisines,
                ):
                    out.append(Violation("SNAPSHOT_MISMATCH", d, pos, item.place_id))
                if meal is None or meal not in profile.meals:
                    out.append(Violation("MEAL_TYPE_NOT_PLANNED", d, pos, str(meal)))
                    continue
                if r is not None and meal not in r.meal_types:
                    out.append(Violation("VENUE_DOES_NOT_SERVE_MEAL", d, pos, meal))
                if meal in meal_types_today:
                    out.append(Violation("MEAL_TWICE_A_DAY", d, pos, meal))
                meal_types_today.add(meal)
                if item.place_id in meal_places_today:
                    out.append(Violation("RESTAURANT_TWICE_A_DAY", d, pos, item.place_id))
                meal_places_today.add(item.place_id)
                if (item.place_id in seen_meal_places) != ("PLACE_REPEATED" in item.reasons):
                    out.append(Violation("REPEATED_PLACE_REASON", d, pos, item.place_id))
                venue = r.venue_type if r is not None else None
                if item.duration_minutes != config.meal_minutes(meal, venue):
                    out.append(Violation("MEAL_LENGTH", d, pos, str(item.duration_minutes)))
                meal_window = config.meal_window(meal)
                if (
                    item.start_minute < meal_window.start_minute
                    or item.end_minute > meal_window.end_minute
                ):
                    out.append(
                        Violation(
                            "MEAL_OUTSIDE_WINDOW",
                            d,
                            pos,
                            f"{meal} {item.start_minute}-{item.end_minute}",
                        )
                    )

            last = pos == len(day.items)
            if last:
                seen_meal_places.update(meal_places_today)
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
            if nxt.start_minute < item.end_minute + leg.minutes:
                out.append(
                    Violation(
                        "OVERLAP",
                        d,
                        pos,
                        f"next starts {nxt.start_minute}, needs {item.end_minute + leg.minutes}",
                    )
                )

    for note in plan.notes:
        problem = _check_note(note.code, note.params)
        if problem:
            out.append(Violation("BAD_NOTE", detail=problem))

    s = plan.stats
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
