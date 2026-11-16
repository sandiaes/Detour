import uuid

import structlog
from fastapi import APIRouter, Request, status

from detour_api.deps import DatabaseDep, SessionDep, SettingsDep
from detour_api.errors import ApiError
from detour_api.models.search import (
    AttributionEntry,
    ImportJob,
    ImportRequest,
    RegionCatalog,
    RegionInfo,
    RegionRemoval,
)
from detour_api.repo import geo, import_jobs, regions
from detour_api.routers.responses import ERRORS
from detour_api.settings import Settings

log = structlog.get_logger("detour.regions")

router = APIRouter(prefix="/v1", tags=["regions"])


@router.get("/regions", summary="Import regions, their status and the data version in use.")
def list_regions(db: DatabaseDep) -> list[RegionInfo]:
    with db.tx() as conn:
        return geo.list_regions(conn)


def _owner_only(settings: Settings, person_id: uuid.UUID) -> None:
    """Removing a region changes data every installation shares, so only the owner's installations
    (``DETOUR_OWNER_INSTALLATION_IDS``) may do it. With none configured nobody may (ADR 033)."""
    if person_id not in settings.owner_installations:
        raise ApiError(403, "not_owner", "only the owner of this server can change its regions")


@router.get(
    "/regions/catalog",
    summary="The regions that can be imported, their state and the latest import started from the "
    "app (ADR 033). Anyone may read it; only the owner can_manage.",
    responses=ERRORS,
)
def region_catalog(session: SessionDep, settings: SettingsDep, request: Request) -> RegionCatalog:
    with session.tx() as conn:
        return import_jobs.catalog(
            conn,
            settings,
            can_manage=session.person_id in settings.owner_installations,
            import_enabled=request.app.state.github.enabled,
        )


@router.post(
    "/regions/{region_id}/import",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start importing a region from the catalog: asks GitHub to run the 'Import region' "
    "workflow, which reports its progress (ADR 033). Owner only. 503 without a GitHub token.",
    responses=ERRORS,
)
def import_region(
    session: SessionDep,
    settings: SettingsDep,
    request: Request,
    region_id: str,
    body: ImportRequest | None = None,
) -> ImportJob:
    _owner_only(settings, session.person_id)
    github = request.app.state.github
    if not github.enabled:
        raise ApiError(503, "import_unavailable", "this server cannot start imports")
    with session.tx() as conn:
        job_id = import_jobs.start_job(conn, settings, region_id, session.person_id)
    # The job exists and is committed before GitHub is asked: the workflow updates it by id.
    outcome = github.dispatch_import(region_id, job_id, body.gazetteer if body else True)
    failed = {
        "disabled": "this server cannot start imports",
        "unavailable": "GitHub could not be reached",
        "budget_exhausted": "too many imports were started today",
        "refused": "GitHub refused the request: check the token and the workflow",
    }.get(outcome.state)
    with session.tx() as conn:
        import_jobs.finish_request(
            conn, job_id, ok=failed is None, message=failed, run_url=outcome.run_url
        )
        job = import_jobs.latest_jobs(conn, settings)[region_id]
    if failed is not None:
        raise ApiError(502, "import_not_started", failed)
    return job


@router.get(
    "/regions/{region_id}/removal-preview",
    summary="What removing a region's imported data takes away and keeps (ADR 033). Owner only.",
    responses=ERRORS,
)
def removal_preview(session: SessionDep, settings: SettingsDep, region_id: str) -> RegionRemoval:
    _owner_only(settings, session.person_id)
    with session.tx() as conn:
        return regions.preview(conn, session.person_id, region_id)


@router.delete(
    "/regions/{region_id}",
    summary="Remove a region's imported data, keeping every place a trip still names (ADR 033). "
    "Owner only; the region can be imported again.",
    responses=ERRORS,
)
def remove_region(session: SessionDep, settings: SettingsDep, region_id: str) -> RegionRemoval:
    _owner_only(settings, session.person_id)
    with session.tx() as conn:
        result = regions.remove(conn, session.person_id, region_id)
    # After the commit, like the importer: rewrite the tables so the files and the size shrink.
    if result.places_removed >= regions.FULL_VACUUM_THRESHOLD:
        regions.vacuum_full(session.db.engine)
    return result


@router.get(
    "/attributions",
    summary="Credits the app must show for the data in use (OpenStreetMap, GeoNames, map tiles).",
)
def list_attributions(db: DatabaseDep, settings: SettingsDep) -> list[AttributionEntry]:
    with db.tx() as conn:
        entries = geo.licences(conn)
    entries += [
        AttributionEntry(
            name="Map tiles",
            text=a.text,
            url=a.url,
            licence=None,
            applies_to="The map",
        )
        for a in settings.map_attribution
    ]
    return entries
