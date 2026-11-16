from fastapi import APIRouter, Request, Response, status
from sqlalchemy.exc import SQLAlchemyError

from detour_api.deps import InstallationDep, SettingsDep, resolve_device
from detour_api.schemas import ErrorResponse, InstallationInfo, InstallationRegistration
from detour_api.tokens import issue_token

router = APIRouter(prefix="/v1/installations", tags=["installations"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Register an anonymous installation and receive its bearer token.",
)
def register_installation(settings: SettingsDep, response: Response) -> InstallationRegistration:
    installation_id, token = issue_token(settings.token_secret_bytes)
    response.headers["Cache-Control"] = "no-store"
    return InstallationRegistration(installation_id=installation_id, token=token)


@router.get(
    "/me",
    summary="Token check: returns the installation the bearer token belongs to and its person "
    "(null while the database cannot be reached). 401 device_removed for a removed phone.",
    responses={401: {"model": ErrorResponse}},
)
def current_installation(installation_id: InstallationDep, request: Request) -> InstallationInfo:
    engine = request.app.state.engine
    person_id = None
    if engine is not None:
        try:
            person_id = resolve_device(engine, installation_id).person_id
        except SQLAlchemyError:  # a paused database must not stop the app from connecting
            person_id = None
    return InstallationInfo(installation_id=installation_id, person_id=person_id)
