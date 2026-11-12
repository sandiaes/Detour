"""Turn the uncached cells into provider requests (ADR 004, ADR 013).

Rules, all from ADR 004 and the owner's measurements of 2026-11-12:

* a matrix request has at most 100 cells and every source-target distance at most 150 km;
* a cell farther apart than that is one single-route request, one per leg.

The request shape is fixed (``matrix-v1``): **one source and up to 100 targets**. A sparse set of
cells (each place against a bounded set of neighbours, as ADR 004 asks Phase 4 to plan) packs
without waste, and every cell comes from the same kind of request. The price is more requests
for a dense matrix: n places need about n x ceil((n - 1) / 100) matrix requests, where a 10 x 10
block shape would need about a quarter of that for n = 50 (ADR 013 weighs this).

The plan is a pure function of the cells: sorted, so the same cells always give the same requests.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from detour_api.adapters.valhalla import MATRIX_MAX_CELLS, MATRIX_MAX_METERS
from detour_api.travel.types import Coord, distance_m


@dataclass(frozen=True)
class MatrixRequest:
    source: Coord
    targets: tuple[Coord, ...]


@dataclass(frozen=True)
class RouteRequest:
    origin: Coord
    destination: Coord


def is_matrix_cell(a: Coord, b: Coord) -> bool:
    """True if the pair is close enough for a matrix request; otherwise it is a route leg."""
    return distance_m(a, b) <= MATRIX_MAX_METERS


def plan(cells: Iterable[tuple[Coord, Coord]]) -> tuple[list[MatrixRequest], list[RouteRequest]]:
    """Matrix requests (grouped by source, at most 100 targets each) and route requests."""
    by_source: dict[Coord, list[Coord]] = defaultdict(list)
    routes: list[RouteRequest] = []
    for a, b in sorted(set(cells)):
        if a == b:
            continue
        if is_matrix_cell(a, b):
            by_source[a].append(b)
        else:
            routes.append(RouteRequest(a, b))
    matrices = [
        MatrixRequest(source, tuple(targets[i : i + MATRIX_MAX_CELLS]))
        for source, targets in sorted(by_source.items())
        for i in range(0, len(targets), MATRIX_MAX_CELLS)
    ]
    return matrices, routes
