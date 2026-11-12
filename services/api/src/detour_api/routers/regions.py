from fastapi import APIRouter

from detour_api.deps import DatabaseDep, SettingsDep
from detour_api.models.search import AttributionEntry, RegionInfo
from detour_api.repo import geo

router = APIRouter(prefix="/v1", tags=["regions"])


@router.get("/regions", summary="Import regions, their status and the data version in use.")
def list_regions(db: DatabaseDep) -> list[RegionInfo]:
    with db.tx() as conn:
        return geo.list_regions(conn)


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
