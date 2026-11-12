from fastapi import APIRouter, Response, status

from detour_api.deps import InstallationDep, SettingsDep
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
    summary="Token check: returns the installation the bearer token belongs to.",
    responses={401: {"model": ErrorResponse}},
)
def current_installation(installation_id: InstallationDep) -> InstallationInfo:
    return InstallationInfo(installation_id=installation_id)
