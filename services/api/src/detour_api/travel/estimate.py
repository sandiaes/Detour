"""The labelled fallback: straight-line distance times a mode factor (ADR 004, ADR 013).

When there is no routed time (adapter off, provider failing, budget or time used up, or the
provider has no route for the cell) a transfer is **estimated** from the straight-line distance:

    meters  = straight-line distance x detour factor
    seconds = meters, converted at the mode's speed

These numbers are our own assumptions, not provider data and not measured. They are versioned
(``ESTIMATE_VERSION``) and always shown with the label ``estimated`` (CLAUDE.md, constraint 5). The
driving speed has two tiers because one speed is wrong for both a city centre and a motorway.
"""

from dataclasses import dataclass

from detour_api.travel.types import Coord, EstimateReason, Mode, TravelTime, distance_m

ESTIMATE_VERSION = "2026-11-12.1"


@dataclass(frozen=True)
class ModeRule:
    detour_factor: float
    # Metres per second for the first ``tier_meters`` of the path, and beyond it.
    near_speed: float
    far_speed: float
    tier_meters: float


KMH = 1000 / 3600

RULES: dict[Mode, ModeRule] = {
    # Walking: a single speed (4.5 km/h) over any distance.
    "walk": ModeRule(1.3, 4.5 * KMH, 4.5 * KMH, 0.0),
    # Driving: 30 km/h for the first 25 km of path (streets, junctions), 80 km/h beyond.
    "drive": ModeRule(1.3, 30 * KMH, 80 * KMH, 25_000.0),
}


def estimate(a: Coord, b: Coord, mode: Mode) -> tuple[int, int]:
    """``(seconds, meters)`` for a transfer; zero for two identical points."""
    rule = RULES[mode]
    meters = distance_m(a, b) * rule.detour_factor
    near = min(meters, rule.tier_meters)
    far = meters - near
    seconds = near / rule.near_speed + far / rule.far_speed
    return round(seconds), round(meters)


def estimated(a: Coord, b: Coord, mode: Mode, reason: EstimateReason) -> TravelTime:
    seconds, meters = estimate(a, b, mode)
    return TravelTime(seconds, meters, "estimated", "estimate", reason)
