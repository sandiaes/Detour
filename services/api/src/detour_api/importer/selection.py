"""The attraction selection rule: which OpenStreetMap objects become places.

One function, ``decide``, so the rule is read, tested and versioned in one place. It implements
ADR 003 with the additions of ADR 011:

* kept by default: ``tourism=attraction|museum|gallery|viewpoint|zoo|theme_park|aquarium``, every
  ``historic=*`` value not named below, and ``amenity=restaurant|cafe``;
* never imported: wayside shrines and crosses, boundary stones, bomb craters;
* memorials: kept only with a ``wikidata`` tag **and** a name, and not of a subtype that is a
  plaque, grave marker or similar (the stricter test asked for in ADR 003's addendum);
* ``historic=yes|building|railway|stone|tomb``: kept only with a name **and** at least one
  notability tag (``wikidata``, ``wikipedia`` or ``heritage``).

Every excluded object gets a class (``historic=wayside_shrine``) and a reason code, which is what
the data quality report counts.
"""

from collections.abc import Mapping
from dataclasses import dataclass

# Bump when any rule below changes: the version is stored on every import run.
RULES_VERSION = "2026-11-12.1"

ATTRACTION_TOURISM = frozenset(
    {"attraction", "museum", "gallery", "viewpoint", "zoo", "theme_park", "aquarium"}
)
FOOD_AMENITY = frozenset({"restaurant", "cafe"})

# ADR 003, section 2.
ALWAYS_EXCLUDED_HISTORIC = frozenset(
    {"wayside_shrine", "wayside_cross", "boundary_stone", "bomb_crater"}
)
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
QUALIFIED_ONLY_HISTORIC = frozenset({"yes", "building", "railway", "stone", "tomb"})
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
    amenity = tags.get("amenity")
    if amenity in FOOD_AMENITY:
        return Decision(True, f"amenity={amenity}", "food", "restaurant", amenity)

    tourism = tags.get("tourism")
    if tourism in ATTRACTION_TOURISM:
        return Decision(True, f"tourism={tourism}", "tourism", "attraction", tourism)

    historic = tags.get("historic")
    if historic is None:
        return None
    cls = f"historic={historic}"

    if historic in ALWAYS_EXCLUDED_HISTORIC:
        return Decision(False, cls, REASON_ALWAYS_EXCLUDED)

    if historic == "memorial":
        if not _present(tags, "wikidata"):
            return Decision(False, cls, REASON_MEMORIAL_NO_WIKIDATA)
        if not _present(tags, "name"):
            return Decision(False, cls, REASON_MEMORIAL_UNNAMED)
        subtype = tags.get("memorial", tags.get("memorial:type", "")).strip().lower()
        if subtype in EXCLUDED_MEMORIAL_SUBTYPES:
            return Decision(False, cls, REASON_MEMORIAL_SUBTYPE)
        return Decision(True, cls, "memorial_with_wikidata_and_name", "attraction", "memorial")

    if historic in QUALIFIED_ONLY_HISTORIC:
        if _present(tags, "name") and any(_present(tags, k) for k in NOTABILITY_TAGS):
            category = "historic" if historic == "yes" else f"historic_{historic}"
            return Decision(True, cls, "generic_class_qualified", "attraction", category)
        return Decision(False, cls, REASON_UNQUALIFIED)

    category = historic.strip() or "historic"
    return Decision(True, cls, "historic", "attraction", category)
