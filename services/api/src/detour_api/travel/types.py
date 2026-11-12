"""Value types shared by the routing adapter and the travel-time service."""

import math
from dataclasses import dataclass
from typing import Literal, NamedTuple

Mode = Literal["walk", "drive"]
Confidence = Literal["routed", "estimated"]
Source = Literal["cache", "provider", "estimate"]
# Why a value is an estimate. ``no_route``: the provider answered that it has no route for the
# cell (kept in the cache so it is not asked again at once). The others are not stored.
EstimateReason = Literal[
    "same_point",
    "no_route",
    "adapter_disabled",
    "adapter_unavailable",
    "budget_exhausted",
    "rate_limited",
    "time_limit",
    "cache_unavailable",
    "provider_not_asked",
]

MODES: tuple[Mode, ...] = ("walk", "drive")

# A coordinate is kept as integers of 1e-5 degree (about 1.1 m). The request sent to the provider
# is built from these integers, so a cached cell is a function of its key and nothing else.
SCALE = 100_000
EARTH_RADIUS_M = 6_371_008.8


class Coord(NamedTuple):
    lat_e5: int
    lon_e5: int

    @classmethod
    def from_degrees(cls, lat: float, lon: float) -> "Coord":
        if not (math.isfinite(lat) and math.isfinite(lon)):
            raise ValueError("coordinates must be finite")
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            raise ValueError("coordinates out of range")
        return cls(round(lat * SCALE), round(lon * SCALE))

    @property
    def lat(self) -> float:
        return round(self.lat_e5 / SCALE, 5)

    @property
    def lon(self) -> float:
        return round(self.lon_e5 / SCALE, 5)


def distance_m(a: Coord, b: Coord) -> float:
    """Great-circle distance in metres (haversine)."""
    phi1, phi2 = math.radians(a.lat), math.radians(b.lat)
    d_phi = phi2 - phi1
    d_lambda = math.radians(b.lon - a.lon)
    h = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


@dataclass(frozen=True)
class TravelTime:
    """One transfer. ``confidence`` is what the app shows; ``source`` and ``reason`` say how the
    value came about."""

    seconds: int
    meters: int
    confidence: Confidence
    source: Source
    reason: EstimateReason | None = None
    algorithm: str | None = None
