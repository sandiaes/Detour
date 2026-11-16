"""Change sets: preview adding or removing a place, then apply or discard (Phase 7, ADR 018)."""

import uuid

from fastapi import APIRouter, Request, status

from detour_api.deps import SessionDep
from detour_api.models.changes import (
    ChangeSet,
    ChangeSetApplied,
    ChangeSetCreate,
    ItineraryVersion,
    OptimizeRequest,
    PlaceSuggestionRequest,
    PlaceSuggestions,
    StopsEdit,
)
from detour_api.models.common import PlanningErrorBody
from detour_api.planner import change_service, optimize_service, stop_service
from detour_api.repo import changes, stays
from detour_api.routers.responses import ERRORS

router = APIRouter(prefix="/v1", tags=["changes"])


@router.post(
    "/itineraries/{itinerary_id}/change-sets",
    status_code=status.HTTP_201_CREATED,
    summary="Preview adding a place (it becomes a visit every recalculation keeps) or removing a "
    "visit. Returns the diff; nothing changes until the change set is applied.",
    responses={**ERRORS, 422: {"model": PlanningErrorBody}},
)
def preview_change(
    session: SessionDep, request: Request, itinerary_id: uuid.UUID, body: ChangeSetCreate
) -> ChangeSet:
    return change_service.preview(
        session,
        itinerary_id,
        body,
        request.app.state.travel_time,
        request.app.state.settings,
    )


@router.post(
    "/itineraries/{itinerary_id}/optimize",
    status_code=status.HTTP_201_CREATED,
    summary="Preview a shorter order of the stops of a plan of any kind (ADR 029): within each day "
    "or across all days. Locked stops and the ones named in fixed_item_ids stay; restaurants and "
    "cafés keep their day. Returns the diff and the saving; nothing changes until it is applied. "
    "409 no_better_order when the plan is already as short as the search can make it.",
    responses={**ERRORS, 422: {"model": PlanningErrorBody}},
)
def preview_optimize(
    session: SessionDep, request: Request, itinerary_id: uuid.UUID, body: OptimizeRequest
) -> ChangeSet:
    return optimize_service.preview_optimize(
        session,
        itinerary_id,
        body,
        request.app.state.travel_time,
        request.app.state.settings,
    )


@router.post(
    "/itineraries/{itinerary_id}/optimize/undo",
    status_code=status.HTTP_201_CREATED,
    summary="Preview restoring the plan as it was before the latest applied Optimize, while "
    "nothing else changed it. 409 nothing_to_undo otherwise.",
    responses=ERRORS,
)
def preview_optimize_undo(session: SessionDep, itinerary_id: uuid.UUID) -> ChangeSet:
    return optimize_service.preview_undo(session, itinerary_id)


@router.post(
    "/itineraries/{itinerary_id}/place-suggestions",
    summary="Where a place fits in a planned itinerary: up to three days, best first, each with "
    "the time it would get, the travel it adds and the visits it moves or leaves out, from the "
    "same recalculation as the add_place preview. Nothing is stored.",
    responses={**ERRORS, 422: {"model": PlanningErrorBody}},
)
def place_suggestions(
    session: SessionDep, request: Request, itinerary_id: uuid.UUID, body: PlaceSuggestionRequest
) -> PlaceSuggestions:
    return change_service.suggest_places(
        session,
        itinerary_id,
        body,
        request.app.state.travel_time,
        request.app.state.settings,
    )


@router.get("/change-sets/{change_set_id}", summary="One change set.", responses=ERRORS)
def get_change_set(session: SessionDep, change_set_id: uuid.UUID) -> ChangeSet:
    with session.tx() as conn:
        return changes.require(conn, session.installation_id, change_set_id)


@router.post(
    "/change-sets/{change_set_id}/apply",
    summary="Apply a previewed change: the itinerary gets a new version, exactly as previewed; "
    "the previous version is kept. 409 change_set_stale if the plan changed since the preview.",
    responses=ERRORS,
)
def apply_change_set(
    request: Request, session: SessionDep, change_set_id: uuid.UUID
) -> ChangeSetApplied:
    applied = change_service.apply(session, change_set_id)
    # The plan comes back whole and the app stores it as the plan, so it carries each day's
    # morning leg from its stay like a plan that is read (ADR 030); otherwise the line and the
    # "Walk from" row vanish after Optimize, its undo and every other change until it is read again.
    with session.tx() as conn:
        stays.with_starts(
            conn, session.installation_id, applied.itinerary, request.app.state.travel_time
        )
    return applied


@router.post(
    "/change-sets/{change_set_id}/discard",
    summary="Discard a previewed change. The itinerary is not touched.",
    responses=ERRORS,
)
def discard_change_set(session: SessionDep, change_set_id: uuid.UUID) -> ChangeSet:
    return change_service.discard(session, change_set_id)


@router.get(
    "/itineraries/{itinerary_id}/versions",
    summary="Earlier versions of an itinerary, newest first, and what replaced each.",
    responses=ERRORS,
)
def list_versions(session: SessionDep, itinerary_id: uuid.UUID) -> list[ItineraryVersion]:
    with session.tx() as conn:
        return changes.list_versions(conn, session.installation_id, itinerary_id)


@router.post(
    "/trips/{trip_id}/stops/preview",
    status_code=status.HTTP_201_CREATED,
    summary="Preview new stops for a multi-city trip (ADR 024): the active plan repaired, with "
    "what each stop keeps, what is filled in and what leaves with a removed day. Apply or discard "
    "it like any change set.",
    responses={**ERRORS, 422: {"model": PlanningErrorBody}},
)
def preview_stops(
    session: SessionDep, request: Request, trip_id: uuid.UUID, body: StopsEdit
) -> ChangeSet:
    return stop_service.preview_stops(
        session,
        trip_id,
        body.stops,
        request.app.state.travel_time,
        request.app.state.settings,
    )
