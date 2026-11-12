"""The travel-time service (architecture section 4.5, ADR 004, ADR 013).

    cache (geo.travel_time)  ->  FOSSGIS Valhalla through the adapter  ->  labelled estimate

* **Plan generation reads the cache; only misses call the adapter.** A hit makes no network call.
* Cells within the matrix limits go to matrix requests (one source, up to 100 targets); cells
  farther apart go to one route request each. A given pair always takes the same path, so its
  cached time never mixes request shapes.
* Every provider answer is stored with the provider, the response date and the request shape. A
  cell the provider has no route for is stored as ``estimated`` (no number: it is recomputed on
  read) and asked again only after a retry period.
* Anything that stops the provider (adapter off, breaker open, budget or rate limit, a time
  limit, a failure) gives the estimate for the affected cells, with the reason. Those estimates
  are **not stored**: they say nothing about the provider and a later call may do better.
* Route geometry is fetched only on request, for the selected itinerary, and is never cached
  here or archived (ADR 006).
"""

import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime

import structlog
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from detour_api.adapters.valhalla import MATRIX_SHAPE, PROVIDER, ROUTE_SHAPE, ValhallaClient
from detour_api.repo import travel_time as repo
from detour_api.settings import Settings
from detour_api.travel import chunking
from detour_api.travel.estimate import estimated
from detour_api.travel.types import Coord, EstimateReason, Mode, TravelTime, distance_m

log = structlog.get_logger("detour.travel")

Cell = tuple[Coord, Coord]

# A pair this far apart that comes back as 0 s and 0 m is not a route (some Valhalla versions
# answer an unreachable cell that way); it is treated as "no route".
ZERO_IS_NOT_A_ROUTE_BEYOND_M = 25.0

_STATE_REASON: dict[str, EstimateReason] = {
    "disabled": "adapter_disabled",
    "unavailable": "adapter_unavailable",
    "budget_exhausted": "budget_exhausted",
    "rate_limited": "rate_limited",
}


@dataclass
class TravelStats:
    """What one call did; for logs and tests."""

    cache_hits: int = 0
    provider_requests: int = 0
    estimates: dict[str, int] = field(default_factory=dict)

    def count_estimate(self, reason: str) -> None:
        self.estimates[reason] = self.estimates.get(reason, 0) + 1


@dataclass
class TravelResult:
    times: dict[Cell, TravelTime]
    stats: TravelStats

    def get(self, a: Coord, b: Coord) -> TravelTime:
        return self.times[(a, b)]


@dataclass(frozen=True)
class RouteGeometry:
    seconds: int
    meters: int
    points: list[tuple[float, float]]


