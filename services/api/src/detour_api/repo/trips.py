"""Trips, the past-trip archive (ADR 006) and installations."""

import uuid
from typing import Any

from sqlalchemy import Connection, text

from detour_api.errors import conflict, invalid, not_found
from detour_api.models.trips import (
    Destination,
    Trip,
    TripCreate,
    TripUpdate,
    TripVisit,
    end_date_of,
)

MAX_TRIPS_PER_INSTALLATION = 100

_TRIP_COLUMNS = """
    t.id, t.title, t.destination_kind, t.destination_ref, t.destination_name,
    ST_Y(t.destination_point) AS dlat, ST_X(t.destination_point) AS dlon, t.duration_days,
    t.start_date, t.selected_itinerary_id, t.status, t.archived_at, t.is_seed, t.created_at, t.updated_at
"""


def ensure_installation(conn: Connection, installation_id: uuid.UUID) -> None:
    """Create the installation row on first use and note when it was last seen (hourly)."""
    conn.execute(
        text(
            "INSERT INTO app.installation (id) VALUES (:i)"
            " ON CONFLICT (id) DO UPDATE SET last_seen_at = now()"
            " WHERE app.installation.last_seen_at < now() - interval '1 hour'"
        ),
        {"i": installation_id},
    )


def _trip(row: Any) -> Trip:
    return Trip(
        id=row.id,
        title=row.title,
        destination=Destination(
            kind=row.destination_kind,
            ref=row.destination_ref,
            name=row.destination_name,
            lat=row.dlat,
            lon=row.dlon,
        ),
        duration_days=row.duration_days,
        start_date=row.start_date,
        end_date=end_date_of(row.start_date, row.duration_days),
        selected_itinerary_id=row.selected_itinerary_id,
        status=row.status,
        archived_at=row.archived_at,
        is_seed=row.is_seed,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def get_trip(conn: Connection, installation_id: uuid.UUID, trip_id: uuid.UUID) -> Trip | None:
    row = conn.execute(
        text(f"SELECT {_TRIP_COLUMNS} FROM app.trip t WHERE t.id = :t AND t.installation_id = :i"),
        {"t": trip_id, "i": installation_id},
    ).first()
    return None if row is None else _trip(row)


def require_trip(conn: Connection, installation_id: uuid.UUID, trip_id: uuid.UUID) -> Trip:
    trip = get_trip(conn, installation_id, trip_id)
    if trip is None:
        raise not_found("trip")
    return trip


def list_trips(
    conn: Connection, installation_id: uuid.UUID, status: str | None = None
) -> list[Trip]:
    rows = conn.execute(
        text(
            f"SELECT {_TRIP_COLUMNS} FROM app.trip t WHERE t.installation_id = :i"
            " AND (CAST(:s AS text) IS NULL OR t.status = :s)"
            " ORDER BY t.created_at DESC, t.id"
        ),
        {"i": installation_id, "s": status},
    ).all()
    return [_trip(r) for r in rows]


def create_trip(
    conn: Connection,
    installation_id: uuid.UUID,
    body: TripCreate,
    *,
    destination_name: str,
    lat: float,
    lon: float,
    is_seed: bool = False,
) -> Trip:
    count = conn.execute(
        text("SELECT count(*) FROM app.trip WHERE installation_id = :i"), {"i": installation_id}
    ).scalar_one()
    if count >= MAX_TRIPS_PER_INSTALLATION:
        raise conflict(
            "limit_reached", f"at most {MAX_TRIPS_PER_INSTALLATION} trips per installation"
        )
    trip_id = uuid.uuid4()
    conn.execute(
        text(
            """
            INSERT INTO app.trip (id, installation_id, title, destination_kind, destination_ref,
                destination_name, destination_point, duration_days, start_date, is_seed)
            VALUES (:id, :inst, :title, :kind, :ref, :dname,
                ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), :days, :start, :seed)
            """
        ),
        {
            "id": trip_id,
            "inst": installation_id,
            "title": body.title,
            "kind": body.destination_kind,
            "ref": body.destination_ref,
            "dname": destination_name,
            "lat": lat,
            "lon": lon,
            "days": body.duration_days,
            "start": body.start_date,
            "seed": is_seed,
        },
    )
    return require_trip(conn, installation_id, trip_id)


def update_trip(
    conn: Connection, installation_id: uuid.UUID, trip_id: uuid.UUID, body: TripUpdate
) -> Trip:
    trip = require_trip(conn, installation_id, trip_id)
    if trip.status == "past":
        raise conflict("trip_archived", "a past trip cannot be changed")
    changed = body.model_fields_set
    sets: list[str] = []
    params: dict[str, Any] = {"t": trip_id, "i": installation_id}

    if "title" in changed:
        if body.title is None:
            raise invalid("title_required", "title cannot be cleared")
        sets.append("title = :title")
        params["title"] = body.title
    if "duration_days" in changed:
        if body.duration_days is None:
            raise invalid("duration_required", "duration_days cannot be cleared")
        if body.duration_days != trip.duration_days:
            has = conn.execute(
                text("SELECT 1 FROM app.itinerary WHERE trip_id = :t LIMIT 1"), {"t": trip_id}
            ).first()
            if has:
                raise conflict(
                    "has_itineraries",
                    "the number of days cannot change while the trip has itineraries",
                )
        sets.append("duration_days = :days")
        params["days"] = body.duration_days
    if "start_date" in changed:
        sets.append("start_date = :start")
        params["start"] = body.start_date
    if "selected_itinerary_id" in changed:
        _select_itinerary(conn, trip_id, body.selected_itinerary_id)
        sets.append("selected_itinerary_id = :sel")
        params["sel"] = body.selected_itinerary_id
    if sets:
        conn.execute(
            text(
                f"UPDATE app.trip SET {', '.join(sets)}, updated_at = now() WHERE id = :t AND installation_id = :i"
            ),
            params,
        )
    if "start_date" in changed:
        conn.execute(
            text(
                "UPDATE app.itinerary_day d SET date ="
                " CASE WHEN CAST(:s AS date) IS NULL THEN NULL"
                "      ELSE CAST(:s AS date) + (d.day_index - 1) END"
                " FROM app.itinerary it WHERE d.itinerary_id = it.id AND it.trip_id = :t"
            ),
            {"s": body.start_date, "t": trip_id},
        )
    return require_trip(conn, installation_id, trip_id)


def _select_itinerary(conn: Connection, trip_id: uuid.UUID, itinerary_id: uuid.UUID | None) -> None:
    if itinerary_id is not None:
        owned = conn.execute(
            text("SELECT 1 FROM app.itinerary WHERE id = :i AND trip_id = :t"),
            {"i": itinerary_id, "t": trip_id},
        ).first()
        if owned is None:
            raise invalid(
                "itinerary_not_in_trip", "selected_itinerary_id is not an itinerary of this trip"
            )
    conn.execute(
        text(
            "UPDATE app.itinerary SET status = 'proposed' WHERE trip_id = :t AND status = 'selected'"
        ),
        {"t": trip_id},
    )
    if itinerary_id is not None:
        conn.execute(
            text("UPDATE app.itinerary SET status = 'selected' WHERE id = :i"), {"i": itinerary_id}
        )


def delete_trip(conn: Connection, installation_id: uuid.UUID, trip_id: uuid.UUID) -> None:
    """Deletes the trip with its itineraries, days, items, transfers and archive rows.

    Price records stay (they belong to the installation); their link to an item is cleared.
    """
    result = conn.execute(
        text("DELETE FROM app.trip WHERE id = :t AND installation_id = :i"),
        {"t": trip_id, "i": installation_id},
    )
    if result.rowcount == 0:
        raise not_found("trip")


# -- archive (ADR 006) -------------------------------------------------------------------------


def archive_trip(conn: Connection, installation_id: uuid.UUID, trip_id: uuid.UUID) -> Trip:
    """Turn a trip into a past trip.

    Keeps one snapshot row per city and attraction of the *selected* itinerary; deletes every
    itinerary (and with them transfers, route geometry, versions and seeds). Prices untouched.
    """
    trip = require_trip(conn, installation_id, trip_id)
    if trip.status == "past":
        raise conflict("already_archived", "the trip is already a past trip")
    conn.execute(text("SELECT 1 FROM app.trip WHERE id = :t FOR UPDATE"), {"t": trip_id})

    visits: list[dict[str, Any]] = []
    if trip.selected_itinerary_id is not None:
        cities = conn.execute(
            text(
                """
                SELECT c.id, c.name, ST_Y(c.geom) lat, ST_X(c.geom) lon, min(d.day_index) AS day
                FROM app.itinerary_day d JOIN geo.city c ON c.id = d.base_city_id
                WHERE d.itinerary_id = :it GROUP BY c.id, c.name, c.geom
                ORDER BY min(d.day_index), c.id
                """
            ),
            {"it": trip.selected_itinerary_id},
        ).all()
        visits += [
            {
                "kind": "city",
                "name": c.name,
                "lat": c.lat,
                "lon": c.lon,
                "ref": f"city:{c.id}",
                "day": c.day,
            }
            for c in cities
        ]
        items = conn.execute(
            text(
                """
                SELECT d.day_index, i.position, i.display_name, i.place_id,
                       ST_Y(i.display_point) lat, ST_X(i.display_point) lon, up.kind AS up_kind
                FROM app.itinerary_item i
                JOIN app.itinerary_day d ON d.id = i.day_id
                LEFT JOIN app.user_place up ON up.id = i.user_place_id
                WHERE d.itinerary_id = :it AND i.type = 'visit' AND i.display_point IS NOT NULL
                ORDER BY d.day_index, i.position
                """
            ),
            {"it": trip.selected_itinerary_id},
        ).all()
        for it in items:
            visits.append(
                {
                    "kind": "city" if it.up_kind == "city" else "attraction",
                    "name": it.display_name,
                    "lat": it.lat,
                    "lon": it.lon,
                    "ref": None if it.place_id is None else str(it.place_id),
                    "day": it.day_index,
                }
            )
    if not any(v["kind"] == "city" for v in visits) and trip.destination.kind == "city":
        visits.insert(
            0,
            {
                "kind": "city",
                "name": trip.destination.name,
                "lat": trip.destination.lat,
                "lon": trip.destination.lon,
                "ref": f"city:{trip.destination.ref}",
                "day": 1,
            },
        )
    for v in visits:
        conn.execute(
            text(
                "INSERT INTO app.trip_visit (id, trip_id, kind, name, point, geo_place_ref,"
                " day_number) VALUES (:id, :t, :k, :n, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326),"
                " :ref, :d)"
            ),
            {
                "id": uuid.uuid4(),
                "t": trip_id,
                "k": v["kind"],
                "n": v["name"],
                "lon": v["lon"],
                "lat": v["lat"],
                "ref": v["ref"],
                "d": v["day"],
            },
        )
    conn.execute(
        text("UPDATE app.trip SET selected_itinerary_id = NULL WHERE id = :t"), {"t": trip_id}
    )
    conn.execute(text("DELETE FROM app.itinerary WHERE trip_id = :t"), {"t": trip_id})
    conn.execute(
        text(
            "UPDATE app.trip SET status = 'past', archived_at = now(), updated_at = now() WHERE id = :t"
        ),
        {"t": trip_id},
    )
    return require_trip(conn, installation_id, trip_id)


def list_visits(
    conn: Connection, installation_id: uuid.UUID, trip_id: uuid.UUID
) -> list[TripVisit]:
    require_trip(conn, installation_id, trip_id)
    rows = conn.execute(
        text(
            "SELECT id, kind, name, ST_Y(point) lat, ST_X(point) lon, geo_place_ref, day_number,"
            " confirmed FROM app.trip_visit WHERE trip_id = :t ORDER BY day_number, (kind = 'city') DESC, name, id"
        ),
        {"t": trip_id},
    ).all()
    return [
        TripVisit(
            id=r.id,
            kind=r.kind,
            name=r.name,
            lat=r.lat,
            lon=r.lon,
            geo_place_ref=r.geo_place_ref,
            day_number=r.day_number,
            confirmed=r.confirmed,
        )
        for r in rows
    ]


def set_visit_confirmed(
    conn: Connection,
    installation_id: uuid.UUID,
    trip_id: uuid.UUID,
    visit_id: uuid.UUID,
    confirmed: bool,
) -> TripVisit:
    require_trip(conn, installation_id, trip_id)
    result = conn.execute(
        text("UPDATE app.trip_visit SET confirmed = :c WHERE id = :v AND trip_id = :t"),
        {"c": confirmed, "v": visit_id, "t": trip_id},
    )
    if result.rowcount == 0:
        raise not_found("visit")
    return next(v for v in list_visits(conn, installation_id, trip_id) if v.id == visit_id)
