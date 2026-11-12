"""Candidate selection and scoring (architecture section 5.2, step 2).

A candidate's **value** is what a plan gains by including it, in tenths of a point
(``value_scale``); one minute of travel costs ``profile.travel_weight`` of those units. All
arithmetic is on integers (floor division), so a value is the same on every machine.

    base   = base points + notability points + category points
    value  = base x value_scale x distance factor x repeat-category factor

* **Notability** comes from what the import has: OSM tags linking to Wikidata, Wikipedia or a
  heritage listing, and ``tourism=attraction``; plus the Wikidata sitelink count when the import
  has fetched it (it does not yet: data-model section 2.8). There are no ratings.
* **Distance** from the destination point: full value at the point, ``edge_value_pct`` at the
  profile's radius, nothing beyond it.
* **Repeat category:** the n-th best place of a category keeps ``repeat_category_pct[n]`` of its
  value, so a profile with a steep table prefers variety.
"""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from detour_api.planner.config import PlannerConfig, Profile
from detour_api.planner.types import Candidate
from detour_api.travel.types import Coord, distance_m


@dataclass(frozen=True)
class Scored:
    candidate: Candidate
    distance_m: int
    value: int


def centre_distance(candidate: Candidate, centre: Coord) -> int:
    return round(distance_m(centre, candidate.coord))


def notability_points(candidate: Candidate, config: PlannerConfig) -> int:
    points = sum(p for key, p in config.notability_points.items() if candidate.signals.get(key))
    if candidate.sitelink_count is not None:
        for at_least, bonus in config.sitelink_points:
            if candidate.sitelink_count >= at_least:
                points += bonus
                break
    return points


def category_points(candidate: Candidate, config: PlannerConfig) -> int:
    return config.category_points.get(candidate.category, config.default_category_points)


def base_value(candidate: Candidate, config: PlannerConfig) -> int:
    return (
        config.base_points
        + notability_points(candidate, config)
        + category_points(candidate, config)
    )


def score(
    candidates: Iterable[Candidate],
    centre: Coord,
    profile: Profile,
    config: PlannerConfig,
    limit: int,
) -> list[Scored]:
    """The profile's candidates within its radius, best first (ties by place id), at most
    ``limit``."""
    within: list[tuple[Candidate, int, int]] = []
    for c in sorted(candidates, key=lambda c: c.place_id):
        d = centre_distance(c, centre)
        if d > profile.radius_m:
            continue
        drop = (100 - profile.edge_value_pct) * d // profile.radius_m
        within.append((c, d, base_value(c, config) * config.value_scale * (100 - drop)))
    by_category: dict[str, list[tuple[Candidate, int, int]]] = defaultdict(list)
    for item in within:
        by_category[item[0].category].append(item)
    scored: list[Scored] = []
    table = profile.repeat_category_pct
    for items in by_category.values():
        items.sort(key=lambda t: (-t[2], t[0].place_id))
        for rank, (c, d, pre) in enumerate(items):
            pct = table[min(rank, len(table) - 1)]
            scored.append(Scored(c, d, pre * pct // 10_000))
    scored.sort(key=lambda s: (-s.value, s.candidate.place_id))
    return scored[:limit]


def static_reasons(candidate: Candidate, distance: int, config: PlannerConfig) -> list[str]:
    """Reason codes that depend on the place alone (the engine adds those that depend on the
    plan)."""
    reasons: list[str] = []
    if candidate.signals.get("has_wikidata"):
        reasons.append("WIKIDATA_LINKED")
    if candidate.signals.get("has_wikipedia"):
        reasons.append("WIKIPEDIA_ARTICLE")
    top_sitelinks = config.sitelink_points[0][0] if config.sitelink_points else None
    if (
        candidate.sitelink_count is not None
        and top_sitelinks is not None
        and candidate.sitelink_count >= top_sitelinks
    ):
        reasons.append("WIKIDATA_SITELINKS")
    if candidate.signals.get("has_heritage"):
        reasons.append("HERITAGE_LISTED")
    if candidate.signals.get("tourism_attraction"):
        reasons.append("TAGGED_TOURIST_ATTRACTION")
    if category_points(candidate, config) >= config.highlight_category_points:
        reasons.append("HIGHLIGHT_CATEGORY")
    if distance <= config.near_centre_m:
        reasons.append("NEAR_CENTRE")
    return reasons


def nearest(points: Sequence[tuple[str, Coord]], k: int) -> dict[str, list[str]]:
    """For each point, the ids of its ``k`` nearest others (straight line, ties by id)."""
    result: dict[str, list[str]] = {}
    for pid, coord in points:
        others = sorted(
            ((round(distance_m(coord, c)), oid) for oid, c in points if oid != pid),
        )
        result[pid] = [oid for _, oid in others[:k]]
    return result
