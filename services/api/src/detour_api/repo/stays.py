"""Stays: where the traveller sleeps, per range of days of a trip (ADR 030)."""

import uuid
from typing import Any

from sqlalchemy import Connection, text

from detour_api.errors import conflict, invalid, not_found
from detour_api.models.trips import Day, Itinerary, Stay, StayCreate, StayStart, StayUpdate
from detour_api.planner.config import DEFAULT_CONFIG
from detour_api.planner.travel import ServiceTravelSource, TravelLookup, minutes
from detour_api.planner.types import Leg
from detour_api.repo import trips
from detour_api.travel.service import TravelTimeService
from detour_api.travel.types import Coord

MAX_STAYS = 30
_COLUMNS = "id, trip_id, name, lat, lon, first_day, last_day, created_at"


def _stay(row: Any) -> Stay:
    return Stay(
        id=row.id,
        trip_id=row.trip_id,
        name=row.name,
        lat=row.lat,
        lon=row.lon,
        first_day=row.first_day,
        last_day=row.last_day,
        created_at=row.created_at,
    )


def list_for_trip(conn: Connection, trip_id: uuid.UUID) -> list[Stay]:
    rows = conn.execute(
        text(f"SELECT {_COLUMNS} FROM app.trip_stay WHERE trip_id = :t ORDER BY first_day, id"),
        {"t": trip_id},
    ).all()
    return [_stay(r) for r in rows]


def list_all(conn: Connection, installation_id: uuid.UUID, trip_id: uuid.UUID) -> list[Stay]:
    trips.require_trip(conn, installation_id, trip_id)
    return list_for_trip(conn, trip_id)


def _check(first: int, last: int, days: int, others: list[Stay], own: uuid.UUID | None) -> None:
    if last < first:
        raise invalid("bad_day_range", "last_day cannot be before first_day")
    if last > days:
        raise invalid("day_out_of_range", f"The trip has {days} days")
    for o in others:
        if o.id != own and first <= o.last_day and o.first_day <= last:
            raise conflict(
                "stay_overlap", f"Days {o.first_day} to {o.last_day} already have a stay"
            )


def _editable(conn: Connection, installation_id: uuid.UUID, trip_id: uuid.UUID) -> int:
    trip = trips.require_open_trip(conn, installation_id, trip_id)
    return trip.duration_days


def create(
    conn: Connection, installation_id: uuid.UUID, trip_id: uuid.UUID, body: StayCreate
) -> Stay:
    days = _editable(conn, installation_id, trip_id)
    existing = list_for_trip(conn, trip_id)
    if len(existing) >= MAX_STAYS:
        raise conflict("too_many_stays", f"A trip has at most {MAX_STAYS} stays")
    _check(body.first_day, body.last_day, days, existing, None)
    stay_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO app.trip_stay (id, trip_id, name, lat, lon, first_day, last_day)"
            " VALUES (:i, :t, :n, :lat, :lon, :f, :l)"
        ),
        {
            "i": stay_id,
            "t": trip_id,
            "n": body.name.strip(),
            "lat": body.lat,
            "lon": body.lon,
            "f": body.first_day,
            "l": body.last_day,
        },
    )
    return require(conn, installation_id, trip_id, stay_id)


def require(
    conn: Connection, installation_id: uuid.UUID, trip_id: uuid.UUID, stay_id: uuid.UUID
) -> Stay:
    trips.require_trip(conn, installation_id, trip_id)
    row = conn.execute(
        text(f"SELECT {_COLUMNS} FROM app.trip_stay WHERE id = :i AND trip_id = :t"),
        {"i": stay_id, "t": trip_id},
    ).first()
    if row is None:
        raise not_found("stay")
    return _stay(row)


