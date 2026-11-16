"""Trip export and import as a file (ADR 028). The phone adds documents and the zip."""

import uuid

from fastapi import APIRouter, status

from detour_api.deps import SessionDep
from detour_api.models.exchange import ImportResult, TripFile
from detour_api.repo import exchange, trips
from detour_api.routers.responses import AUTH, ERRORS

# Declared before the trips router so that /export is not read as a trip identifier.
router = APIRouter(prefix="/v1/trips", tags=["exchange"])


@router.get(
    "/export",
    summary="Every trip of the caller in the trip-file shape (ADR 028): a backup.",
    responses=AUTH,
)
def export_all(session: SessionDep) -> TripFile:
    with session.tx() as conn:
        trips.archive_due_trips(conn, session.person_id)
        found = trips.list_trips(conn, session.person_id)
        # Oldest first, so an import keeps the order the trips were made in.
        return exchange.export_file([exchange.export_trip(conn, t) for t in reversed(found)])


@router.get(
    "/{trip_id}/export",
    summary="One trip in the trip-file shape (ADR 028): the chosen plan, or a past trip's record.",
    responses=ERRORS,
)
def export_one(session: SessionDep, trip_id: uuid.UUID) -> TripFile:
    with session.tx() as conn:
        trips.archive_due_trips(conn, session.person_id)
        trip = trips.require_trip(conn, session.person_id, trip_id)
        return exchange.export_file([exchange.export_trip(conn, trip)])


@router.post(
    "/import",
    status_code=status.HTTP_201_CREATED,
    summary="Add the trips of a trip file as new trips (ADR 028). Never merges or overwrites; "
    "all or nothing.",
    responses=ERRORS,
)
def import_trips(session: SessionDep, body: TripFile) -> ImportResult:
    with session.tx() as conn:
        return exchange.import_file(conn, session.person_id, body)
