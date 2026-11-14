"""Plan generation for a trip: read, plan, write, with per-stage timings in the logs (KPI source).

1. one transaction: the trip, its checks and the candidates (repo/planning.py)
2. no transaction: the engine, which may wait on the routing provider (bounded)
3. one transaction: the itineraries, days, items and transfers
"""

import time
import uuid

import structlog

from detour_api.deps import Session
from detour_api.errors import ApiError
from detour_api.models.trips import GenerationResult
from detour_api.planner import engine
from detour_api.planner.config import DEFAULT_CONFIG, PlannerConfig
from detour_api.planner.reasons import issue_text
from detour_api.planner.sequencer import HeuristicSequencer
from detour_api.planner.travel import ServiceTravelSource
from detour_api.planner.types import PlanInvalid, PlanningImpossible
from detour_api.repo import planning
from detour_api.settings import Settings
from detour_api.travel.service import TravelTimeService

log = structlog.get_logger("detour.planner")


def generate_for_trip(
    session: Session,
    trip_id: uuid.UUID,
    travel: TravelTimeService,
    settings: Settings,
    config: PlannerConfig = DEFAULT_CONFIG,
) -> GenerationResult:
    started = time.perf_counter()
    with session.tx() as conn:
        context = planning.load_context(conn, session.installation_id, trip_id, config)
    loaded = time.perf_counter()

    sequencer = HeuristicSequencer()
    source = ServiceTravelSource(travel, max_seconds=settings.planner_provider_max_seconds)
    try:
        generation = engine.generate(
            context.request,
            context.candidates,
            source,
            config=config,
            sequencer=sequencer,
            use_provider=settings.planner_use_provider,
        )
    except PlanningImpossible as exc:
        params = [{"code": i.code, "text": issue_text(i.code, i.params)} for i in exc.issues]
        log.info("plan_impossible", trip_id=str(trip_id), issues=[i.code for i in exc.issues])
        raise ApiError(
            422,
            "planning_impossible",
            " ".join(p["text"] for p in params),
            extra={"issues": params},
        ) from exc
    except PlanInvalid as exc:
        # A bug: never shown as an itinerary.
        log.error("plan_invalid", trip_id=str(trip_id), profile=exc.profile, violations=str(exc))
        raise ApiError(500, "plan_invalid", "the planner produced an invalid plan") from exc
    planned = time.perf_counter()

    with session.tx() as conn:
        result = planning.save_generation(
            conn,
            session.installation_id,
            context,
            generation,
            sequencer.name,
            config.max_jaccard_num * 1000 // config.max_jaccard_den,
        )
    saved = time.perf_counter()
    log.info(
        "plan_generated",
        trip_id=str(trip_id),
        days=context.request.days,
        kind=context.request.kind,
        candidates=len(context.candidates),
        plans=len(generation.plans),
        distinct=generation.distinct,
        jaccard_permille=generation.jaccard_permille,
        visits=[p.stats.visits for p in generation.plans],
        meals=[p.stats.meals for p in generation.plans],
        routed_transfers=sum(p.stats.routed_transfers for p in generation.plans),
        estimated_transfers=sum(p.stats.estimated_transfers for p in generation.plans),
        load_ms=round((loaded - started) * 1000, 1),
        engine_ms=round((planned - loaded) * 1000, 1),
        save_ms=round((saved - planned) * 1000, 1),
        total_ms=round((saved - started) * 1000, 1),
    )
    return result