def update(
    conn: Connection,
    installation_id: uuid.UUID,
    trip_id: uuid.UUID,
    stay_id: uuid.UUID,
    body: StayUpdate,
) -> Stay:
    days = _editable(conn, installation_id, trip_id)
    current = require(conn, installation_id, trip_id, stay_id)
    changed = body.model_fields_set
    if {"name", "lat", "lon", "first_day", "last_day"} & changed and any(
        getattr(body, f) is None for f in changed
    ):
        raise invalid("stay_field_required", "A stay's fields cannot be cleared")
    first = body.first_day if body.first_day is not None else current.first_day
    last = body.last_day if body.last_day is not None else current.last_day
    merged: dict[str, Any] = {
        "name": body.name.strip() if body.name is not None else current.name,
        "lat": body.lat if body.lat is not None else current.lat,
        "lon": body.lon if body.lon is not None else current.lon,
        "f": first,
        "l": last,
    }
    _check(first, last, days, list_for_trip(conn, trip_id), stay_id)
    conn.execute(
        text(
            "UPDATE app.trip_stay SET name = :name, lat = :lat, lon = :lon, first_day = :f,"
            " last_day = :l WHERE id = :i"
        ),
        {**merged, "i": stay_id},
    )
    return require(conn, installation_id, trip_id, stay_id)


def delete(
    conn: Connection, installation_id: uuid.UUID, trip_id: uuid.UUID, stay_id: uuid.UUID
) -> None:
    _editable(conn, installation_id, trip_id)
    require(conn, installation_id, trip_id, stay_id)
    conn.execute(text("DELETE FROM app.trip_stay WHERE id = :i"), {"i": stay_id})


def stay_of_day(stays: list[Stay], day_index: int) -> Stay | None:
    for s in stays:
        if s.first_day <= day_index <= s.last_day:
            return s
    return None


def start_of(stay: Stay, first_item_id: uuid.UUID, leg: Any) -> StayStart:
    """A day's morning at its stay: ``leg`` is a ``planner.types.Leg`` to the first stop."""
    return StayStart(
        stay_id=stay.id,
        name=stay.name,
        lat=stay.lat,
        lon=stay.lon,
        to_item_id=first_item_id,
        mode=leg.mode,
        seconds=leg.seconds,
        meters=leg.meters,
        confidence=leg.confidence,
    )


def attach_starts(days: list[Day], stays: list[Stay], lookup: Any) -> None:
    """Fill ``Day.start`` from cached times and labelled estimates (never calls a provider).
    ``lookup`` is a ``TravelLookup`` already fetched for the cells in ``start_cells``."""
    for day in days:
        stay = stay_of_day(stays, day.day_index)
        first = next((i for i in day.items if i.lat is not None and i.lon is not None), None)
        if stay is None or first is None or first.lat is None or first.lon is None:
            continue
        a = Coord.from_degrees(stay.lat, stay.lon)
        b = Coord.from_degrees(first.lat, first.lon)
        t = lookup.get(a, b)
        leg = Leg(
            mode=lookup.mode(a, b),
            seconds=t.seconds,
            meters=t.meters,
            minutes=minutes(t.seconds),
            confidence=t.confidence,
            estimate_reason=t.reason,
        )
        day.start = start_of(stay, first.id, leg)


def start_cells(days: list[Day], stays: list[Stay]) -> list[Any]:
    cells = []
    for day in days:
        stay = stay_of_day(stays, day.day_index)
        first = next((i for i in day.items if i.lat is not None and i.lon is not None), None)
        if stay is None or first is None or first.lat is None or first.lon is None:
            continue
        cells.append(
            (Coord.from_degrees(stay.lat, stay.lon), Coord.from_degrees(first.lat, first.lon))
        )
    return cells


def with_starts(
    conn: Connection,
    installation_id: uuid.UUID,
    itinerary: Itinerary,
    travel: TravelTimeService,
) -> Itinerary:
    """The itinerary with each day's morning leg from its stay (ADR 030). Reads the cache only:
    a time not cached is a labelled estimate, so reading a plan never calls the routing provider."""
    stays = list_for_trip(conn, itinerary.trip_id)
    if not stays:
        return itinerary
    trip = trips.require_trip(conn, installation_id, itinerary.trip_id)
    cells = start_cells(itinerary.days, stays)
    if not cells:
        return itinerary
    lookup = TravelLookup(
        ServiceTravelSource(travel, max_seconds=0.0),
        DEFAULT_CONFIG.walk_max_m if trip.uses_car else 10**9,
    )
    lookup.fetch(cells, use_provider=False)
    attach_starts(itinerary.days, stays, lookup)
    return itinerary
