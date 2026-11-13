"""Previewing and applying a change to a plan (Phase 7, ADR 018), with per-stage timings in the
logs (the KPI source for recalculation latency and acceptance).

Preview:
1. one transaction: the itinerary, the place to add or the item to remove, and the data around
   the plan (repo/changes.py)
2. no transaction: the recalculation, which may wait on the routing provider (bounded), and the
   independent validator; or, when the change undoes the latest addition, the stored version
3. one transaction: the change set with its proposal and diff

Nothing in the itinerary changes until ``apply``.
"""

import time
import uuid
from dataclasses import asdict

import structlog

from detour_api.deps import Session
from detour_api.errors import ApiError, conflict, invalid
from detour_api.models.changes import ChangeSet, ChangeSetApplied, ChangeSetCreate
from detour_api.models.restaurants import SlotRequest, SlotSuggestions
from detour_api.planner import diff, recalc, restaurant_slots
from detour_api.planner.config import DEFAULT_CONFIG, ENGINE_VERSION, PlannerConfig
from detour_api.planner.recalc import DEFAULT_RECALC, RecalcConfig, Revision
from detour_api.planner.revision_validator import validate_revision
from detour_api.planner.travel import ServiceTravelSource
from detour_api.planner.types import Note, PlanningImpossible
from detour_api.repo import changes
from detour_api.repo.plan_state import State, from_rplan, to_rplan
from detour_api.settings import Settings
from detour_api.travel.service import TravelTimeService

log = structlog.get_logger("detour.recalc")


def preview(
    session: Session,
    itinerary_id: uuid.UUID,
    body: ChangeSetCreate,
    travel: TravelTimeService,
    settings: Settings,
    config: PlannerConfig = DEFAULT_CONFIG,
    rconfig: RecalcConfig = DEFAULT_RECALC,
) -> ChangeSet:
    started = time.perf_counter()
    with session.tx() as conn:
        ctx = changes.load_context(
            conn, session.installation_id, itinerary_id, body, config, rconfig
        )
    loaded = time.perf_counter()

    notes: list[Note]
    if ctx.restores is not None:
        proposal = ctx.restores[1]
        notes = [Note("PLAN_RESTORED", {"name": ctx.target_name})]
    else:
        assert ctx.recalc is not None  # noqa: S101 - set whenever nothing is restored
        revision = _recalculate(ctx, travel, settings, config, rconfig)
        proposal = _proposal(ctx.state, revision, ctx.data_version, config, rconfig)
        notes = [n for n in revision.notes if n.code in changes.CHANGE_NOTES]
    computed = time.perf_counter()

    planned = diff.compare(to_rplan(ctx.state, ctx.profile), to_rplan(proposal, ctx.profile))
    with session.tx() as conn:
        result = changes.save(
            conn, session.installation_id, ctx, proposal, changes.diff_model(planned), notes
        )
    saved = time.perf_counter()
    log.info(
        "change_previewed",
        itinerary_id=str(itinerary_id),
        change_set_id=str(result.id),
        action=ctx.action,
        slot=None if ctx.slot_day is None else f"{ctx.slot_day}:{ctx.slot_meal}",
        restores=ctx.restores is not None,
        days_changed=list(planned.days_changed),
        added=len(planned.added),
        removed=len(planned.removed),
        moved=len(planned.moved),
        travel_minutes_added=planned.travel_minutes_added,
        load_ms=round((loaded - started) * 1000, 1),
        engine_ms=round((computed - loaded) * 1000, 1),
        save_ms=round((saved - computed) * 1000, 1),
        total_ms=round((saved - started) * 1000, 1),
    )
    return result


