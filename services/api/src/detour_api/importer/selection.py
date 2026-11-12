"""The attraction selection rule: which OpenStreetMap objects become places.

One function, ``decide``, so the rule is read, tested and versioned in one place. It implements
ADR 003 with the additions of ADR 011:

* kept by default: ``tourism=attraction|museum|gallery|viewpoint|zoo|theme_park|aquarium``, every
  ``historic=*`` value not named below, and ``amenity=restaurant|cafe``;
* never imported: wayside shrines and crosses, boundary stones, bomb craters (ADR 003), and tree
  shrines, ``heritage`` and ``heritage_building`` (ADR 011, after the first real import);
* memorials: kept only with a ``wikidata`` tag **and** a name, and not of a subtype that is a
  plaque, grave marker or similar (the stricter test asked for in ADR 003's addendum);
* ``historic=yes|building|railway|stone|tomb``: kept only with a name **and** at least one
  notability tag (``wikidata``, ``wikipedia`` or ``heritage``).

Every excluded object gets a class (``historic=wayside_shrine``) and a reason code, which is what
the data quality report counts.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass

# Bump when any rule below changes: the version is stored on every import run.
RULES_VERSION = "2026-11-12.4"

ATTRACTION_TOURISM = frozenset(
    {"attraction", "museum", "gallery", "viewpoint", "zoo", "theme_park", "aquarium"}
)
FOOD_AMENITY = frozenset({"restaurant", "cafe"})

# ADR 011, owner decision of 2026-11-12 ("only cities and tourist spots mostly"): the
# historic=* values that are tourist spots. Everything else is left out and counted by class, so
# the report shows what was dropped. Chosen from the categories of the first real import
# (Austria); other countries may need additions, and the report will show which.
TOURIST_HISTORIC = frozenset(
    {
        "castle", "fort", "fortress", "palace", "ruins", "archaeological_site", "monument",
        "manor", "monastery", "abbey", "church", "chapel", "temple", "city_gate", "tower",
        "aqueduct", "viaduct", "bridge", "battlefield", "fountain", "statue",
        "technical_monument", "place_of_worship", "cemetery",
    }
)  # fmt: skip
# ADR 003, section 2.
ALWAYS_EXCLUDED_HISTORIC = frozenset(
    {
        "wayside_shrine",
        "wayside_cross",
        "boundary_stone",
        "bomb_crater",
        # ADR 011, owner decision after reading the first real import (Austria): a shrine on a
        # tree is a wayside shrine; "heritage" values name a protection status, not a kind of sight.
        "tree_shrine",
        "heritage",
        "heritage_building",
    }
)
_CLEAN_VALUE = re.compile(r"[^a-z0-9_]+")


def _normalised(value: str) -> str:
    """The tag value as the stored category spells it: lower case, other characters as ``_``."""
    return _CLEAN_VALUE.sub("_", value.strip().lower()).strip("_")


# ADR 011: memorial subtypes that mark small local objects rather than sights.
EXCLUDED_MEMORIAL_SUBTYPES = frozenset(
    {
        "plaque",
        "blue_plaque",
        "stolperstein",
        "ghost_bike",
        "bench",
        "grave",
        "war_grave",
        "cross",
        "stone",
    }
)
# ADR 011: generic classes that were still imported after ADR 003.
# railway is not here any more: track segments are not tourist spots (see TOURIST_HISTORIC).
# citywalls: walls are mapped in many short pieces, so only named, documented ones are kept.
QUALIFIED_ONLY_HISTORIC = frozenset({"yes", "building", "stone", "tomb", "citywalls"})
NOTABILITY_TAGS = ("wikidata", "wikipedia", "heritage")

# Classes whose decision the owner is asked to review: the import writes a sample of them.
REVIEW_CLASSES = frozenset({"historic=memorial"}) | {
    f"historic={v}" for v in QUALIFIED_ONLY_HISTORIC
}

REASON_ALWAYS_EXCLUDED = "adr003_excluded_class"
REASON_MEMORIAL_NO_WIKIDATA = "memorial_without_wikidata"
REASON_MEMORIAL_UNNAMED = "memorial_without_name"
REASON_MEMORIAL_SUBTYPE = "memorial_excluded_subtype"
REASON_UNQUALIFIED = "generic_class_without_name_and_notability"
REASON_NO_GEOMETRY = "no_geometry"
REASON_ATTRACTION_UNNAMED = "attraction_without_name"
REASON_NOT_NEAR = "restaurant_not_near_attraction_or_town"

# ADR 011, owner decision of 2026-11-12: restaurants and cafes are kept only near attractions or
# towns (importer/proximity.py). Radii and town size chosen from a measurement on the Austria
# database: 500 m keeps 51 % of its restaurants and 75 % of its cafes.
RESTAURANT_RADIUS_M = 500
TOWN_MIN_POPULATION = 5000
TOWN_RADIUS_M = 1500
REASON_NOT_TOURIST = "historic_class_not_tourist"


@dataclass(frozen=True)
class Decision:
    kept: bool
    osm_class: str  # for example "historic=memorial" or "tourism=museum"
    reason: str  # why it was excluded, or why it was kept
    kind: str | None = None  # "attraction" or "restaurant" when kept
    category: str | None = None


def _present(tags: Mapping[str, str], key: str) -> bool:
    return bool(tags.get(key, "").strip())


def decide(tags: Mapping[str, str]) -> Decision | None:
    """Classify one object. ``None`` means it is not a candidate at all."""
    named = _present(tags, "name")

    amenity = tags.get("amenity")
    if amenity in FOOD_AMENITY:
        return Decision(True, f"amenity={amenity}", "food", "restaurant", amenity)

    tourism = tags.get("tourism")
    if tourism in ATTRACTION_TOURISM:
        if not named:  # an unnamed "viewpoint" cannot be shown in an itinerary
            return Decision(False, f"tourism={tourism}", REASON_ATTRACTION_UNNAMED)
        return Decision(True, f"tourism={tourism}", "tourism", "attraction", tourism)

    historic = tags.get("historic")
    if historic is None:
        return None
    cls = f"historic={historic}"
    value = _normalised(historic)

    if value in ALWAYS_EXCLUDED_HISTORIC:
        return Decision(False, cls, REASON_ALWAYS_EXCLUDED)

    if value == "memorial":
        if not _present(tags, "wikidata"):
            return Decision(False, cls, REASON_MEMORIAL_NO_WIKIDATA)
        if not named:
            return Decision(False, cls, REASON_MEMORIAL_UNNAMED)
        subtype = tags.get("memorial", tags.get("memorial:type", "")).strip().lower()
        if subtype in EXCLUDED_MEMORIAL_SUBTYPES:
            return Decision(False, cls, REASON_MEMORIAL_SUBTYPE)
        return Decision(True, cls, "memorial_with_wikidata_and_name", "attraction", "memorial")

    if value in QUALIFIED_ONLY_HISTORIC:
        if named and any(_present(tags, k) for k in NOTABILITY_TAGS):
            category = "historic" if value == "yes" else f"historic_{value}"
            return Decision(True, cls, "generic_class_qualified", "attraction", category)
        return Decision(False, cls, REASON_UNQUALIFIED)

    if value in TOURIST_HISTORIC:
        if not named:
            return Decision(False, cls, REASON_ATTRACTION_UNNAMED)
        return Decision(True, cls, "historic", "attraction", value)

    return Decision(False, cls, REASON_NOT_TOURIST)
