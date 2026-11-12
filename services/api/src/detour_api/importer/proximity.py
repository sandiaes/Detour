"""Keep restaurants and cafes only near attractions or towns (ADR 011).

A restaurant on a remote road is never proposed in an itinerary, and restaurants and cafes are
more than half of the data. The rule keeps one when it is within ``RESTAURANT_RADIUS_M`` of a kept
attraction, or within ``TOWN_RADIUS_M`` of the centre of a gazetteer town with at least
``TOWN_MIN_POPULATION`` inhabitants. Distances are great-circle distances.

Pure Python on a grid, so it needs no database and gives the same answer on every machine.
"""

import math
from collections.abc import Iterable

EARTH_RADIUS_M = 6_371_008.8
METERS_PER_DEGREE = 111_320.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (
        math.sin((p2 - p1) / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


class ProximityIndex:
    """Answers "is there a point within ``radius_m``?" with a grid of cells at least that wide."""

    def __init__(self, points: Iterable[tuple[float, float]], radius_m: float) -> None:
        self.radius_m = radius_m
        pts = sorted(set(points))  # (lat, lon); sorted so nothing depends on input order
        self.count = len(pts)
        widest = min(max((abs(lat) for lat, _ in pts), default=0.0), 85.0)
        self._cell_lat = radius_m / METERS_PER_DEGREE
        self._cell_lon = radius_m / (METERS_PER_DEGREE * math.cos(math.radians(widest)))
        self._cells: dict[tuple[int, int], list[tuple[float, float]]] = {}
        for lat, lon in pts:
            self._cells.setdefault(self._key(lat, lon), []).append((lat, lon))

    def _key(self, lat: float, lon: float) -> tuple[int, int]:
        return math.floor(lat / self._cell_lat), math.floor(lon / self._cell_lon)

    def near(self, lat: float, lon: float) -> bool:
        ci, cj = self._key(lat, lon)
        for i in (ci - 1, ci, ci + 1):
            for j in (cj - 1, cj, cj + 1):
                for plat, plon in self._cells.get((i, j), ()):
                    if haversine_m(lat, lon, plat, plon) <= self.radius_m:
                        return True
        return False
