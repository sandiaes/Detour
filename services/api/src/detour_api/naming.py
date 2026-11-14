"""The name of a multi-city trip (ADR 024, decision 22; owner decision of 2026-11-14).

* Two stops: "<first city> to <last city>" ("Tokyo to Osaka").
* Three or more: "Multi-city <place>", where the place is the country when every stop is in one
  country ("Multi-city Japan"), else the region of the table below when all stops share one
  ("Multi-city Central Europe"), else the continent ("Multi-city Europe"), else "Multi-city trip".

Countries are the stops' GeoNames country codes. The region and continent come from this fixed
table, nothing is generated. The owner chose finer names than continents; the regions are the
usual English names, with Central Europe for the German-speaking countries and their eastern
neighbours. A country missing from the table gives "Multi-city trip" once the stops span countries.
"""

from collections.abc import Sequence

_REGIONS: dict[str, tuple[str, ...]] = {
    "Central Europe": ("AT", "CH", "CZ", "DE", "HU", "LI", "PL", "SI", "SK"),
    "Western Europe": ("BE", "FR", "IE", "LU", "MC", "NL", "GB"),
    "Northern Europe": ("DK", "EE", "FI", "FO", "IS", "LT", "LV", "NO", "SE"),
    "Southern Europe": ("AD", "ES", "GR", "IT", "MT", "PT", "SM", "VA", "CY"),
    "the Balkans": ("AL", "BA", "BG", "HR", "ME", "MK", "RO", "RS", "XK"),
    "Eastern Europe": ("BY", "MD", "UA"),
    "East Asia": ("CN", "HK", "JP", "KR", "MN", "MO", "TW"),
    "Southeast Asia": ("BN", "ID", "KH", "LA", "MM", "MY", "PH", "SG", "TH", "TL", "VN"),
    "South Asia": ("BD", "BT", "IN", "LK", "MV", "NP", "PK"),
    "the Middle East": ("AE", "BH", "IL", "JO", "KW", "LB", "OM", "PS", "QA", "SA", "TR"),
    "North Africa": ("DZ", "EG", "LY", "MA", "TN"),
    "North America": ("CA", "MX", "US"),
    "Australia and New Zealand": ("AU", "NZ"),
}

_CONTINENTS: dict[str, tuple[str, ...]] = {
    "Europe": (
        "Central Europe",
        "Western Europe",
        "Northern Europe",
        "Southern Europe",
        "the Balkans",
        "Eastern Europe",
    ),
    "Asia": ("East Asia", "Southeast Asia", "South Asia"),
    "Oceania": ("Australia and New Zealand",),
}

REGION_OF: dict[str, str] = {c: region for region, codes in _REGIONS.items() for c in codes}
CONTINENT_OF: dict[str, str] = {
    region: continent for continent, regions in _CONTINENTS.items() for region in regions
}

FALLBACK = "Multi-city trip"


def route_name(
    stop_names: Sequence[str],
    stop_countries: Sequence[str | None],
    country_names: dict[str, str],
) -> str:
    """The trip's name from its stops in order (``country_names``: ISO code to English name)."""
    if len(stop_names) == 2:
        return f"{stop_names[0]} to {stop_names[-1]}"
    codes = set(stop_countries)
    if None in codes or not codes:
        return FALLBACK
    if len(codes) == 1:
        (code,) = codes
        name = country_names.get(str(code))
        return f"Multi-city {name}" if name else FALLBACK
    regions = {REGION_OF.get(str(c)) for c in codes}
    if None in regions:
        return FALLBACK
    if len(regions) == 1:
        (region,) = regions
        return f"Multi-city {region}"
    continents = {CONTINENT_OF.get(str(r)) for r in regions}
    if len(continents) == 1 and None not in continents:
        (continent,) = continents
        return f"Multi-city {continent}"
    return FALLBACK
