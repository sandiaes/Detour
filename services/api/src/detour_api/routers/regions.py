import uuid

import structlog
from fastapi import APIRouter

from detour_api.deps import DatabaseDep, SessionDep, SettingsDep
from detour_api.errors import ApiError
from detour_api.models.search import AttributionEntry, RegionInfo, RegionRemoval
from detour_api.repo import geo, regions
from detour_api.routers.responses import ERRORS
from detour_api.settings import Settings

log = structlog.get_logger("detour.regions")

router = APIRouter(prefix="/v1", tags=["regions"])


@router.get("/regions", summary="Import regions, their status and the data version in use.")
def list_regions(db: DatabaseDep) -> list[RegionInfo]:
    with db.tx() as conn:
        return geo.list_regions(conn)


def _owner_only(settings: Settings, installation_id: uuid.UUID) -> None:
    """Removing a region changes data every installation shares, so only the owner's installations
    (``DETOUR_OWNER_INSTALLATION_IDS``) may do it. With none configured nobody may (ADR 033)."""
    if installation_id not in settings.owner_installations:
        raise ApiError(403, "not_owner", "only the owner of this server can change its regions")


@router.get(
    "/regions/{region_id}/removal-preview",
    summary="What removing a region's imported data takes away and keeps (ADR 033). Owner only.",
    responses=ERRORS,
)
def removal_preview(session: SessionDep, settings: SettingsDep, region_id: str) -> RegionRemoval:
    _owner_only(settings, session.installation_id)
    with session.tx() as conn:
        return regions.preview(conn, session.installation_id, region_id)


@router.delete(
    "/regions/{region_id}",
    summary="Remove a region's imported data, keeping every place a trip still names (ADR 033). "
    "Owner only; the region can be imported again.",
    responses=ERRORS,
)
def remove_region(session: SessionDep, settings: SettingsDep, region_id: str) -> RegionRemoval:
    _owner_only(settings, session.installation_id)
    with session.tx() as conn:
        result = regions.remove(conn, session.installation_id, region_id)
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
