import uuid

from fastapi import APIRouter, Request, Response, status

from detour_api.deps import IfMatch, SessionDep
from detour_api.models.trips import Item, ItemCreate, ItemUpdate, Itinerary
from detour_api.repo import itineraries, stays
from detour_api.routers.responses import ERRORS

router = APIRouter(prefix="/v1", tags=["itineraries"])


@router.get(
    "/itineraries/{itinerary_id}",
    summary="An itinerary with its days and items.",
    responses=ERRORS,
)
def get_itinerary(request: Request, session: SessionDep, itinerary_id: uuid.UUID) -> Itinerary:
    with session.tx() as conn:
        plan = itineraries.require_itinerary(conn, session.person_id, itinerary_id)
        return stays.with_starts(conn, session.person_id, plan, request.app.state.travel_time)


@router.delete(
    "/itineraries/{itinerary_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an itinerary with its days, items and transfers.",
    responses=ERRORS,
)
def delete_itinerary(
    session: SessionDep, itinerary_id: uuid.UUID, if_match: IfMatch = None
) -> Response:
    with session.tx() as conn:
        itineraries.check_version(conn, session.person_id, if_match, itinerary_id=itinerary_id)
        itineraries.delete_itinerary(conn, session.person_id, itinerary_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/itineraries/{itinerary_id}/days/{day_index}/items",
    status_code=status.HTTP_201_CREATED,
    summary="Add a visit, meal or free-time block to a day (1-based).",
    responses=ERRORS,
)
def create_item(
    session: SessionDep,
    itinerary_id: uuid.UUID,
    day_index: int,
    body: ItemCreate,
    if_match: IfMatch = None,
) -> Item:
    with session.tx() as conn:
        itineraries.check_version(conn, session.person_id, if_match, itinerary_id=itinerary_id)
        return itineraries.create_item(conn, session.person_id, itinerary_id, day_index, body)


@router.get("/items/{item_id}", summary="One itinerary item.", responses=ERRORS)
def get_item(session: SessionDep, item_id: uuid.UUID) -> Item:
    with session.tx() as conn:
        return itineraries.require_item(conn, session.person_id, item_id)


@router.patch(
    "/items/{item_id}",
    summary="Change time, duration, lock, meal type, day or position of an item.",
    responses=ERRORS,
)
def update_item(
    session: SessionDep, item_id: uuid.UUID, body: ItemUpdate, if_match: IfMatch = None
) -> Item:
    with session.tx() as conn:
        itineraries.check_version(conn, session.person_id, if_match, item_id=item_id)
        return itineraries.update_item(conn, session.person_id, item_id, body)


@router.delete(
    "/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove an item from its day.",
    responses=ERRORS,
)
def delete_item(session: SessionDep, item_id: uuid.UUID, if_match: IfMatch = None) -> Response:
    with session.tx() as conn:
        itineraries.check_version(conn, session.person_id, if_match, item_id=item_id)
        itineraries.delete_item(conn, session.person_id, item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
