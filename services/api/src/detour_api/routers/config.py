from fastapi import APIRouter

from detour_api.deps import SettingsDep
from detour_api.schemas import AttributionLine, ClientConfig, MapConfig

router = APIRouter(prefix="/v1", tags=["config"])


@router.get("/config", summary="Client configuration: map style URL and attribution lines.")
def get_config(settings: SettingsDep) -> ClientConfig:
    return ClientConfig(
        config_version=settings.config_version,
        map=MapConfig(
            style_url=settings.map_style_url,
            attribution=[AttributionLine(text=a.text, url=a.url) for a in settings.map_attribution],
        ),
    )
