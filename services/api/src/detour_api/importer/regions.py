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
    # Read on 2026-11-17 from each region's page ("File size: ..."); GB figures are x 1000.
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
        RegionDef("austria", "Austria", "europe/austria", ("AT",), download_mb=777),
        RegionDef("czech-republic", "Czechia", "europe/czech-republic", ("CZ",), download_mb=909),
        RegionDef("hungary", "Hungary", "europe/hungary", ("HU",), download_mb=314),
        RegionDef("italy", "Italy", "europe/italy", ("IT",), download_mb=2100),
        RegionDef("japan", "Japan", "asia/japan", ("JP",), download_mb=2400),
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
