from fastapi import APIRouter, Request, Response, status

from detour_api import __version__
from detour_api.db import check_database
from detour_api.deps import SettingsDep
from detour_api.schemas import DatabaseStatus, HealthResponse, ReadinessResponse

router = APIRouter(prefix="/v1/health", tags=["health"])


@router.get("", summary="Liveness: the process is up. Does not touch the database.")
def health(settings: SettingsDep) -> HealthResponse:
    return HealthResponse(status="ok", version=__version__, release=settings.release)


@router.head("", include_in_schema=False)
def health_head() -> Response:
    """HEAD for uptime monitors that can only send HEAD (docs/deployment.md, "Keeping it awake")."""
    return Response(status_code=status.HTTP_200_OK)


@router.get(
    "/ready",
    summary="Readiness: the database answers and the geo and app schemas exist.",
    responses={503: {"model": ReadinessResponse}},
)
def ready(request: Request, response: Response) -> ReadinessResponse:
    check = check_database(request.app.state.engine)
    ok = check.status == "ok" and set(check.schemas) == {"app", "geo"}
    body = ReadinessResponse(
        status="ok" if ok else "unavailable",
        database=DatabaseStatus(status=check.status, schemas=check.schemas, postgis=check.postgis),
    )
    if not ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return body


@router.head("/ready", include_in_schema=False)
def ready_head(request: Request, response: Response) -> Response:
    """HEAD for uptime monitors: same database check and status as GET, no body."""
    ready(request, response)
    return Response(status_code=response.status_code or status.HTTP_200_OK)
