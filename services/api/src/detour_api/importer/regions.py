"""The regions the project knows how to import (decision D2, ADR 009)."""

from dataclasses import dataclass

GEOFABRIK_BASE = "https://download.geofabrik.de"


@dataclass(frozen=True)
class RegionDef:
    id: str  # slug; also the Geofabrik file name
    name: str
    geofabrik_path: str  # for example europe/austria
    countries: tuple[str, ...]  # ISO 3166-1 alpha-2
    # The size Geofabrik shows for the extract, when it was read (ADR 033); None when not read.
    download_mb: int | None = None

    @property
    def extract_url(self) -> str:
        return f"{GEOFABRIK_BASE}/{self.geofabrik_path}-latest.osm.pbf"

    @property
    def poly_url(self) -> str:
        return f"{GEOFABRIK_BASE}/{self.geofabrik_path}.poly"


REGIONS: dict[str, RegionDef] = {
    r.id: r
    for r in (
        RegionDef("austria", "Austria", "europe/austria", ("AT",)),
        RegionDef("czech-republic", "Czechia", "europe/czech-republic", ("CZ",)),
        RegionDef("hungary", "Hungary", "europe/hungary", ("HU",)),
        RegionDef("italy", "Italy", "europe/italy", ("IT",)),
        RegionDef("japan", "Japan", "asia/japan", ("JP",)),
        # Geofabrik lists Greater London under England with a 124 MB extract (read 2026-11-17,
        # https://download.geofabrik.de/europe/great-britain/england.html). It shows no .poly
        # file for it, so the region's coverage polygon stays unknown (the importer warns).
        RegionDef(
            "greater-london",
            "Greater London",
            "europe/great-britain/england/greater-london",
            ("GB",),
            download_mb=124,
        ),
    )
}