def _recalculate(
    ctx: changes.Context,
    travel: TravelTimeService,
    settings: Settings,
    config: PlannerConfig,
    rconfig: RecalcConfig,
) -> Revision:
    assert ctx.recalc is not None  # noqa: S101
    source = ServiceTravelSource(travel, max_seconds=settings.recalc_provider_max_seconds)
    try:
        if ctx.dining is not None:
            assert ctx.slot_day is not None and ctx.slot_meal is not None  # noqa: S101
            revision = restaurant_slots.add_restaurant(
                ctx.recalc,
                ctx.dining,
                ctx.slot_day,
                ctx.slot_meal,  # type: ignore[arg-type]
                None if ctx.after_item_id is None else str(ctx.after_item_id),
                source,
                config=config,
                rconfig=rconfig,
                use_provider=settings.planner_use_provider,
            )
        elif ctx.addition is not None:
            revision = recalc.add_place(
                ctx.recalc,
                ctx.addition,
                source,
                config=config,
                rconfig=rconfig,
                use_provider=settings.planner_use_provider,
            )
        else:
            assert ctx.removed_key is not None  # noqa: S101
            revision = recalc.remove_place(
                ctx.recalc,
                ctx.removed_key,
                source,
                config=config,
                rconfig=rconfig,
                use_provider=settings.planner_use_provider,
            )
    except PlanningImpossible as exc:
        log.info(
            "recalculation_impossible",
            itinerary_id=str(ctx.itinerary_id),
            action=ctx.action,
            issues=[i.code for i in exc.issues],
        )
        raise changes.impossible(exc.issues) from exc
    problems = validate_revision(
        ctx.recalc.plan,
        revision,
        added=(
            ctx.dining.key
            if ctx.dining is not None
            else None
            if ctx.addition is None
            else ctx.addition.key
        ),
        removed=ctx.removed_key,
        candidates={c.place_id: c for c in ctx.recalc.candidates},
        restaurants={r.place_id: r for r in ctx.recalc.restaurants},
        config=config,
        added_meal=ctx.dining,
    )
    if problems:
        # A bug: never shown as a proposal.
        log.error("revision_invalid", itinerary_id=str(ctx.itinerary_id), violations=str(problems))
        raise ApiError(500, "plan_invalid", "the recalculation produced an invalid plan")
    return revision


def _proposal(
    current: State,
    revision: Revision,
    data_version: str | None,
    config: PlannerConfig,
    rconfig: RecalcConfig,
) -> State:
    summary = {
        **current["summary"],
        "stats": asdict(revision.stats),
        "notes": [{"code": n.code, "params": n.params} for n in revision.notes],
    }
    versions = {
        "engine_version": f"{ENGINE_VERSION}+{recalc.RECALC_VERSION}",
        "config_version": recalc.config_version(config, rconfig),
        "import_run_id": data_version,
    }
    return from_rplan(revision.plan, current, summary, versions)


def apply(session: Session, change_id: uuid.UUID) -> ChangeSetApplied:
    with session.tx() as conn:
        result = changes.apply(conn, session.installation_id, change_id)
    if result is None:
        log.info("change_expired", change_set_id=str(change_id))
        raise conflict(
            "change_set_stale", "the plan changed after this preview; preview the change again"
        )
    log.info(
        "change_applied",
        change_set_id=str(change_id),
        itinerary_id=str(result.itinerary.id),
        version=result.itinerary.version,
    )
    return result


def discard(session: Session, change_id: uuid.UUID) -> ChangeSet:
    with session.tx() as conn:
        result = changes.discard(conn, session.installation_id, change_id)
    log.info("change_discarded", change_set_id=str(change_id))
    return result


def suggest_slots(
    session: Session,
    itinerary_id: uuid.UUID,
    body: SlotRequest,
    travel: TravelTimeService,
    settings: Settings,
    config: PlannerConfig = DEFAULT_CONFIG,
    rconfig: RecalcConfig = DEFAULT_RECALC,
) -> SlotSuggestions:
    """Up to three slots for a restaurant, best first (ADR 019). Nothing is stored and no routing
    provider is asked: times come from the cache and labelled estimates; the preview that follows
    asks the provider for the changed day's legs."""
    started = time.perf_counter()
    with session.tx() as conn:
        ctx = changes.load_restaurant_context(
            conn,
            session.installation_id,
            itinerary_id,
            body.place_id,
            body.user_place_id,
            config,
            rconfig,
        )
    assert ctx.recalc is not None and ctx.dining is not None  # noqa: S101
    days = len(ctx.state["days"])
    if body.day is not None and body.day > days:
        raise invalid("day_not_found", f"the plan has {days} days")
    loaded = time.perf_counter()
    source = ServiceTravelSource(travel, max_seconds=settings.recalc_provider_max_seconds)
    try:
        result = restaurant_slots.suggest(
            ctx.recalc,
            ctx.dining,
            source,
            day=body.day,
            meal=body.meal_type,
            config=config,
            rconfig=rconfig,
        )
    except PlanningImpossible as exc:
        raise changes.impossible(exc.issues) from exc
    response = changes.slot_suggestions(ctx.dining, result)
    log.info(
        "restaurant_slots_suggested",
        itinerary_id=str(itinerary_id),
        suggestions=len(result.suggestions),
        # Best first, "day:meal": with change_previewed's slot, the source of the acceptance KPI.
        slots=[f"{x.day_index}:{x.meal_type}" for x in result.suggestions],
        slots_considered=result.slots_considered,
        load_ms=round((loaded - started) * 1000, 1),
        engine_ms=round((time.perf_counter() - loaded) * 1000, 1),
    )
    return response
