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
from detour_api.repo import people, trips
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


# The person of each phone, per engine, for at most a minute (ADR 034): a phone removed under Your
# devices is refused within that time even by another process; this process forgets at once.
_PERSON_TTL_SECONDS = 60.0
_persons: "weakref.WeakKeyDictionary[Engine, dict[uuid.UUID, tuple[people.Device, float]]]" = (
    weakref.WeakKeyDictionary()
)


def _cached_device(engine: Engine, device_id: uuid.UUID) -> people.Device | None:
    with _seen_lock:
        entry = _persons.get(engine, {}).get(device_id)
    if entry is None or time.monotonic() - entry[1] >= _PERSON_TTL_SECONDS:
        return None
    return entry[0]


def forget_devices(engine: Engine | None) -> None:
    """Drop what this process knows about phones' persons (after a join or a removal)."""
    if engine is None:
        return
    with _seen_lock:
        _persons.pop(engine, None)


def resolve_device(engine: Engine | None, device_id: uuid.UUID) -> people.Device:
    """The person a phone belongs to; a removed phone is refused with 401 ``device_removed``."""
    if engine is None:  # no database: nothing to resolve, every request fails on its first query
        return people.Device(person_id=device_id, revoked=False)
    device = _cached_device(engine, device_id)
    if device is None:
        with engine.begin() as conn:
            device = people.resolve_device(conn, device_id)
        with _seen_lock:
            persons = _persons.setdefault(engine, {})
            if len(persons) >= _SEEN_MAX:
                persons.clear()
            persons[device_id] = (device, time.monotonic())
    if device.revoked:
        raise ApiError(
            401,
            "device_removed",
            "this phone was removed from its owner's devices; it starts again as a new phone",
        )
    return device


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
    """The caller, and the means to talk to the database as it.

    ``installation_id`` is the **data owner**: the id of the caller's person (ADR 034), which is
    the id of the person's first phone, so every query that names an installation sees all of the
    person's trips from any of their phones. ``device_id`` is the phone that sent the request.
    """

    db: Database
    installation_id: uuid.UUID
    photon: PhotonClient
    device_id: uuid.UUID

    @contextmanager
    def tx(self) -> Iterator[Connection]:
        engine = self.db.engine
        known = engine is not None and _recently_seen(engine, self.device_id)
        with self.db.tx() as conn:
            if not known:
                trips.ensure_installation(conn, self.device_id)
            yield conn
        # The request's transaction has ended: its work is committed and nothing is locked.
        if not known and engine is not None:
            _mark_seen(engine, self.device_id)
            try:
                trips.touch_installation(engine, self.device_id)
            except SQLAlchemyError as exc:  # bookkeeping only: never fail the request for it
                log.warning("installation_touch_failed", error=type(exc).__name__)


def get_session(request: Request, installation_id: InstallationDep) -> Session:
    engine = request.app.state.engine
    device = resolve_device(engine, installation_id)
    return Session(
        db=Database(engine),
        installation_id=device.person_id,
        photon=request.app.state.photon,
        device_id=installation_id,
    )


SessionDep = Annotated[Session, Depends(get_session)]


def get_database(request: Request) -> Database:
    return Database(request.app.state.engine)


DatabaseDep = Annotated[Database, Depends(get_database)]
