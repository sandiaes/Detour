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
from detour_api.errors import ApiError, conflict
from detour_api.models.changes import (
    ChangeSet,
    ChangeSetApplied,
    ChangeSetCreate,
    PlaceSuggestion,
    PlaceSuggestionRequest,
    PlaceSuggestions,
    SuggestionReason,
)
from detour_api.planner import diff, recalc
from detour_api.planner.config import DEFAULT_CONFIG, ENGINE_VERSION, PlannerConfig
from detour_api.planner.reasons import issue_text
from detour_api.planner.recalc import DEFAULT_RECALC, RecalcConfig, Revision
from detour_api.planner.revision_validator import validate_revision
from detour_api.planner.travel import ServiceTravelSource
from detour_api.planner.types import Issue, Note, PlanningImpossible
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
        day=ctx.only_day,
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
        if ctx.addition is not None:
            revision = recalc.add_place(
                ctx.recalc,
                ctx.addition,
                source,
                config=config,
                rconfig=rconfig,
                use_provider=settings.planner_use_provider,
                only_day=ctx.only_day,
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
        added=None if ctx.addition is None else ctx.addition.key,
        removed=ctx.removed_key,
        candidates={c.place_id: c for c in ctx.recalc.candidates},
        config=config,
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


MAX_PLACE_SUGGESTIONS = 3

# Why a day is suggested: fixed templates over the computed facts (CLAUDE.md, constraint 1).
_SUGGESTION_TEXT = {
    "LEAST_TRAVEL": "Adds the least travel of the days that can take it.",
    "LESS_TRAVEL": "The plan travels {minutes} min less.",
    "MORE_TRAVEL": "Adds about {minutes} min of travel.",
    "NOTHING_LEFT_OUT": "Every planned visit stays in the plan.",
    "LEAVES_OUT": "Leaves out {names} to make room.",
    "NO_DAY_CHANGES": "No other visit changes day.",
    "VISITS_MOVE": "{count} other visits change day.",
    "NEW_BASE": "Day {day} would be spent based in {town}, near it.",
}


def _reason(code: str, **params: object) -> SuggestionReason:
    return SuggestionReason(code=code, text=_SUGGESTION_TEXT[code].format(**params))


def suggest_places(
    session: Session,
    itinerary_id: uuid.UUID,
    body: PlaceSuggestionRequest,
    travel: TravelTimeService,
    settings: Settings,
    config: PlannerConfig = DEFAULT_CONFIG,
    rconfig: RecalcConfig = DEFAULT_RECALC,
) -> PlaceSuggestions:
    """Up to three days a place could go on, best first (ADR 021). The recalculation of Phase 7
    is run once per day with only that day allowed, and the days are ranked by its own stability
    cost (travel, moved and left-out visits, retimed items), ties to the earlier day. Nothing is
    stored and no routing provider is asked: times come from the cache and labelled estimates;
    the preview of the chosen day asks the provider as usual."""
    started = time.perf_counter()
    request = ChangeSetCreate(
        action="add_place",
        place_id=body.place_id,
        user_place_id=body.user_place_id,
        duration_minutes=body.duration_minutes,
    )
    with session.tx() as conn:
        ctx = changes.load_context(
            conn, session.installation_id, itinerary_id, request, config, rconfig
        )
    assert ctx.recalc is not None and ctx.addition is not None  # noqa: S101
    loaded = time.perf_counter()
    source = ServiceTravelSource(travel, max_seconds=settings.recalc_provider_max_seconds)
    current = to_rplan(ctx.state, ctx.profile)
    found: list[tuple[int, int, Revision, diff.PlanDiff]] = []
    issues: list[Issue] = []
    days = [d.day_index for d in ctx.recalc.plan.days]
    for k in days:
        try:
            revision = recalc.add_place(
                ctx.recalc,
                ctx.addition,
                source,
                config=config,
                rconfig=rconfig,
                use_provider=False,
                only_day=k,
            )
        except PlanningImpossible as exc:
            issues.extend(exc.issues)
            continue
        problems = validate_revision(
            ctx.recalc.plan,
            revision,
            added=ctx.addition.key,
            removed=None,
            candidates={c.place_id: c for c in ctx.recalc.candidates},
            config=config,
        )
        if problems:
            # A bug: never suggested.
            log.error("suggestion_invalid", itinerary_id=str(itinerary_id), day=k)
            continue
        proposal = _proposal(ctx.state, revision, ctx.data_version, config, rconfig)
        found.append(
            (revision.cost, k, revision, diff.compare(current, to_rplan(proposal, ctx.profile)))
        )
    found.sort(key=lambda f: (f[0], f[1]))
    best = found[:MAX_PLACE_SUGGESTIONS]
    least = min((f[3].travel_minutes_added for f in best), default=0)
    suggestions: list[PlaceSuggestion] = []
    for rank, (_, k, revision, planned) in enumerate(best, start=1):
        day = next(d for d in revision.plan.days if d.day_index == k)
        index = next(n for n, e in enumerate(day.items) if e.key == ctx.addition.key)
        entry = day.items[index]
        after = day.items[index - 1].name if index > 0 else None
        before = day.items[index + 1].name if index + 1 < len(day.items) else None
        model = changes.diff_model(planned)
        new_base = next((b.new_name for b in planned.base_changes if b.day == k), None)
        added = planned.travel_minutes_added
        reasons: list[SuggestionReason] = []
        if len(best) > 1 and added == least:
            reasons.append(_reason("LEAST_TRAVEL"))
        if added < 0:
            reasons.append(_reason("LESS_TRAVEL", minutes=-added))
        elif added > 0:
            reasons.append(_reason("MORE_TRAVEL", minutes=added))
        if planned.removed:
            reasons.append(_reason("LEAVES_OUT", names=", ".join(i.name for i in planned.removed)))
        else:
            reasons.append(_reason("NOTHING_LEFT_OUT"))
        if planned.moved:
            reasons.append(_reason("VISITS_MOVE", count=len(planned.moved)))
        else:
            reasons.append(_reason("NO_DAY_CHANGES"))
        if new_base:
            reasons.append(_reason("NEW_BASE", day=k, town=new_base))
        suggestions.append(
            PlaceSuggestion(
                rank=rank,
                day=k,
                start_time=changes.clock(entry.start_minute),
                end_time=changes.clock(entry.end_minute),
                after_name=after,
                before_name=before,
                new_base_name=new_base,
                travel_minutes_added=added,
                estimated=bool(planned.estimated_legs),
                diff=model,
                reasons=reasons,
            )
        )
    log.info(
        "place_days_suggested",
        itinerary_id=str(itinerary_id),
        suggestions=len(suggestions),
        days=[s.day for s in suggestions],
        days_considered=len(days),
        load_ms=round((loaded - started) * 1000, 1),
        engine_ms=round((time.perf_counter() - loaded) * 1000, 1),
    )
    addition = ctx.addition
    shown_issues: list[SuggestionReason] = []
    if not suggestions:
        seen: set[str] = set()
        for i in issues:
            text = issue_text(i.code, i.params)
            if text not in seen:
                seen.add(text)
                shown_issues.append(SuggestionReason(code=i.code, text=text))
    return PlaceSuggestions(
        name=addition.name,
        duration_minutes=addition.duration_minutes,
        duration_source=addition.duration_source,
        suggestions=suggestions,
        days_considered=len(days),
        issues=shown_issues,
    )
