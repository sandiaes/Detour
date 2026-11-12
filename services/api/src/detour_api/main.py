"""Application factory. Run with ``uvicorn detour_api.main:create_app --factory``."""

import re
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import httpx
import structlog
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy.exc import OperationalError

from detour_api import __version__
from detour_api.adapters.photon import PhotonClient
from detour_api.db import make_engine
from detour_api.errors import install_handlers
from detour_api.logging import configure_logging, get_logger
from detour_api.routers import (
    config,
    health,
    installations,
    itineraries,
    regions,
    search,
    trips,
    user_places,
)
from detour_api.settings import Settings, get_settings

_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def _operation_id(route: APIRoute) -> str:
    return route.name


def create_app(
    settings: Settings | None = None, *, photon_transport: httpx.BaseTransport | None = None
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    log = get_logger("detour.api")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        url = settings.sqlalchemy_url
        app.state.engine = make_engine(url) if url else None
        app.state.photon = PhotonClient(settings, app.state.engine, photon_transport)
        log.info(
            "startup",
            version=__version__,
            environment=settings.environment,
            database="configured" if url else "not_configured",
        )
        yield
        if app.state.engine is not None:
            app.state.engine.dispose()

    app = FastAPI(
        title="Detour API",
        version=__version__,
        summary="Backend for the Detour travel planner (Phase 2: data and search).",
        openapi_url="/v1/openapi.json",
        docs_url="/v1/docs",
        redoc_url=None,
        generate_unique_id_function=_operation_id,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = None
    app.state.photon = PhotonClient(settings, None)
    install_handlers(app)

    @app.exception_handler(OperationalError)
    async def _database_down(_: Request, __: OperationalError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"detail": "the database is unavailable", "code": "database_unavailable"},
        )

    @app.middleware("http")
    async def request_log(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming if _REQUEST_ID.match(incoming) else uuid.uuid4().hex
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            log.exception("request_failed", method=request.method, path=request.url.path)
            raise
        response.headers["X-Request-ID"] = request_id
        # Path only: query strings and headers can carry secrets and are never logged.
        log.info(
            "request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
        )
        return response

    app.include_router(health.router)
    app.include_router(config.router)
    app.include_router(installations.router)
    app.include_router(regions.router)
    app.include_router(search.router)
    app.include_router(trips.router)
    app.include_router(itineraries.router)
    app.include_router(user_places.router)
    return app
