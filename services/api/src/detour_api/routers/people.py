"""People and their devices (ADR 034, step 1): add a phone with a one-time code, recover with the
recovery code, list and remove phones."""

import uuid

import structlog
from fastapi import APIRouter, Request, Response, status
from sqlalchemy import Connection

from detour_api.deps import Session, SessionDep, SettingsDep, forget_devices
from detour_api.models.common import ErrorBody
from detour_api.models.people import (
    DeviceInfo,
    InviteRequest,
    JoinRequest,
    JoinResult,
    LinkCode,
    LinkedPerson,
    PersonInfo,
    PersonUpdate,
    RecoveryCode,
)
from detour_api.repo import people
from detour_api.routers.responses import ERRORS, Responses

log = structlog.get_logger("detour.people")

router = APIRouter(prefix="/v1", tags=["people"])

JOIN_ERRORS: Responses = {**ERRORS, 400: {"model": ErrorBody}}


def _person(session: Session, conn: Connection) -> PersonInfo:
    row = people.get_person(conn, session.person_id)
    return PersonInfo(
        person_id=row.id,
        display_name=row.display_name,
        people=[
            LinkedPerson(person_id=p.id, name=p.display_name, linked_at=p.linked_at)
            for p in row.people
        ],
        device_id=session.device_id,
        devices=[
            DeviceInfo(
                id=d.id,
                added_at=d.joined_at or d.added_at,
                last_seen_at=d.last_seen_at,
                this_device=d.id == session.device_id,
            )
            for d in row.devices
        ],
        recovery_code_created_at=row.recovery_created_at,
    )


@router.get(
    "/me", summary="You: your phones and whether you have a recovery code.", responses=ERRORS
)
def get_me(session: SessionDep) -> PersonInfo:
    with session.tx() as conn:
        return _person(session, conn)


@router.post(
    "/me/link-codes",
    status_code=status.HTTP_201_CREATED,
    summary="A one-time code (10 minutes) to type on another phone to make it one of yours. "
    "An earlier unused code stops working.",
    responses=ERRORS,
)
def create_link_code(session: SessionDep, settings: SettingsDep, response: Response) -> LinkCode:
    with session.tx() as conn:
        code, expires_at = people.create_link_code(
            conn, settings.token_secret_bytes, session.person_id, session.device_id
        )
    response.headers["Cache-Control"] = "no-store"
    return LinkCode(code=people.format_code(code), expires_at=expires_at)


@router.post(
    "/me/recovery-code",
    status_code=status.HTTP_201_CREATED,
    summary="A new recovery code, shown once. The earlier one stops working.",
    responses=ERRORS,
)
def create_recovery_code(
    session: SessionDep, settings: SettingsDep, response: Response
) -> RecoveryCode:
    with session.tx() as conn:
        code, created_at = people.create_recovery_code(
            conn, settings.token_secret_bytes, session.person_id
        )
    response.headers["Cache-Control"] = "no-store"
    return RecoveryCode(code=people.format_code(code), created_at=created_at)


@router.delete(
    "/me/devices/{device_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Sign out one of your other phones; its token is refused from then on.",
    responses=ERRORS,
)
def remove_device(device_id: uuid.UUID, session: SessionDep, request: Request) -> Response:
    with session.tx() as conn:
        people.remove_device(conn, session.person_id, session.device_id, device_id)
    forget_devices(request.app.state.engine)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/installations/join",
    summary="Make this phone one of yours with a code from another phone, or with your "
    "recovery code (which signs out your other phones). This phone's own trips come along. "
    "400 code_invalid; 409 has_other_devices or limit_reached.",
    responses=JOIN_ERRORS,
)
def join(
    body: JoinRequest, session: SessionDep, settings: SettingsDep, request: Request
) -> JoinResult:
    with session.tx() as conn:
        result = people.join(conn, settings.token_secret_bytes, session.device_id, body.code)
    forget_devices(request.app.state.engine)
    log.info("device_joined", recovered=result.recovered, moved_trips=result.moved_trips)
    joined = Session(
        db=session.db,
        person_id=result.person_id,
        photon=session.photon,
        device_id=session.device_id,
    )
    with joined.tx() as conn:
        person = _person(joined, conn)
    return JoinResult(person=person, recovered=result.recovered, moved_trips=result.moved_trips)


@router.patch("/me", summary="Change your name as others see it.", responses=ERRORS)
def update_me(body: PersonUpdate, session: SessionDep) -> PersonInfo:
    with session.tx() as conn:
        people.set_display_name(conn, session.person_id, body.display_name)
        return _person(session, conn)


@router.post(
    "/me/invite-codes",
    status_code=status.HTTP_201_CREATED,
    summary="A one-time code (10 minutes) for someone else to type under People, to link the two "
    "of you so you can share trips. An earlier unused invite code stops working.",
    responses=ERRORS,
)
def create_invite_code(session: SessionDep, settings: SettingsDep, response: Response) -> LinkCode:
    with session.tx() as conn:
        code, expires_at = people.create_link_code(
            conn, settings.token_secret_bytes, session.person_id, session.device_id, "invite"
        )
    response.headers["Cache-Control"] = "no-store"
    return LinkCode(code=people.format_code(code), expires_at=expires_at)


@router.post(
    "/people/link",
    summary="Link yourself to the person who showed this invite code. 400 code_invalid; 409 "
    "already_linked, own_invite or limit_reached.",
    responses=JOIN_ERRORS,
)
def link_person(body: InviteRequest, session: SessionDep, settings: SettingsDep) -> PersonInfo:
    with session.tx() as conn:
        people.link_people(
            conn, settings.token_secret_bytes, session.person_id, session.device_id, body.code
        )
        return _person(session, conn)


@router.delete(
    "/people/{person_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unlink a person. Trips already shared stay shared; leave them or stop sharing them.",
    responses=ERRORS,
)
def unlink_person(person_id: uuid.UUID, session: SessionDep) -> Response:
    with session.tx() as conn:
        people.unlink(conn, session.person_id, person_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
