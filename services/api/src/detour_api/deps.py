"""Shared request dependencies."""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import Connection, Engine

from detour_api.adapters.photon import PhotonClient
from detour_api.errors import ApiError
from detour_api.repo import trips
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


class Database:
    """Transactions on the application's engine. The commit happens before the response is sent."""

    def __init__(self, engine: Engine | None) -> None:
        self._engine = engine

    @contextmanager
    def tx(self) -> Iterator[Connection]:
        if self._engine is None:
            raise ApiError(503, "database_unavailable", "the database is not configured")
        with self._engine.begin() as conn:
            yield conn


@dataclass(frozen=True)
class Session:
    """The caller: an installation, and the means to talk to the database as it."""

    db: Database
    installation_id: uuid.UUID
    photon: PhotonClient

    @contextmanager
    def tx(self) -> Iterator[Connection]:
        with self.db.tx() as conn:
            trips.ensure_installation(conn, self.installation_id)
            yield conn


def get_session(request: Request, installation_id: InstallationDep) -> Session:
    return Session(
        db=Database(request.app.state.engine),
        installation_id=installation_id,
        photon=request.app.state.photon,
    )


SessionDep = Annotated[Session, Depends(get_session)]


def get_database(request: Request) -> Database:
    return Database(request.app.state.engine)


DatabaseDep = Annotated[Database, Depends(get_database)]
