"""The API shape of a resolved name."""

from detour_api.models.common import PlaceName
from detour_api.names.resolver import ResolvedName


def to_api(resolved: ResolvedName) -> PlaceName:
    return PlaceName(
        display=resolved.display,
        local=resolved.local,
        # "und" (unknown) and "mul" are not languages a reader can use: null.
        local_lang=None
        if not resolved.local_lang or resolved.local_lang.split("-")[0] in ("und", "mul")
        else resolved.local_lang,
        type=resolved.display_type,
        source=resolved.source,
        confidence=round(resolved.confidence, 2),
        auto_generated=resolved.generated,
        user_override=resolved.user_override,
    )
