"""The regions the project knows how to import (decision D2, ADR 009)."""

from dataclasses import dataclass

GEOFABRIK_BASE = "https://download.geofabrik.de"


@dataclass(frozen=True)
class RegionDef:
    id: str  # slug; also the Geofabrik file name
    name: str
    geofabrik_path: str  # for example europe/austria
    countries: tuple[str, ...]  # ISO 3166-1 alpha-2

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
        # Geofabrik lists Greater London under England (read 2026-11-17,
        # https://download.geofabrik.de/europe/great-britain/england.html). That table shows no
        # .poly link for it; if the file is missing the coverage polygon stays unknown and the
        # importer warns.
        RegionDef(
            "greater-london",
            "Greater London",
            "europe/great-britain/england/greater-london",
            ("GB",),
        ),
        # Whole countries, each a single extract at Geofabrik's europe page (links read
        # 2026-11-17, https://download.geofabrik.de/europe.html). The country code decides which
        # region a destination belongs to, so a country appears once. France and Germany (about
        # 4.5 GB each) are left out until a smaller one has been imported and measured.
        # City extracts (ADR 033): each claims its country's code, so a destination belongs to it
        # only inside its coverage polygon (geo.region_for_country). Links read 2026-11-17 on
        # Geofabrik: france/ile-de-france (324 MB), germany/berlin (95 MB); each region's own page
        # links a .poly file.
        RegionDef("paris", "Paris (Île-de-France)", "europe/france/ile-de-france", ("FR",)),
        RegionDef("berlin", "Berlin", "europe/germany/berlin", ("DE",)),
        RegionDef("belgium", "Belgium", "europe/belgium", ("BE",)),
        RegionDef("croatia", "Croatia", "europe/croatia", ("HR",)),
        RegionDef("denmark", "Denmark", "europe/denmark", ("DK",)),
        RegionDef("finland", "Finland", "europe/finland", ("FI",)),
        RegionDef("greece", "Greece", "europe/greece", ("GR",)),
        RegionDef("iceland", "Iceland", "europe/iceland", ("IS",)),
        # The extract also holds Northern Ireland (code GB); the region claims only IE.
        RegionDef(
            "ireland",
            "Ireland",
            "europe/ireland-and-northern-ireland",
            ("IE",),
        ),
        RegionDef("luxembourg", "Luxembourg", "europe/luxembourg", ("LU",)),
        RegionDef("malta", "Malta", "europe/malta", ("MT",)),
        RegionDef("netherlands", "Netherlands", "europe/netherlands", ("NL",)),
        RegionDef("norway", "Norway", "europe/norway", ("NO",)),
        RegionDef("poland", "Poland", "europe/poland", ("PL",)),
        RegionDef("portugal", "Portugal", "europe/portugal", ("PT",)),
        RegionDef("slovakia", "Slovakia", "europe/slovakia", ("SK",)),
        RegionDef("slovenia", "Slovenia", "europe/slovenia", ("SI",)),
        RegionDef("spain", "Spain", "europe/spain", ("ES",)),
        RegionDef("sweden", "Sweden", "europe/sweden", ("SE",)),
        RegionDef("switzerland", "Switzerland", "europe/switzerland", ("CH",)),
    )
}
