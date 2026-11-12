"""FOSSGIS Valhalla routing adapter (ADR 004, ADR 013).

The only routing provider. It is called from the backend only, through this class, which provides
what architecture section 6 requires of every provider:

* an identifying ``User-Agent`` and an ``X-Client-Id`` header naming the project (ADR 004),
* a timeout,
* a token bucket (1 call per second sustained, bursts of 10), a circuit breaker that opens after
  any 429, error response, timeout or unreadable body, and a daily budget in
  ``app.provider_usage`` reserved before each call,
* a fallback: every failure becomes a ``state`` in the result, never an exception, so the
  travel-time service falls back to a labelled estimate. There is no second provider.

Caching lives in the service, not here. Tests never reach the server: only an injected transport
enables the adapter when ``environment`` is ``test``.

**One fixed request shape** (ADR 013). The same pair returned 523 s in two matrix requests and
653 s in a third (``docs/spikes/fossgis-matrix-check.md``), cause unknown. So:

* ``matrix-v1``: always one source and 1 to 100 targets (``sources_to_targets``), JSON body with
  exactly ``sources``, ``targets`` and ``costing``, coordinates rounded to 1e-5 degree. Valhalla
  chooses its matrix algorithm itself and no request option selects it; fixing the counts at
  1 x N keeps every cell on the same kind of request, and the algorithm named in each response is
  stored with the cell.
* ``route-v1``: ``route`` with two locations and ``costing``, used for legs beyond the matrix
  distance limit and for the geometry of a selected itinerary.

Response formats follow real responses the owner recorded on 2026-11-12
(``tests/fixtures/valhalla/*-recorded.json``): ``sources_to_targets`` with ``distance`` in
kilometres and integer ``time`` in seconds, ``trip.summary.length`` and a fractional ``.time``, an
encoded polyline with six decimals. Still **unverified** (ADR 013): the shape of a null cell, and
that ``POST`` is accepted (the owner's checks used ``GET``). The parsers accept the null variants
listed in ADR 013 and refuse anything else.
"""

import json
import math
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Literal

import httpx
import structlog
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from detour_api.adapters.budget import reserve_call
from detour_api.adapters.ratelimit import CircuitBreaker, Clock, Sleeper, TokenBucket
from detour_api.settings import Settings
from detour_api.travel.types import Coord, Mode

log = structlog.get_logger("detour.valhalla")

PROVIDER = "fossgis-valhalla"
MATRIX_SHAPE = "matrix-v1"
ROUTE_SHAPE = "route-v1"

# Limits measured by the owner on 2026-11-12 (ADR 004).
MATRIX_MAX_CELLS = 100
# 150 km is the server's limit on the distance between a source and a target. A margin keeps a
# pair that the server measures slightly differently from being refused (and opening the breaker).
MATRIX_MAX_METERS = 148_500

COSTING: dict[Mode, str] = {"walk": "pedestrian", "drive": "auto"}

State = Literal["ok", "disabled", "unavailable", "budget_exhausted", "rate_limited"]


@dataclass(frozen=True)
class MatrixCell:
    """``seconds`` and ``meters`` are None when the provider has no route for the cell."""

    seconds: int | None
    meters: int | None


@dataclass
class MatrixResult:
    state: State
    cells: list[MatrixCell] = field(default_factory=list)
    algorithm: str | None = None
    response_date: datetime | None = None


@dataclass
class RouteResult:
    state: State
    seconds: int = 0
    meters: int = 0
    response_date: datetime | None = None
    geometry: list[tuple[float, float]] = field(default_factory=list)


# -- parsing ------------------------------------------------------------------------------------


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    return number if math.isfinite(number) and number >= 0 else None