class TravelTimeService:
    def __init__(
        self,
        settings: Settings,
        engine: Engine | None,
        client: ValhallaClient,
        *,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._engine = engine
        self._client = client
        self._now = now

    # -- public interface ----------------------------------------------------------------------

    def matrix(
        self,
        points: Sequence[Coord],
        mode: Mode,
        *,
        max_seconds: float | None = None,
        use_provider: bool = True,
    ) -> TravelResult:
        """Every ordered pair of distinct points. Dense: for a sparse set use ``cells``."""
        unique = sorted(set(points))
        return self.cells(
            [(a, b) for a in unique for b in unique if a != b],
            mode,
            max_seconds=max_seconds,
            use_provider=use_provider,
        )

    def travel_time(self, a: Coord, b: Coord, mode: Mode) -> TravelTime:
        """One transfer, by the same rules as ``cells``."""
        return self.cells([(a, b)], mode).get(a, b)

    def cells(
        self,
        cells: Iterable[Cell],
        mode: Mode,
        *,
        max_seconds: float | None = None,
        use_provider: bool = True,
    ) -> TravelResult:
        """Times for the given ordered pairs. ``max_seconds`` limits the time spent on provider
        calls in this operation (cells not reached are estimated); ``use_provider=False`` reads
        the cache and estimates, and never calls out."""
        stats = TravelStats()
        times: dict[Cell, TravelTime] = {}
        pending: list[Cell] = []
        for cell in sorted(set(cells)):
            if cell[0] == cell[1]:
                times[cell] = self._estimate(cell, mode, "same_point", stats)
            else:
                pending.append(cell)

        pending = self._read_cache(pending, mode, times, stats)
        if pending:
            if not use_provider:
                self._estimate_all(pending, mode, "provider_not_asked", times, stats)
            elif not self._client.enabled:
                self._estimate_all(pending, mode, "adapter_disabled", times, stats)
            else:
                deadline = None if max_seconds is None else self._now() + max_seconds
                self._fetch(pending, mode, deadline, times, stats)
        log.info(
            "travel_times",
            mode=mode,
            cells=len(times),
            cache_hits=stats.cache_hits,
            provider_requests=stats.provider_requests,
            estimates=stats.estimates,
        )
        return TravelResult(times, stats)

    def route_geometry(self, a: Coord, b: Coord, mode: Mode) -> RouteGeometry | None:
        """The line to draw for one transfer of the selected itinerary. One route request; the
        answer is returned, never stored here. None if the provider cannot give it: no line is
        invented."""
        if a == b:
            return None
        result = self._client.route(a, b, mode, geometry=True)
        if result.state != "ok":
            return None
        return RouteGeometry(result.seconds, result.meters, result.geometry)

    # -- cache ---------------------------------------------------------------------------------

    def _read_cache(
        self,
        pending: list[Cell],
        mode: Mode,
        times: dict[Cell, TravelTime],
        stats: TravelStats,
    ) -> list[Cell]:
        if not pending or self._engine is None:
            return pending
        near = [c for c in pending if chunking.is_matrix_cell(*c)]
        far = [c for c in pending if not chunking.is_matrix_cell(*c)]
        try:
            with self._engine.begin() as conn:
                found = {
                    **repo.read(conn, near, mode, MATRIX_SHAPE),
                    **repo.read(conn, far, mode, ROUTE_SHAPE),
                }
        except SQLAlchemyError as exc:
            # Without the cache the provider could not be used responsibly either: estimate.
            log.warning("travel_cache_unavailable", error=type(exc).__name__)
            self._estimate_all(pending, mode, "cache_unavailable", times, stats)
            return []
        misses: list[Cell] = []
        for cell in pending:
            row = found.get(cell)
            if row is None:
                misses.append(cell)
            elif row.confidence == "routed" and row.seconds is not None and row.meters is not None:
                stats.cache_hits += 1
                times[cell] = TravelTime(
                    row.seconds, row.meters, "routed", "cache", algorithm=row.algorithm
                )
            else:
                stats.cache_hits += 1
                times[cell] = self._estimate(cell, mode, "no_route", stats)
        return misses

    # -- provider ------------------------------------------------------------------------------

    def _fetch(
        self,
        misses: list[Cell],
        mode: Mode,
        deadline: float | None,
        times: dict[Cell, TravelTime],
        stats: TravelStats,
    ) -> None:
        matrices, routes = chunking.plan(misses)
        stop: EstimateReason | None = None
        for request in matrices:
            cells = [(request.source, t) for t in request.targets]
            stop = stop or self._time_limit(deadline)
            if stop is not None:
                self._estimate_all(cells, mode, stop, times, stats)
                continue
            stats.provider_requests += 1
            result = self._client.matrix_row(request.source, list(request.targets), mode)
            if result.state != "ok":
                stop = _STATE_REASON[result.state]
                self._estimate_all(cells, mode, stop, times, stats)
                continue
            routed: list[repo.RoutedWrite] = []
            no_route: list[Cell] = []
            for cell, item in zip(cells, result.cells, strict=True):
                if (
                    item.seconds is None
                    or item.meters is None
                    or (
                        item.seconds == 0
                        and item.meters == 0
                        and distance_m(*cell) > ZERO_IS_NOT_A_ROUTE_BEYOND_M
                    )
                ):
                    no_route.append(cell)
                    times[cell] = self._estimate(cell, mode, "no_route", stats)
                else:
                    routed.append(
                        repo.RoutedWrite(cell, item.seconds, item.meters, result.algorithm)
                    )
                    times[cell] = TravelTime(
                        item.seconds,
                        item.meters,
                        "routed",
                        "provider",
                        algorithm=result.algorithm,
                    )
            assert result.response_date is not None  # noqa: S101
            self._store(
                MATRIX_SHAPE, mode, result.response_date, routed, no_route, result.algorithm
            )
        for leg in routes:
            cell = (leg.origin, leg.destination)
            stop = stop or self._time_limit(deadline)
            if stop is not None:
                self._estimate_all([cell], mode, stop, times, stats)
                continue
            stats.provider_requests += 1
            route = self._client.route(leg.origin, leg.destination, mode)
            if route.state != "ok":
                stop = _STATE_REASON[route.state]
                self._estimate_all([cell], mode, stop, times, stats)
                continue
            times[cell] = TravelTime(route.seconds, route.meters, "routed", "provider")
            assert route.response_date is not None  # noqa: S101
            self._store(
                ROUTE_SHAPE,
                mode,
                route.response_date,
                [repo.RoutedWrite(cell, route.seconds, route.meters, None)],
                [],
                None,
            )

    def _time_limit(self, deadline: float | None) -> EstimateReason | None:
        if deadline is not None and self._now() >= deadline:
            return "time_limit"
        return None

    def _store(
        self,
        shape: str,
        mode: Mode,
        response_date: datetime,
        routed: list[repo.RoutedWrite],
        no_route: list[Cell],
        algorithm: str | None,
    ) -> None:
        if self._engine is None:
            return
        try:
            with self._engine.begin() as conn:
                repo.write_routed(conn, routed, mode, shape, PROVIDER, response_date)
                repo.write_no_route(
                    conn,
                    no_route,
                    mode,
                    shape,
                    PROVIDER,
                    response_date,
                    self._settings.routing_no_route_retry_days,
                    algorithm,
                )
                repo.evict_oldest(conn, self._settings.routing_cache_max_rows)
        except SQLAlchemyError as exc:
            # The answers are still returned to the caller; they are just not kept.
            log.warning("travel_cache_write_failed", error=type(exc).__name__)

    # -- estimates -----------------------------------------------------------------------------

    def _estimate(
        self, cell: Cell, mode: Mode, reason: EstimateReason, stats: TravelStats
    ) -> TravelTime:
        stats.count_estimate(reason)
        return estimated(cell[0], cell[1], mode, reason)

    def _estimate_all(
        self,
        cells: Iterable[Cell],
        mode: Mode,
        reason: EstimateReason,
        times: dict[Cell, TravelTime],
        stats: TravelStats,
    ) -> None:
        for cell in cells:
            times[cell] = self._estimate(cell, mode, reason, stats)
