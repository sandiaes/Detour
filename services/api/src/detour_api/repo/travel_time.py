"""SQL for the travel-time cache, ``geo.travel_time`` (ADR 013). Bound parameters only."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Connection, text

from detour_api.travel.types import Coord, Mode

Cell = tuple[Coord, Coord]


@dataclass(frozen=True)
class CachedRow:
    confidence: str
    seconds: int | None
    meters: int | None
    algorithm: str | None


@dataclass(frozen=True)
class RoutedWrite:
    cell: Cell
    seconds: int
    meters: int
    algorithm: str | None


def read(conn: Connection, cells: Sequence[Cell], mode: Mode, shape: str) -> dict[Cell, CachedRow]:
    """Valid rows for the cells: routed rows always, estimated (no-route) rows until they
    expire. One query for all cells."""
    if not cells:
        return {}
    rows = conn.execute(
        text(
            "SELECT q.i, t.confidence, t.seconds, t.meters, t.algorithm"
            " FROM unnest(CAST(:flat AS integer[]), CAST(:flon AS integer[]),"
            "              CAST(:tlat AS integer[]), CAST(:tlon AS integer[]))"
            "      WITH ORDINALITY AS q(flat, flon, tlat, tlon, i)"
            " JOIN geo.travel_time t ON t.from_lat = q.flat AND t.from_lon = q.flon"
            "  AND t.to_lat = q.tlat AND t.to_lon = q.tlon"
            "  AND t.mode = :mode AND t.request_shape = :shape"
            " WHERE t.retry_after IS NULL OR t.retry_after > now()"
        ),
        {
            "flat": [a.lat_e5 for a, _ in cells],
            "flon": [a.lon_e5 for a, _ in cells],
            "tlat": [b.lat_e5 for _, b in cells],
            "tlon": [b.lon_e5 for _, b in cells],
            "mode": mode,
            "shape": shape,
        },
    ).all()
    return {cells[i - 1]: CachedRow(c, s, m, alg) for i, c, s, m, alg in rows}


_UPSERT = (
    "INSERT INTO geo.travel_time (from_lat, from_lon, to_lat, to_lon, mode, request_shape,"
    " provider, confidence, seconds, meters, algorithm, response_date, retry_after)"
    " VALUES (:flat, :flon, :tlat, :tlon, :mode, :shape, :provider, :confidence, :seconds,"
    " :meters, :algorithm, :response_date, {retry})"
    " ON CONFLICT (from_lat, from_lon, to_lat, to_lon, mode, request_shape) DO UPDATE SET"
    " provider = EXCLUDED.provider, confidence = EXCLUDED.confidence, seconds = EXCLUDED.seconds,"
    " meters = EXCLUDED.meters, algorithm = EXCLUDED.algorithm,"
    " response_date = EXCLUDED.response_date, retry_after = EXCLUDED.retry_after"
)


def _key(cell: Cell, mode: Mode, shape: str, provider: str) -> dict[str, object]:
    a, b = cell
    return {
        "flat": a.lat_e5,
        "flon": a.lon_e5,
        "tlat": b.lat_e5,
        "tlon": b.lon_e5,
        "mode": mode,
        "shape": shape,
        "provider": provider,
    }


def write_routed(
    conn: Connection,
    rows: Sequence[RoutedWrite],
    mode: Mode,
    shape: str,
    provider: str,
    response_date: datetime,
) -> None:
    if not rows:
        return
    conn.execute(
        text(_UPSERT.format(retry="NULL")),
        [
            {
                **_key(r.cell, mode, shape, provider),
                "confidence": "routed",
                "seconds": r.seconds,
                "meters": r.meters,
                "algorithm": r.algorithm,
                "response_date": response_date,
            }
            for r in rows
        ],
    )


def write_no_route(
    conn: Connection,
    cells: Sequence[Cell],
    mode: Mode,
    shape: str,
    provider: str,
    response_date: datetime,
    retry_days: int,
    algorithm: str | None,
) -> None:
    """Remember that the provider had no route for these cells (an estimated row: no number is
    stored, the estimate is computed on read). Not asked again until ``retry_days`` have passed."""
    if not cells:
        return
    conn.execute(
        text(_UPSERT.format(retry="now() + make_interval(days => :retry_days)")),
        [
            {
                **_key(cell, mode, shape, provider),
                "confidence": "estimated",
                "seconds": None,
                "meters": None,
                "algorithm": algorithm,
                "response_date": response_date,
                "retry_days": retry_days,
            }
            for cell in cells
        ],
    )


def evict_oldest(conn: Connection, max_rows: int) -> int:
    """Keep the table at most ``max_rows`` rows (it counts toward ADR 009 gate 6): delete the
    oldest responses first. Returns the number deleted."""
    result = conn.execute(
        text(
            "DELETE FROM geo.travel_time WHERE ctid IN ("
            " SELECT ctid FROM geo.travel_time ORDER BY response_date, from_lat, from_lon,"
            " to_lat, to_lon LIMIT GREATEST(0, (SELECT count(*) FROM geo.travel_time) - :max))"
        ),
        {"max": max_rows},
    )
    return result.rowcount
