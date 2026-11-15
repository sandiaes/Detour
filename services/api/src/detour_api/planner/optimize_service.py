"""Previewing Optimize and its undo (ADR 029), as Phase 7 change sets (action ``optimize``).

1. one transaction: the itinerary of any profile, its trip, the stored plan;
2. no transaction: the search (``planner/optimize.py``), which may wait on the routing provider
   (bounded), and the independent check (``planner/optimize_validator.py``);
3. one transaction: the change set with its proposal and diff.

Applying and discarding are the ordinary change-set endpoints. Nothing changes before apply.
"""

import time
import uuid
from dataclasses import asdict
from typing import Any

import structlog
from sqlalchemy import text

from detour_api.deps import Session
from detour_api.errors import ApiError, conflict, invalid
from detour_api.models.changes import ChangeSet, OptimizeRequest
from detour_api.models.trips import Stay
from detour_api.planner import diff, optimize, recalc
from detour_api.planner.config import DEFAULT_CONFIG, ENGINE_VERSION, PlannerConfig
from detour_api.planner.optimize_validator import validate
from detour_api.planner.recalc import RDay, RPlan
from detour_api.planner.travel import ServiceTravelSource, TravelLookup
from detour_api.planner.types import Note
from detour_api.repo import changes, stays, trips
from detour_api.repo.plan_state import State, read_state, to_rplan
from detour_api.settings import Settings
from detour_api.travel.service import TravelTimeService
from detour_api.travel.types import Coord

log = structlog.get_logger("detour.optimize")

MIN_STOPS = 3
WALK_EVERYWHERE_M = 10**9


