import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response, status

from detour_api.deps import SessionDep
from detour_api.models.trips import UserPlace, UserPlaceCreate, UserPlaceUpdate
from detour_api.repo import user_places
from detour_api.routers.responses import AUTH, ERRORS

router = APIRouter(prefix="/v1/user-places", tags=["user places"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Save a place that is not in the imported data (a pin or an external search result).",
    responses=ERRORS,
)
def create_user_place(session: SessionDep, body: UserPlaceCreate) -> UserPlace:
    with session.tx() as conn:
        return user_places.create(conn, session.person_id, body)


@router.get("", summary="The caller's own places.", responses=AUTH)
def list_user_places(
    session: SessionDep,
    kind: Annotated[Literal["city", "location", "restaurant", "cafe"] | None, Query()] = None,
) -> list[UserPlace]:
    with session.tx() as conn:
        return user_places.list_all(conn, session.person_id, kind)


@router.get("/{place_id}", summary="One of the caller's places.", responses=ERRORS)
def get_user_place(session: SessionDep, place_id: uuid.UUID) -> UserPlace:
    with session.tx() as conn:
        return user_places.require(conn, session.person_id, place_id)


@router.patch("/{place_id}", summary="Rename, move or re-describe a place.", responses=ERRORS)
def update_user_place(session: SessionDep, place_id: uuid.UUID, body: UserPlaceUpdate) -> UserPlace:
    with session.tx() as conn:
        return user_places.update(conn, session.person_id, place_id, body)


@router.delete(
    "/{place_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a place that no itinerary item uses.",
    responses=ERRORS,
)
def delete_user_place(session: SessionDep, place_id: uuid.UUID) -> Response:
    with session.tx() as conn:
        user_places.delete(conn, session.person_id, place_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
