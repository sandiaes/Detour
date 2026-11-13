import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request, Response, status

from detour_api.deps import SessionDep
from detour_api.errors import ApiError, invalid
from detour_api.models.common import PlanningErrorBody
from detour_api.models.trips import (
    ArchiveInfo,
    GenerationResult,
    Itinerary,
    ItinerarySummary,
    Trip,
    TripCreate,
    TripUpdate,
    TripVisit,
    TripVisitUpdate,
)
from detour_api.planner.service import generate_for_trip
from detour_api.repo import geo, itineraries, trips
from detour_api.routers.responses import AUTH, ERRORS

router = APIRouter(prefix="/v1/trips", tags=["trips"])


@router.post("", status_code=status.HTTP_201_CREATED, summary="Create a trip.", responses=ERRORS)
def create_trip(session: SessionDep, body: TripCreate) -> Trip:
    with session.tx() as conn:
        dest = geo.resolve_destination(conn, body.destination_kind, body.destination_ref)
        if dest is None:
            raise invalid("destination_not_found", "no such city or area in the imported data")
        if dest.region_id is None or dest.region_status != "available":
            raise ApiError(
                409,
                "region_not_available",
                "this destination is outside the regions that are available for planning",
            )
        if body.destination_kind == "area" and not geo.area_planning_allowed(dest):
            raise invalid("area_single_city_only", geo.SINGLE_CITY_MESSAGE)
        return trips.create_trip(
            conn,
            session.installation_id,
            body,
            destination_name=dest.name,
            lat=dest.lat,
            lon=dest.lon,
        )


@router.get("", summary="The caller's trips, newest first.", responses=AUTH)
def list_trips(
    session: SessionDep,
    status_filter: Annotated[Literal["active", "past"] | None, Query(alias="status")] = None,
) -> list[Trip]:
    with session.tx() as conn:
        trips.archive_due_trips(conn, session.installation_id)  # ADR 006: after the last day
        return trips.list_trips(conn, session.installation_id, status_filter)


@router.get("/{trip_id}", summary="One trip.", responses=ERRORS)
def get_trip(session: SessionDep, trip_id: uuid.UUID) -> Trip:
    with session.tx() as conn:
        trips.archive_due_trips(conn, session.installation_id)  # ADR 006: after the last day
        return trips.require_trip(conn, session.installation_id, trip_id)


@router.patch(
    "/{trip_id}",
    summary="Change a trip. Only the fields sent are changed; null clears the optional ones.",
    responses=ERRORS,
)
def update_trip(session: SessionDep, trip_id: uuid.UUID, body: TripUpdate) -> Trip:
    with session.tx() as conn:
        return trips.update_trip(conn, session.installation_id, trip_id, body)


@router.delete(
    "/{trip_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a trip with its itineraries, days, items, transfers and archive rows.",
    responses=ERRORS,
)
def delete_trip(session: SessionDep, trip_id: uuid.UUID) -> Response:
    with session.tx() as conn:
        trips.delete_trip(conn, session.installation_id, trip_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{trip_id}/archive",
    summary="Make the trip a past trip (ADR 006): keep a snapshot of its visits, delete the plans.",
    responses=ERRORS,
)
def archive_trip(session: SessionDep, trip_id: uuid.UUID) -> Trip:
    with session.tx() as conn:
        return trips.archive_trip(conn, session.installation_id, trip_id)


@router.get(
    "/{trip_id}/archive",
    summary="What a past trip keeps and how much room it takes (ADR 006).",
    responses=ERRORS,
)
def get_trip_archive(session: SessionDep, trip_id: uuid.UUID) -> ArchiveInfo:
    with session.tx() as conn:
        return trips.get_archive_info(conn, session.installation_id, trip_id)


@router.get("/{trip_id}/visits", summary="The archived visits of a past trip.", responses=ERRORS)
def list_trip_visits(session: SessionDep, trip_id: uuid.UUID) -> list[TripVisit]:
    with session.tx() as conn:
        return trips.list_visits(conn, session.installation_id, trip_id)


@router.patch(
    "/{trip_id}/visits/{visit_id}",
    summary="Confirm or clear one archived visit (the app cannot know what was really visited).",
    responses=ERRORS,
)
def update_trip_visit(
    session: SessionDep, trip_id: uuid.UUID, visit_id: uuid.UUID, body: TripVisitUpdate
) -> TripVisit:
    with session.tx() as conn:
        return trips.set_visit_confirmed(
            conn, session.installation_id, trip_id, visit_id, body.confirmed
        )


@router.post(
    "/{trip_id}/itineraries",
    status_code=status.HTTP_201_CREATED,
    summary="Create an empty itinerary (one day per trip day) to fill by hand.",
    responses=ERRORS,
)
def create_itinerary(session: SessionDep, trip_id: uuid.UUID) -> Itinerary:
    with session.tx() as conn:
        return itineraries.create_manual(conn, session.installation_id, trip_id)


@router.get("/{trip_id}/itineraries", summary="The trip's itineraries.", responses=ERRORS)
def list_itineraries(session: SessionDep, trip_id: uuid.UUID) -> list[ItinerarySummary]:
    with session.tx() as conn:
        return itineraries.list_for_trip(conn, session.installation_id, trip_id)


@router.post(
    "/{trip_id}/itineraries/generate",
    status_code=status.HTTP_201_CREATED,
    summary="Plan the trip: two meaningfully different itineraries of attractions, or one with "
    "the reason (Phase 4: city destinations, no meals). Replaces earlier unselected proposals.",
    responses={**ERRORS, 422: {"model": PlanningErrorBody}},
)
def generate_itineraries(
    session: SessionDep, request: Request, trip_id: uuid.UUID
) -> GenerationResult:
    return generate_for_trip(
        session, trip_id, request.app.state.travel_time, request.app.state.settings
    )
