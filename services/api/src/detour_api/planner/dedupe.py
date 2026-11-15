"""One sight, one candidate.

OpenStreetMap often maps a single attraction twice: a node and the outline of the same building or
artwork, or a statue and the memorial it stands on, under the same name a few metres apart. Each
becomes its own ``geo.place``, so a plan could visit "the same" sight twice in a row. Candidates
that share a normalised name and lie within ``SAME_SIGHT_RADIUS_M`` of each other are one sight:
the best-documented one stays (a Wikidata or Wikipedia link, more sitelinks), ties broken by
identifier so the result never depends on input order.
"""

import math
from collections import defaultdict
from collections.abc import Iterable

from detour_api.planner.types import Candidate
from detour_api.textnorm import normalize_text

EARTH_RADIUS_M = 6_371_008.8


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """The great-circle distance in metres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (
        math.sin((p2 - p1) / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


SAME_SIGHT_RADIUS_M = 300.0


def _rank(c: Candidate) -> tuple[int, int, int, int, str]:
    s = c.signals
    return (
        -int(bool(s.get("has_wikidata"))),
        -int(bool(s.get("has_wikipedia"))),
        -int(bool(s.get("has_heritage"))),
        -(c.sitelink_count or 0),
        c.place_id,
    )


def collapse_duplicates(candidates: Iterable[Candidate]) -> list[Candidate]:
    """The candidates without the extra copies of a sight, in ``place_id`` order."""
    groups: dict[str, list[Candidate]] = defaultdict(list)
    for c in candidates:
        groups[normalize_text(c.name)].append(c)
    kept: list[Candidate] = []
    for group in groups.values():
        chosen: list[Candidate] = []
        for c in sorted(group, key=_rank):
            if not any(
                haversine_m(c.lat, c.lon, k.lat, k.lon) <= SAME_SIGHT_RADIUS_M for k in chosen
            ):
                chosen.append(c)
        kept.extend(chosen)
    return sorted(kept, key=lambda c: c.place_id)