def preview_optimize(
    session: Session,
    itinerary_id: uuid.UUID,
    body: OptimizeRequest,
    travel: TravelTimeService,
    settings: Settings,
    config: PlannerConfig = DEFAULT_CONFIG,
) -> ChangeSet:
    started = time.perf_counter()
    with session.tx() as conn:
        row = changes.itinerary_row(conn, session.installation_id, itinerary_id)
        trip_id = conn.execute(
            text("SELECT trip_id FROM app.itinerary WHERE id = :i"), {"i": itinerary_id}
        ).scalar_one()
        trip = trips.require_trip(conn, session.installation_id, trip_id)
        state = read_state(conn, itinerary_id)
        trip_stays = stays.list_for_trip(conn, trip_id)
    day_index = {d["id"]: d["day_index"] for d in state["days"]}
    items = [{**r, "day": day_index[r["day_id"]]} for r in state["items"]]
    known = {str(r["id"]) for r in items}
    unknown = [str(i) for i in body.fixed_item_ids if str(i) not in known]
    if unknown:
        raise invalid("unknown_items", "fixed_item_ids names stops that are not in this plan")
    located = [r for r in items if r["lat"] is not None and r["type"] != "free_time"]
    if len(located) < MIN_STOPS:
        raise ApiError(
            422, "not_enough_stops", f"Optimize needs at least {MIN_STOPS} stops with a place"
        )
    if len(located) > optimize.MAX_STOPS:
        raise ApiError(
            422, "too_many_stops", f"Optimize handles at most {optimize.MAX_STOPS} stops"
        )

    days = [optimize.DayInfo(d["day_index"], d["base_city_id"]) for d in state["days"]]
    cities = (
        [optimize.CityPoint(s.city_id, s.lat, s.lon) for s in trip.stops]
        if trip.destination.kind == "route"
        else []
    )
    point = (
        (trip.destination.lat, trip.destination.lon) if trip.destination.kind == "place" else None
    )
    stops, far = optimize.build_stops(
        items,
        days,
        scope=body.scope,
        fixed_ids=[str(i) for i in body.fixed_item_ids],
        cities=cities,
        place_point=point,
    )
    loaded = time.perf_counter()

    rules = optimize.rules_of(config)
    source = ServiceTravelSource(travel, max_seconds=settings.recalc_provider_max_seconds)
    # Without a car every leg is walked, however long (the mode rule of planner/travel.py).
    lookup = TravelLookup(source, config.walk_max_m if trip.uses_car else WALK_EVERYWHERE_M)
    day_numbers = [d.index for d in days]
    # Each day starts at its stay, when it has one (ADR 030): the leg to the first stop counts.
    anchors: dict[int, Coord] = {}
    day_stay: dict[int, Stay] = {}
    for n in day_numbers:
        stay = stays.stay_of_day(trip_stays, n)
        if stay is not None:
            anchors[n] = Coord.from_degrees(stay.lat, stay.lon)
            day_stay[n] = stay
    outcome = optimize.optimize(
        stops,
        day_numbers,
        scope=body.scope,
        lookup=lookup,
        use_provider=settings.planner_use_provider,
        rules=rules,
        anchors=anchors,
    )
    problems = validate(stops, day_numbers, outcome, rules)
    if problems:
        log.error("optimize_invalid", itinerary_id=str(itinerary_id), violations=problems)
        raise ApiError(500, "plan_invalid", "Optimize produced an invalid plan")
    if not outcome.changed_days:
        raise conflict("no_better_order", "No shorter order was found for these stops")
    computed = time.perf_counter()

    kept = sum(1 for s in stops if s.fixed and s.kind != "free_time")
    notes = [
        Note(
            "OPTIMIZED",
            {
                "saved": outcome.travel_before - outcome.travel_after,
                "before": outcome.travel_before,
                "after": outcome.travel_after,
                "km": max(0, (outcome.meters_before - outcome.meters_after) // 1000),
            },
        )
    ]
    if outcome.estimated_after:
        legs = sum(1 for d in outcome.days.values() for p in d if p.leg is not None)
        notes.append(
            Note("OPTIMIZE_ESTIMATED", {"estimated": outcome.estimated_after, "legs": legs})
        )
    if kept:
        notes.append(Note("OPTIMIZE_KEPT", {"count": kept}))
    if far:
        notes.append(Note("OPTIMIZE_FAR_KEPT", {"count": far, "name": trip.destination.name}))
    notes += [Note("OPTIMIZE_NOT_SHORTEST"), Note("OPTIMIZE_NO_HOURS")]

    before_state = _with_plan(state, outcome.before, {})
    proposal = _with_plan(
        state,
        outcome.days,
        {
            "engine_version": f"{ENGINE_VERSION}+{optimize.OPTIMIZE_VERSION}",
            "config_version": state["config_version"],
            "import_run_id": state["import_run_id"],
        },
    )
    proposal["starts"] = _starts(outcome.days, day_stay, state)
    proposal["summary"] = {
        **state["summary"],
        "stats": asdict(recalc.revision_stats(_without_blocks(proposal, row.profile), config)),
        "notes": [{"code": n.code, "params": n.params} for n in notes],
    }
    planned = diff.compare(to_rplan(before_state, row.profile), to_rplan(proposal, row.profile))
    diff_out = changes.diff_model(planned)
    # The saving counts the legs from the stays too, which the stored plan does not carry.
    diff_out.travel_minutes_before = outcome.travel_before
    diff_out.travel_minutes_after = outcome.travel_after
    diff_out.travel_minutes_added = outcome.travel_after - outcome.travel_before
    ctx = changes.Context(
        itinerary_id=itinerary_id,
        version=row.version,
        profile=row.profile,
        state=state,
        action="optimize",
        target_name="Shorter order",
        data_version=state["import_run_id"],
        recalc=None,
    )
    with session.tx() as conn:
        result = changes.save(conn, session.installation_id, ctx, proposal, diff_out, notes)
    log.info(
        "optimize_previewed",
        itinerary_id=str(itinerary_id),
        change_set_id=str(result.id),
        scope=body.scope,
        stops=len(located),
        fixed=kept,
        days_changed=list(outcome.changed_days),
        travel_before=outcome.travel_before,
        travel_after=outcome.travel_after,
        estimated_legs=outcome.estimated_after,
        load_ms=round((loaded - started) * 1000, 1),
        engine_ms=round((computed - loaded) * 1000, 1),
        total_ms=round((time.perf_counter() - started) * 1000, 1),
    )
    return result


def preview_undo(session: Session, itinerary_id: uuid.UUID) -> ChangeSet:
    """Restore the plan from before the latest applied Optimize, if nothing changed it since."""
    with session.tx() as conn:
        row = changes.itinerary_row(conn, session.installation_id, itinerary_id)
        restores = changes.latest_optimize(conn, itinerary_id, row.version)
        state = read_state(conn, itinerary_id)
    if restores is None:
        raise conflict("nothing_to_undo", "the plan has changed since Optimize, or never had it")
    base_version, proposal = restores
    notes = [Note("OPTIMIZE_UNDONE")]
    planned = diff.compare(to_rplan(state, row.profile), to_rplan(proposal, row.profile))
    ctx = changes.Context(
        itinerary_id=itinerary_id,
        version=row.version,
        profile=row.profile,
        state=state,
        action="optimize",
        target_name="Undo Optimize",
        data_version=state["import_run_id"],
        recalc=None,
        restores=(base_version, proposal),
    )
    with session.tx() as conn:
        result = changes.save(
            conn, session.installation_id, ctx, proposal, changes.diff_model(planned), notes
        )
    log.info("optimize_undo_previewed", itinerary_id=str(itinerary_id), restores=base_version)
    return result


# -- the proposal as a stored state ----------------------------------------------------------------


def _with_plan(
    state: State, days: dict[int, tuple[optimize.Laid, ...]], versions: dict[str, Any]
) -> State:
    """The state with the items in the given order, days, times and legs."""
    day_id = {d["day_index"]: d["id"] for d in state["days"]}
    by_id = {r["id"]: r for r in state["items"]}
    items: list[dict[str, Any]] = []
    transfers: list[dict[str, Any]] = []
    for d in sorted(days):
        laid = days[d]
        for n, p in enumerate(laid, start=1):
            r = by_id[p.id]
            moved = {
                **r,
                "day_id": day_id[d],
                "position": n,
                "start_minute": p.start,
                "end_minute": p.end,
            }
            items.append(moved)
            if p.leg is not None and n < len(laid):
                transfers.append(
                    {
                        "from_item_id": p.id,
                        "to_item_id": laid[n].id,
                        "mode": p.leg.mode,
                        "seconds": p.leg.seconds,
                        "meters": p.leg.meters,
                        "confidence": p.leg.confidence,
                    }
                )
    return {**state, **versions, "items": items, "transfers": transfers}


def _starts(
    days: dict[int, tuple[optimize.Laid, ...]], day_stay: dict[int, Stay], state: State
) -> list[dict[str, Any]]:
    """The proposal's morning legs from the stays, for the preview (not stored with the plan: a
    plan read later works them out again from the stays)."""
    out: list[dict[str, Any]] = []
    for d in sorted(days):
        stay = day_stay.get(d)
        first = next((p for p in days[d] if p.head is not None), None)
        if stay is None or first is None or first.head is None:
            continue
        out.append(
            {
                "day_index": d,
                "stay_id": str(stay.id),
                "name": stay.name,
                "lat": stay.lat,
                "lon": stay.lon,
                "to_item_id": first.id,
                "mode": first.head.mode,
                "seconds": first.head.seconds,
                "meters": first.head.meters,
                "confidence": first.head.confidence,
            }
        )
    return out


def _without_blocks(state: State, profile: str) -> list[RDay]:
    """The plan's days without free-time blocks, for the statistics (they are neither visits nor
    meals)."""
    plan: RPlan = to_rplan(state, profile)
    return [
        RDay(
            d.day_index,
            d.date,
            d.base_city_id,
            d.base_city_name,
            tuple(e for e in d.items if e.kind in ("visit", "meal")),
            d.arrival,
            d.arrival_unknown,
        )
        for d in plan.days
    ]
