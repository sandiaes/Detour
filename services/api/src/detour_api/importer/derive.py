"""Turn one selected OpenStreetMap object into the rows of the geo schema.

Pure functions: no database, no clock. Missing values stay ``None`` (unknown); nothing is guessed.
Every table-shaped result is a plain dataclass so the loader can stream it with COPY.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from detour_api.importer.selection import Decision
from detour_api.textnorm import normalize_text, stable_uuid

OSM_TYPE_WORD = {"N": "node", "W": "way", "R": "relation"}
OSM_LICENCE = "ODbL-1.0"

# Venue type -> meal types, a fixed rule (docs/data-model.md). Only the venue types the importer
# produces are listed. Changing this table is a change of RULES_VERSION.
MEAL_TYPES_BY_VENUE: dict[str, list[str]] = {
    "restaurant": ["dinner", "lunch"],
    "cafe": ["breakfast", "snack"],
}

# Weights of the deterministic ranking score. They only order places for the planner (tuned in
# Phase 4); they are not facts about the places.
SCORE_WEIGHTS = {
    "has_wikidata": 3,
    "has_wikipedia": 2,
    "has_heritage": 2,
    "tourism_attraction": 1,
    "has_name": 1,
}

_LANG = re.compile(r"^[A-Za-z0-9_-]{1,30}$")
_QID = re.compile(r"^Q[0-9]+$")
_DIET = re.compile(r"^[a-z0-9_]{1,40}$")
_CATEGORY_CLEAN = re.compile(r"[^a-z0-9_]+")
# Keys that are copied into their own columns; place_source.tags does not repeat them.
_OWN_COLUMN_PREFIXES = ("name:", "addr:")


@dataclass(frozen=True)
class RestaurantProfileRow:
    cuisines: list[str] | None
    venue_type: str
    meal_types: list[str] | None
    diet_flags: list[str] | None


@dataclass(frozen=True)
class SignalRow:
    wikidata_id: str | None
    osm_signals: dict[str, object]
    score: float


@dataclass(frozen=True)
class PlaceRow:
    id: str
    region_id: str
    kind: str
    category: str
    name: str | None
    name_norm: str | None
    names_i18n: dict[str, str] | None
    lon: float
    lat: float
    address: dict[str, str] | None
    osm_class: str
    source_ref: str
    source_tags: dict[str, str]
    profile: RestaurantProfileRow | None
    signal: SignalRow
    review_tags: dict[str, str] = field(default_factory=dict)
    # The normalised English name (``name:en``), only when it differs from ``name_norm``: search
    # matches it as well, so a traveller can type either name.
    name_en_norm: str | None = None


def source_ref(osm_type: str, osm_id: int) -> str:
    return f"{OSM_TYPE_WORD[osm_type]}/{osm_id}"


def clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def parse_cuisines(raw: str | None) -> list[str] | None:
    """``cuisine=italian;pizza`` -> ``["italian", "pizza"]`` (sorted, unique, lower case)."""
    if raw is None:
        return None
    items = {re.sub(r"\s+", "_", part.strip().lower()) for part in raw.split(";") if part.strip()}
    return sorted(items) or None


def parse_diet_flags(tags: Mapping[str, str]) -> list[str] | None:
    flags: set[str] = set()
    for key, value in tags.items():
        if not key.startswith("diet:"):
            continue
        name = key[5:]
        if not _DIET.match(name):
            continue
        if value == "yes":
            flags.add(name)
        elif value == "only":
            flags.add(f"{name}_only")
    return sorted(flags) or None


def parse_names_i18n(tags: Mapping[str, str]) -> dict[str, str] | None:
    names: dict[str, str] = {}
    for key, value in tags.items():
        text = clean(value)
        if text is None:
            continue
        if key.startswith("name:") and _LANG.match(key[5:]):
            names[key[5:]] = text
        elif key == "int_name":
            names["int"] = text
    return dict(sorted(names.items())) or None


def parse_address(tags: Mapping[str, str]) -> dict[str, str] | None:
    mapping = {
        "addr:street": "street",
        "addr:housenumber": "housenumber",
        "addr:postcode": "postcode",
        "addr:city": "city",
        "addr:country": "country",
    }
    address = {out: v for key, out in mapping.items() if (v := clean(tags.get(key)))}
    return address or None


def parse_wikidata(tags: Mapping[str, str]) -> str | None:
    value = clean(tags.get("wikidata"))
    return value if value and _QID.match(value) else None


def build_signal(tags: Mapping[str, str], name: str | None) -> SignalRow:
    wikidata_id = parse_wikidata(tags)
    flags: dict[str, object] = {
        "has_wikidata": wikidata_id is not None,
        "has_wikipedia": clean(tags.get("wikipedia")) is not None,
        "has_heritage": clean(tags.get("heritage")) is not None,
        "tourism_attraction": tags.get("tourism") == "attraction",
        "has_name": name is not None,
        "has_website": clean(tags.get("website") or tags.get("contact:website")) is not None,
    }
    heritage = clean(tags.get("heritage"))
    if heritage:
        flags["heritage"] = heritage
    score = float(sum(w for key, w in SCORE_WEIGHTS.items() if flags.get(key)))
    return SignalRow(wikidata_id=wikidata_id, osm_signals=dict(sorted(flags.items())), score=score)


def build_place(
    region_id: str,
    osm_type: str,
    osm_id: int,
    decision: Decision,
    tags: Mapping[str, str],
    lon: float,
    lat: float,
) -> PlaceRow:
    assert decision.kept and decision.kind and decision.category  # noqa: S101
    ref = source_ref(osm_type, osm_id)
    name = clean(tags.get("name"))
    category = _CATEGORY_CLEAN.sub("_", decision.category.strip().lower()).strip("_") or "historic"
    profile = None
    if decision.kind == "restaurant":
        venue = decision.category
        profile = RestaurantProfileRow(
            cuisines=parse_cuisines(tags.get("cuisine")),
            venue_type=venue,
            meal_types=MEAL_TYPES_BY_VENUE.get(venue),
            diet_flags=parse_diet_flags(tags),
        )
    names = parse_names_i18n(tags)
    name_en = clean(names.get("en")) if names else None
    en_norm = normalize_text(name_en) if name_en else None
    if en_norm and en_norm == (normalize_text(name) if name else None):
        en_norm = None
    source_tags = {k: v for k, v in sorted(tags.items()) if not k.startswith(_OWN_COLUMN_PREFIXES)}
    return PlaceRow(
        id=str(stable_uuid("place", f"{region_id}/osm/{ref}")),
        region_id=region_id,
        kind=decision.kind,
        category=category,
        name=name,
        name_norm=normalize_text(name) if name else None,
        names_i18n=names,
        lon=lon,
        lat=lat,
        address=parse_address(tags),
        osm_class=decision.osm_class,
        source_ref=ref,
        source_tags=source_tags,
        profile=profile,
        signal=build_signal(tags, name),
        name_en_norm=en_norm or None,
    )
