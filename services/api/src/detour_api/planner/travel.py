"""Travel times for the planner, from the Phase 3 travel-time service (ADR 013).

The engine sees a ``TravelSource``: give it cells and a mode, get back a ``TravelTime`` per cell,
each labelled ``routed`` or ``estimated``. Production uses ``ServiceTravelSource`` (cache, then
FOSSGIS Valhalla within a time limit, then the labelled estimate); tests use a source that returns
fixed times. The engine never makes up a time: every transfer it writes is a value a source
returned, and the validator checks that.

**Mode rule:** a transfer up to ``walk_max_m`` straight-line is walked, a longer one driven. It
depends on the two points only, so a pair always has the same mode.
"""

import math
import time
from collections import defaultdict
from collections.abc import Callable, Iterable
from typing import Protocol

from detour_api.travel.estimate import estimated
from detour_api.travel.service import TravelTimeService
from detour_api.travel.types import Coord, EstimateReason, Mode, TravelTime, distance_m

Cell = tuple[Coord, Coord]


class TravelSource(Protocol):
    def times(
        self, cells: dict[Mode, list[Cell]], *, use_provider: bool
    ) -> dict[Cell, TravelTime]: ...


def mode_for(a: Coord, b: Coord, walk_max_m: int) -> Mode:
    return "walk" if distance_m(a, b) <= walk_max_m else "drive"


def minutes(seconds: int) -> int:
    """The minutes the schedule reserves for a transfer: rounded up, never down."""
    return math.ceil(seconds / 60)


class ServiceTravelSource:
    """The travel-time service, with one time budget shared by every call of a generation."""

    def __init__(
        self,
        service: TravelTimeService,
        *,
        max_seconds: float,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._service = service
        self._max_seconds = max_seconds
        self._now = now
        self._deadline: float | None = None

    def times(self, cells: dict[Mode, list[Cell]], *, use_provider: bool) -> dict[Cell, TravelTime]:
        out: dict[Cell, TravelTime] = {}
        for mode in sorted(cells):
            remaining: float | None = None
            if use_provider:
                if self._deadline is None:
                    self._deadline = self._now() + self._max_seconds
                remaining = max(0.0, self._deadline - self._now())
            result = self._service.cells(
                cells[mode], mode, max_seconds=remaining, use_provider=use_provider
            )
            out.update(result.times)
        return out


class FixedTravelSource:
    """Times from a table, the labelled estimate for every other cell. For tests and fixtures:
    ``table`` holds routed answers recorded for the fixture, nothing else. With
    ``provider_only`` the table answers only calls that may use the provider (an empty cache)."""

    def __init__(
        self, table: dict[Cell, tuple[int, int]] | None = None, *, provider_only: bool = False
    ) -> None:
        self._table = table or {}
        self._provider_only = provider_only
        self.calls: list[tuple[bool, int]] = []

    def times(self, cells: dict[Mode, list[Cell]], *, use_provider: bool) -> dict[Cell, TravelTime]:
        self.calls.append((use_provider, sum(len(v) for v in cells.values())))
        table = {} if self._provider_only and not use_provider else self._table
        out: dict[Cell, TravelTime] = {}
        for mode, items in cells.items():
            for a, b in items:
                hit = table.get((a, b))
                if a == b:
                    out[(a, b)] = estimated(a, b, mode, "same_point")
                elif hit is not None:
                    out[(a, b)] = TravelTime(hit[0], hit[1], "routed", "cache")
                else:
                    out[(a, b)] = estimated(a, b, mode, "provider_not_asked")
        return out


class TravelLookup:
    """The times one generation works with: what the source returned, and for any other pair
    the labelled estimate (reason ``provider_not_asked``). Records every value it hands out, so
    the validator can check each transfer against it."""

    def __init__(self, source: TravelSource, walk_max_m: int) -> None:
        self._source = source
        self._walk_max_m = walk_max_m
        self._answers: dict[Cell, TravelTime] = {}  # from the source
        self._implicit: dict[Cell, TravelTime] = {}  # estimates for pairs never asked about
        self._provider_asked: set[Cell] = set()

    def mode(self, a: Coord, b: Coord) -> Mode:
        return mode_for(a, b, self._walk_max_m)

    def fetch(self, cells: Iterable[Cell], *, use_provider: bool) -> None:
        """Ask the source about cells it has not answered yet (and, with ``use_provider``, about
        cells it answered with an estimate)."""
        by_mode: dict[Mode, list[Cell]] = defaultdict(list)
        for a, b in sorted(set(cells)):
            if a == b:
                continue
            current = self._answers.get((a, b))
            if current is None or (use_provider and current.confidence != "routed"):
                by_mode[self.mode(a, b)].append((a, b))
        if not by_mode:
            return
        answers = self._source.times(dict(by_mode), use_provider=use_provider)
        if use_provider:
            self._provider_asked.update(c for cells_ in by_mode.values() for c in cells_)
        for cell, value in answers.items():
            current = self._answers.get(cell)
            # A routed answer replaces an estimate; nothing replaces a routed answer.
            if current is None or current.confidence != "routed":
                self._answers[cell] = value
                self._implicit.pop(cell, None)

    def answered(self, a: Coord, b: Coord) -> bool:
        """True if the source answered for this pair with a routed time, or was asked with the
        provider allowed (so asking again would not help)."""
        found = self._answers.get((a, b))
        if found is None:
            return False
        return found.confidence == "routed" or (a, b) in self._provider_asked

    def get(self, a: Coord, b: Coord) -> TravelTime:
        found = self._answers.get((a, b)) or self._implicit.get((a, b))
        if found is None:
            reason: EstimateReason = "same_point" if a == b else "provider_not_asked"
            found = estimated(a, b, self.mode(a, b), reason)
            self._implicit[(a, b)] = found
        return found

    def known(self) -> dict[Cell, TravelTime]:
        return {**self._implicit, **self._answers}