def parse_matrix(payload: Any, targets: int) -> tuple[list[MatrixCell], str | None]:
    """Read a one-source ``sources_to_targets`` answer. A cell that is null, or has no usable
    ``time`` and ``distance``, is a null cell; a structure that is not what was asked for
    raises ``ValueError``."""
    if not isinstance(payload, dict):
        raise ValueError("matrix response is not an object")
    units = payload.get("units")
    if units is not None and units != "kilometers":
        raise ValueError("matrix response is not in kilometres")
    rows = payload.get("sources_to_targets")
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], list):
        raise ValueError("matrix response does not have one source row")
    row = rows[0]
    if len(row) != targets:
        raise ValueError("matrix response has the wrong number of targets")
    cells: list[MatrixCell] = []
    for index, item in enumerate(row):
        if isinstance(item, dict):
            to_index = item.get("to_index")
            from_index = item.get("from_index")
            if to_index is not None and to_index != index:
                raise ValueError("matrix cell out of order")
            if from_index is not None and from_index != 0:
                raise ValueError("matrix cell from an unexpected source")
            seconds, kilometres = _number(item.get("time")), _number(item.get("distance"))
            if seconds is None or kilometres is None:
                cells.append(MatrixCell(None, None))
            else:
                cells.append(MatrixCell(round(seconds), round(kilometres * 1000)))
        elif item is None:
            cells.append(MatrixCell(None, None))
        else:
            raise ValueError("matrix cell is neither an object nor null")
    algorithm = payload.get("algorithm")
    return cells, algorithm if isinstance(algorithm, str) and algorithm else None


def decode_polyline6(encoded: str) -> list[tuple[float, float]]:
    """Decode an encoded polyline with six decimals into ``(lat, lon)`` pairs."""
    coords: list[tuple[float, float]] = []
    index = lat = lon = 0
    length = len(encoded)
    while index < length:
        pair: list[int] = []
        for _ in range(2):
            shift = result = 0
            while True:
                if index >= length:
                    raise ValueError("truncated polyline")
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            pair.append(~(result >> 1) if result & 1 else result >> 1)
        lat += pair[0]
        lon += pair[1]
        point = (lat / 1e6, lon / 1e6)
        if not (-90 <= point[0] <= 90 and -180 <= point[1] <= 180):
            raise ValueError("polyline point out of range")
        coords.append(point)
    return coords


def parse_route(payload: Any, *, with_geometry: bool) -> tuple[int, int, list[tuple[float, float]]]:
    """Read ``trip.summary`` (``time`` in seconds, ``length`` in kilometres) and, if asked, the
    legs' encoded shapes."""
    trip = payload.get("trip") if isinstance(payload, dict) else None
    summary = trip.get("summary") if isinstance(trip, dict) else None
    if not isinstance(trip, dict) or not isinstance(summary, dict):
        raise ValueError("route response has no trip summary")
    units = trip.get("units")
    if units is not None and units != "kilometers":
        raise ValueError("route response is not in kilometres")
    seconds, kilometres = _number(summary.get("time")), _number(summary.get("length"))
    if seconds is None or kilometres is None:
        raise ValueError("route summary has no usable time and length")
    geometry: list[tuple[float, float]] = []
    if with_geometry:
        legs = trip.get("legs")
        if not isinstance(legs, list) or not legs:
            raise ValueError("route response has no legs")
        for leg in legs:
            shape = leg.get("shape") if isinstance(leg, dict) else None
            if not isinstance(shape, str) or not shape:
                raise ValueError("route leg has no shape")
            geometry.extend(decode_polyline6(shape))
    return round(seconds), round(kilometres * 1000), geometry


def _response_date(response: httpx.Response) -> datetime:
    header = response.headers.get("date")
    if header:
        try:
            parsed = parsedate_to_datetime(header)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except (TypeError, ValueError):
            pass
    return datetime.now(UTC)


def _location(point: Coord) -> dict[str, float]:
    return {"lat": point.lat, "lon": point.lon}


# -- the client ---------------------------------------------------------------------------------


