"""Matching a place to its Wikidata item.

Identifiers first, in this order: the Wikidata QID Detour already holds (the OpenStreetMap
``wikidata`` tag), a Wikipedia page's ``wikibase_item``, a provider's external identifier (a
GeoNames id through Wikidata's P1566). Coordinates are a controlled fallback only, used by the
operator command, never a similar name alone.

A coordinate match is accepted only when **all** of these hold:

* the candidate has coordinates and lies within the class's distance limit;
* the candidate's country (P17, as an ISO code) is the place's country;
* the candidate's nearest gazetteer city is the place's city (when both are known);
* the candidate is not of a class that is never a place (a person, a work, a disambiguation page,
  a taxon...);
* the place's normalised local name equals one of the candidate's labels or aliases, in any
  language (also after the ASCII folds) -- equal, not similar;
* exactly one candidate passes. Two that pass are ambiguous and neither is used.
"""

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from detour_api.names.search import search_forms

# Distance limits in metres by class of place.
MAX_DISTANCE_M = {
    "landmark": 300.0,
    "business": 100.0,
    "transport": 500.0,
    "natural": 2000.0,
    "settlement": 10000.0,
    "street": 200.0,
}
# Wikidata classes that are never a place on a map (instance of, P31).
NOT_A_PLACE = frozenset(
    {
        "Q5",  # human
        "Q4167410",  # disambiguation page
        "Q13442814",  # scholarly article
        "Q7725634",  # literary work
        "Q11424",  # film
        "Q482994",  # album
        "Q134556",  # single
        "Q16521",  # taxon
        "Q4167836",  # Wikimedia category
        "Q17633526",  # Wikinews article
        "Q11266439",  # Wikimedia template
        "Q215380",  # musical group
    }
)


@dataclass(frozen=True)
class Subject:
    """The place to match, as Detour knows it."""

    lat: float
    lon: float
    country_iso2: str | None
    city_id: int | None
    place_class: str
    local_name: str


@dataclass(frozen=True)
class WikidataCandidate:
    qid: str
    lat: float | None
    lon: float | None
    country_iso2: str | None  # from P17, resolved to the country's ISO code
    city_id: int | None  # Detour's nearest gazetteer city to the candidate's coordinates
    instance_of: frozenset[str]
    names: tuple[str, ...]  # labels and aliases, any language


@dataclass(frozen=True)
class Verdict:
    qid: str
    accepted: bool
    reasons: tuple[str, ...] = field(default=())
    distance_m: float | None = None


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres (haversine, mean Earth radius)."""
    r = 6_371_008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _forms(names: Iterable[str]) -> set[str]:
    return {f for n in names for f in search_forms(n)}


def judge(subject: Subject, candidate: WikidataCandidate) -> Verdict:
    """Whether one candidate matches, with every reason it does not."""
    reasons: list[str] = []
    dist: float | None = None
    if candidate.lat is None or candidate.lon is None:
        reasons.append("no_coordinates")
    else:
        dist = distance_m(subject.lat, subject.lon, candidate.lat, candidate.lon)
        if dist > MAX_DISTANCE_M.get(subject.place_class, MAX_DISTANCE_M["landmark"]):
            reasons.append("too_far")
    if subject.country_iso2 is None or candidate.country_iso2 is None:
        reasons.append("country_unknown")
    elif subject.country_iso2.upper() != candidate.country_iso2.upper():
        reasons.append("other_country")
    if (
        subject.city_id is not None
        and candidate.city_id is not None
        and subject.city_id != candidate.city_id
    ):
        reasons.append("other_city")
    if candidate.instance_of & NOT_A_PLACE:
        reasons.append("not_a_place")
    if not (_forms([subject.local_name]) & _forms(candidate.names)):
        reasons.append("name_differs")
    return Verdict(candidate.qid, not reasons, tuple(reasons), dist)


def choose(
    subject: Subject, candidates: Sequence[WikidataCandidate]
) -> tuple[str | None, list[Verdict]]:
    """The one candidate that matches, or None (none matches, or several do)."""
    verdicts = [judge(subject, c) for c in candidates]
    accepted = [v for v in verdicts if v.accepted]
    return (accepted[0].qid if len(accepted) == 1 else None), verdicts
