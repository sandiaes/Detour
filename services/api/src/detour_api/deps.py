"""Shared request dependencies."""

import threading
import time
import uuid
import weakref
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Annotated

import structlog
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

from detour_api.adapters.photon import PhotonClient
from detour_api.errors import ApiError
from detour_api.repo import trips
from detour_api.settings import Settings
from detour_api.tokens import verify_token

log = structlog.get_logger("detour.deps")

# Installations this process has already created or touched, per engine, and when. A request of a
# known installation does no installation write at all; the row's "last seen" is refreshed at most
# once an hour, in a short transaction of its own (repo/trips.py).
_SEEN_TTL_SECONDS = 3600.0
_SEEN_MAX = 10_000
_seen: "weakref.WeakKeyDictionary[Engine, dict[uuid.UUID, float]]" = weakref.WeakKeyDictionary()
_seen_lock = threading.Lock()


def _recently_seen(engine: Engine, installation_id: uuid.UUID) -> bool:
    with _seen_lock:
        at = _seen.get(engine, {}).get(installation_id)
    return at is not None and time.monotonic() - at < _SEEN_TTL_SECONDS


def _mark_seen(engine: Engine, installation_id: uuid.UUID) -> None:
    with _seen_lock:
        seen = _seen.setdefault(engine, {})
        if len(seen) >= _SEEN_MAX:
            seen.clear()
        seen[installation_id] = time.monotonic()


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

    @property
    def engine(self) -> Engine | None:
        return self._engine

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
        engine = self.db.engine
        known = engine is not None and _recently_seen(engine, self.installation_id)
        with self.db.tx() as conn:
            if not known:
                trips.ensure_installation(conn, self.installation_id)
            yield conn
        # The request's transaction has ended: its work is committed and nothing is locked.
        if not known and engine is not None:
            _mark_seen(engine, self.installation_id)
            try:
                trips.touch_installation(engine, self.installation_id)
            except SQLAlchemyError as exc:  # bookkeeping only: never fail the request for it
                log.warning("installation_touch_failed", error=type(exc).__name__)


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