class ValhallaClient:
    def __init__(
        self,
        settings: Settings,
        engine: Engine | None,
        transport: httpx.BaseTransport | None = None,
        *,
        now: Clock | None = None,
        sleep: Sleeper | None = None,
    ) -> None:
        self._settings = settings
        self._engine = engine
        self._transport = transport
        now_fn: Clock = now if now is not None else time.monotonic
        sleep_fn: Sleeper = sleep if sleep is not None else time.sleep
        self.limiter = TokenBucket(
            settings.routing_rate_per_second, settings.routing_burst, now=now_fn, sleep=sleep_fn
        )
        self.breaker = CircuitBreaker(now=now_fn)
        # Tests must never reach the network: only an injected transport enables the adapter
        # there. Without a database there is no daily budget, so no calls are made either.
        self.enabled = (
            settings.routing_enabled
            and engine is not None
            and (settings.environment != "test" or transport is not None)
        )

    # -- the two requests ------------------------------------------------------------------

    def matrix_row(self, source: Coord, targets: list[Coord], mode: Mode) -> MatrixResult:
        """Times from one source to 1 to 100 targets, all within the matrix distance limit."""
        if not 1 <= len(targets) <= MATRIX_MAX_CELLS:
            raise ValueError("a matrix request has 1 to 100 targets")
        body = {
            "sources": [_location(source)],
            "targets": [_location(t) for t in targets],
            "costing": COSTING[mode],
        }
        outcome = self._post("/sources_to_targets", body)
        if isinstance(outcome, str):
            return MatrixResult(outcome)
        try:
            cells, algorithm = parse_matrix(self._json(outcome), len(targets))
        except ValueError as exc:
            return self._unreadable(exc, MatrixResult("unavailable"))
        self.breaker.record_success()
        return MatrixResult("ok", cells, algorithm, _response_date(outcome))

    def route(
        self, origin: Coord, destination: Coord, mode: Mode, *, geometry: bool = False
    ) -> RouteResult:
        """One route between two places: the time of a long leg, or the geometry of a selected
        itinerary (never cached or archived, ADR 006)."""
        body: dict[str, Any] = {
            "locations": [_location(origin), _location(destination)],
            "costing": COSTING[mode],
        }
        if self._settings.routing_slim_route_requests:
            # Checked by the owner on 2026-11-12 (ADR 013): this drops the turn-by-turn
            # maneuvers (a 662 m walk went from 2,214 to 896 bytes). ``shape_format: no_shape``
            # was also tried and did NOT remove the shape, so it is not sent.
            body["directions_type"] = "none"
        outcome = self._post("/route", body)
        if isinstance(outcome, str):
            return RouteResult(outcome)
        try:
            seconds, meters, shape = parse_route(self._json(outcome), with_geometry=geometry)
        except ValueError as exc:
            return self._unreadable(exc, RouteResult("unavailable"))
        self.breaker.record_success()
        return RouteResult("ok", seconds, meters, _response_date(outcome), shape)

    # -- the safety chain ----------------------------------------------------------------------

    def _post(self, path: str, body: dict[str, Any]) -> httpx.Response | State:
        """Breaker, then rate limit, then daily budget, then the call. Returns the successful
        response, or the state that stopped or failed the call."""
        if not self.enabled or self._engine is None:
            return "disabled"
        if not self.breaker.allow():
            return "unavailable"
        if not self.limiter.acquire(self._settings.routing_max_wait_seconds):
            self.breaker.cancel_probe()
            return "rate_limited"
        try:
            reserved = reserve_call(self._engine, PROVIDER, self._settings.routing_daily_budget)
        except SQLAlchemyError as exc:
            self.breaker.cancel_probe()
            log.warning("routing_budget_check_failed", error=type(exc).__name__)
            return "unavailable"
        if not reserved:
            self.breaker.cancel_probe()
            log.warning("routing_budget_exhausted", budget=self._settings.routing_daily_budget)
            return "budget_exhausted"
        try:
            with httpx.Client(
                base_url=self._settings.routing_base_url,
                headers={
                    "User-Agent": self._settings.routing_user_agent,
                    "X-Client-Id": self._settings.routing_client_id,
                },
                timeout=self._settings.routing_timeout_seconds,
                transport=self._transport,
            ) as client:
                response = client.post(path, json=body)
        except httpx.HTTPError as exc:
            self.breaker.record_failure()
            log.warning("routing_unavailable", error=type(exc).__name__, path=path)
            return "unavailable"
        if response.status_code == 429:
            retry_after = _retry_after(response)
            self.breaker.record_failure(rate_limited=True, retry_after=retry_after)
            log.warning("routing_rate_limited", path=path, retry_after=retry_after)
            return "unavailable"
        if response.status_code != 200:
            self.breaker.record_failure()
            log.warning(
                "routing_error_response",
                status=response.status_code,
                error_code=_error_code(response),
                path=path,
            )
            return "unavailable"
        return response

    def _json(self, response: httpx.Response) -> Any:
        try:
            return response.json()
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("response is not JSON") from exc

    def _unreadable[R](self, exc: ValueError, result: R) -> R:
        self.breaker.record_failure()
        log.warning("routing_unreadable_response", error=str(exc))
        return result


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def _error_code(response: httpx.Response) -> int | None:
    try:
        code = response.json().get("error_code")
    except (ValueError, AttributeError):
        return None
    return code if isinstance(code, int) else None
