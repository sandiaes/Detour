"""Previewing a change to a multi-city trip's stops (ADR 024, decision 19).

The preview is a Phase 7 change set (action ``edit_stops``) on the trip's active itinerary: it is
applied or discarded through the same endpoints, it makes a new itinerary version on apply, and
nothing changes before. The proposal carries the trip's new stops, name and length, which apply
writes with the plan.

1. one transaction: the trip, the active plan and its stops, the new stops checked against the
   imported data, and the sights and places to eat around every old and new stop;
2. no transaction: the new day list (``stop_edits.assemble``), new days filled by the planner,
   every changed day laid out again, and the independent revision validator;
3. one transaction: the change set with its proposal and diff.
"""

import time
import uuid
from dataclasses import asdict
from typing import Any

import structlog
from sqlalchemy import text

from detour_api.deps import Session
from detour_api.errors import ApiError, conflict
from detour_api.models.changes import ChangeSet
from detour_api.models.trips import StopIn
from detour_api.planner import diff, recalc, stop_edits
from detour_api.planner.config import DEFAULT_CONFIG, ENGINE_VERSION, PlannerConfig
from detour_api.planner.recalc import DEFAULT_RECALC, RecalcConfig, RecalcInput
from detour_api.planner.revision_validator import validate_revision
from detour_api.planner.sequencer import HeuristicSequencer
from detour_api.planner.travel import ServiceTravelSource
from detour_api.planner.types import Note, PlanningImpossible
from detour_api.repo import changes, planning, routes, trips
from detour_api.repo.plan_state import from_rplan, read_state, to_rplan, unscheduled
from detour_api.settings import Settings
from detour_api.travel.service import TravelTimeService

log = structlog.get_logger("detour.recalc")


