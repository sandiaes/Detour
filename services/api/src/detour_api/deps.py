"""Shared request dependencies."""

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from detour_api.settings import Settings
from detour_api.tokens import verify_token

_bearer = HTTPBearer(auto_error=False, description="Token from POST /v1/installations")


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]


def require_installation(
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> uuid.UUID:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid installation token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    installation_id = verify_token(settings.token_secret_bytes, credentials.credentials)
    if installation_id is None:
        raise unauthorized
    return installation_id


InstallationDep = Annotated[uuid.UUID, Depends(require_installation)]
