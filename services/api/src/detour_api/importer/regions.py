"""The regions the project knows how to import (decision D2, ADR 009)."""

from dataclasses import dataclass
from typing import Literal

GEOFABRIK_BASE = "https://download.geofabrik.de"


@dataclass(frozen=True)
class RegionDef:
    id: str  # slug; also the Geofabrik file name
    name: str
    geofabrik_path: str  # for example europe/austria
    countries: tuple[str, ...]  # ISO 3166-1 alpha-2
    # The group the app lists it under (ADR 033).
    continent: Literal["Africa", "Asia", "Europe", "North America", "Oceania", "South America"] = (
        "Europe"
    )
    # "country": a whole country, the only region that claims its code. "part": a city or a state
    # that claims its country's code but covers only its coverage polygon; several may share a code.
    scope: Literal["country", "part"] = "country"

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
        RegionDef("japan", "Japan", "asia/japan", ("JP",), "Asia"),
        # Geofabrik lists Greater London under England (read 2026-11-17,
        # https://download.geofabrik.de/europe/great-britain/england.html). That table shows no
        # .poly link for it; if the file is missing the coverage polygon stays unknown and the
        # importer warns.
        RegionDef(
            "greater-london",
            "Greater London",
            "europe/great-britain/england/greater-london",
            ("GB",),
            scope="part",
        ),
        # Whole countries, each a single extract at Geofabrik's europe page (links read
        # 2026-11-17, https://download.geofabrik.de/europe.html). The country code decides which
        # region a destination belongs to, so a country appears once. France and Germany (about
        # 4.5 GB each) are left out until a smaller one has been imported and measured.
        # City extracts (ADR 033): each claims its country's code, so a destination belongs to it
        # only inside its coverage polygon (geo.region_for_country). Links read 2026-11-17 on
        # Geofabrik: france/ile-de-france (324 MB), germany/berlin (95 MB); each region's own page
        # links a .poly file.
        RegionDef(
            "paris", "Paris (Île-de-France)", "europe/france/ile-de-france", ("FR",), scope="part"
        ),
        RegionDef("berlin", "Berlin", "europe/germany/berlin", ("DE",), scope="part"),
        # Geofabrik has no extract for Bordeaux alone: its Aquitaine region (the departments of
        # Gironde, Dordogne, Landes, Lot-et-Garonne and Pyrénées-Atlantiques) is the smallest one
        # that holds it: 283 MB, a .poly linked on its page, OSM data up to 2026-11-18T21:21:02Z
        # (read 2026-11-19, https://download.geofabrik.de/europe/france/aquitaine.html).
        RegionDef(
            "bordeaux", "Bordeaux (Aquitaine)", "europe/france/aquitaine", ("FR",), scope="part"
        ),
        # The USA by state (a country is far too big for the free database). Geofabrik has no
        # extract for New York City alone: the state is 475 MB and links a .poly file (read
        # 2026-11-17, https://download.geofabrik.de/north-america/us/new-york.html).
        RegionDef(
            "new-york",
            "New York State",
            "north-america/us/new-york",
            ("US",),
            "North America",
            "part",
        ),
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