def preview_stops(
    session: Session,
    trip_id: uuid.UUID,
    stops: list[StopIn],
    travel: TravelTimeService,
    settings: Settings,
    config: PlannerConfig = DEFAULT_CONFIG,
    rconfig: RecalcConfig = DEFAULT_RECALC,
) -> ChangeSet:
    started = time.perf_counter()
    with session.tx() as conn:
        trip = trips.require_open_trip(conn, session.person_id, trip_id)
        if trip.destination.kind != "route":
            raise conflict("not_a_route", "only a multi-city trip has stops to edit")
        if trip.selected_itinerary_id is None:
            raise conflict(
                "no_active_plan",
                "this trip has no chosen plan; change its stops with PUT /v1/trips/{id}/stops",
            )
        new_stops, name = routes.resolve_stops(conn, stops, None)
        itinerary_id = trip.selected_itinerary_id
        row = conn.execute(
            text("SELECT profile, version FROM app.itinerary WHERE id = :i"), {"i": itinerary_id}
        ).one()
        state = read_state(conn, itinerary_id)
        issues = unscheduled(state)
        if issues and row.profile != "manual":
            raise changes.impossible(issues)
        wanted = {s.city_id for s in trip.stops} | {s.city_id for s in new_stops}
        cities = changes.cities(conn, sorted(wanted))
        countries = changes.countries(conn, sorted(cities))
        radius = max(p.radius_m for p in config.profiles)
        cands: dict[str, Any] = {}
        for city in cities.values():
            dest_region = changes.region_of(conn, countries.get(city.city_id))
            if dest_region is None:
                continue
            for c in planning.load_candidates(conn, dest_region, city.lat, city.lon, radius):
                cands.setdefault(c.place_id, c)
        rplan = to_rplan(state, row.profile)
    loaded = time.perf_counter()

    old = [stop_edits.OldStop(s.city_id, s.days) for s in trip.stops]
    new = [stop_edits.NewStop(cities[s.city_id], s.days) for s in new_stops]
    assembly = stop_edits.assemble(rplan, old, new, trip.start_date)
    if assembly.issues:
        raise changes.impossible(list(assembly.issues))
    removed_marked = [
        e.name
        + (" (added by you)" if e.origin == "user" else "")
        + (" (locked)" if e.locked else "")
        for e in assembly.removed
        if e.kind == "visit" or e.origin == "user"
    ]
    notes: list[Note] = []
    if removed_marked:
        notes.append(Note("STOP_REMOVED_ITEMS", {"items": ", ".join(removed_marked)}))
    notes.append(Note("STOPS_CHANGED", {"name": name}))
    inp = RecalcInput(
        plan=rplan,
        notes=(),
        bases=cities,
        candidates=tuple(cands[k] for k in sorted(cands)),
        route=True,
        rail_bases=frozenset(b for b, c in countries.items() if c in config.single_city_countries),
    )
    source = ServiceTravelSource(travel, max_seconds=settings.recalc_provider_max_seconds)
    planned_keys = frozenset(
        e.place_id or "" for d in assembly.plan.days for e in d.items if e.kind == "visit"
    )
    fills: dict[int, Any] = {}
    if row.profile != "manual":
        for position, day_indices in assembly.to_fill:
            entries = stop_edits.fill_days(
                new[position],
                len(day_indices),
                row.profile,
                inp.candidates,
                planned_keys
                | frozenset(
                    e.place_id or "" for es in fills.values() for e in es if e.kind == "visit"
                ),
                source,
                config=config,
                sequencer=HeuristicSequencer(),
            )
            for k, items in zip(day_indices, entries, strict=True):
                fills[k] = items
    try:
        if row.profile == "manual":
            before = assembly.plan
            proposal_plan = before
            stats = recalc.revision_stats(before.days, config)
        else:
            before, revision = stop_edits.relay(
                inp,
                assembly,
                fills,
                source,
                config=config,
                rconfig=rconfig,
                use_provider=settings.planner_use_provider,
                notes=notes,
            )
            problems = validate_revision(
                before,
                revision,
                added=None,
                removed=None,
                candidates={c.place_id: c for c in inp.candidates},
                config=config,
            )
            if problems:
                log.error("stop_edit_invalid", trip_id=str(trip_id), violations=str(problems))
                raise ApiError(500, "plan_invalid", "the stop edit produced an invalid plan")
            proposal_plan = revision.plan
            stats = revision.stats
    except PlanningImpossible as exc:
        raise changes.impossible(list(exc.issues)) from exc
    computed = time.perf_counter()

    summary = {
        **state["summary"],
        "stats": asdict(stats),
        "notes": [{"code": n.code, "params": n.params} for n in notes],
    }
    versions = {
        "engine_version": f"{ENGINE_VERSION}+{recalc.RECALC_VERSION}",
        "config_version": recalc.config_version(config, rconfig),
        "import_run_id": state.get("import_run_id"),
    }
    proposal = from_rplan(proposal_plan, state, summary, versions)
    proposal["trip_edit"] = {
        "name": name,
        "duration_days": sum(s.days for s in new_stops),
        "stops": [
            {
                "city_id": s.city_id,
                "name": s.name,
                "country_iso2": s.country_iso2,
                "lat": s.lat,
                "lon": s.lon,
                "days": s.days,
            }
            for s in new_stops
        ],
    }
    planned = diff.compare(rplan, to_rplan(proposal, row.profile))
    ctx = changes.Context(
        itinerary_id=itinerary_id,
        version=row.version,
        profile=row.profile,
        state=state,
        action="edit_stops",
        target_name=name,
        data_version=state.get("import_run_id"),
        recalc=inp,
    )
    with session.tx() as conn:
        result = changes.save(
            conn, session.person_id, ctx, proposal, changes.diff_model(planned), notes
        )
    log.info(
        "stops_previewed",
        trip_id=str(trip_id),
        change_set_id=str(result.id),
        stops=len(new_stops),
        removed=len(assembly.removed),
        filled=len(fills),
        load_ms=round((loaded - started) * 1000, 1),
        engine_ms=round((computed - loaded) * 1000, 1),
        total_ms=round((time.perf_counter() - started) * 1000, 1),
    )
    return result
