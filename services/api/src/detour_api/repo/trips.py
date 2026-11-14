"""Trips, the past-trip archive (ADR 006) and installations."""

import uuid
from datetime import UTC, date, datetime
from typing import Any

import structlog
from sqlalchemy import Connection, text

from detour_api.errors import conflict, invalid, not_found
from detour_api.models.images import Photo
from detour_api.models.trips import (
    ArchiveInfo,
    Destination,
    Trip,
    TripCreate,
    TripStop,
    TripUpdate,
    TripVisit,
    end_date_of,
)
from detour_api.repo import images

MAX_TRIPS_PER_INSTALLATION = 100

_TRIP_COLUMNS = """
    t.id, t.title, t.destination_kind, t.destination_ref, t.destination_name,
    ST_Y(t.destination_point) AS dlat, ST_X(t.destination_point) AS dlon, t.duration_days,
    t.start_date, t.selected_itinerary_id, t.status, t.archived_at, t.is_seed, t.created_at, t.updated_at,
    t.stops_version
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


def trip_stops(conn: Connection, trip_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[TripStop]]:
    """The stops of multi-city trips, in order (ADR 024)."""
    if not trip_ids:
        return {}
    rows = conn.execute(
        text(
            "SELECT trip_id, position, city_id, city_name, country_iso2, ST_Y(point) AS lat,"
            " ST_X(point) AS lon, days FROM app.trip_stop"
            " WHERE trip_id = ANY(CAST(:ids AS uuid[])) ORDER BY trip_id, position"
        ),
        {"ids": [str(t) for t in trip_ids]},
    ).all()
    out: dict[uuid.UUID, list[TripStop]] = {}
    for r in rows:
        out.setdefault(r.trip_id, []).append(
            TripStop(
                position=r.position,
                city_id=r.city_id,
                name=r.city_name,
                country_iso2=r.country_iso2,
                lat=r.lat,
                lon=r.lon,
                days=r.days,
            )
        )
    return out


def _trip(row: Any, cover: Photo | None = None, stops: list[TripStop] | None = None) -> Trip:
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
        cover_image=cover,
        stops=stops or [],
        stops_version=row.stops_version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def get_trip(conn: Connection, installation_id: uuid.UUID, trip_id: uuid.UUID) -> Trip | None:
    row = conn.execute(
        text(f"SELECT {_TRIP_COLUMNS} FROM app.trip t WHERE t.id = :t AND t.installation_id = :i"),
        {"t": trip_id, "i": installation_id},
    ).first()
    if row is None:
        return None
    stops = trip_stops(conn, [row.id]) if row.destination_kind == "route" else {}
    return _trip(row, images.trip_covers(conn, [row.id]).get(row.id), stops.get(row.id))


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
    covers = images.trip_covers(conn, [r.id for r in rows])
    stops = trip_stops(conn, [r.id for r in rows if r.destination_kind == "route"])
    return [_trip(r, covers.get(r.id), stops.get(r.id)) for r in rows]


def create_trip(
    conn: Connection,
    installation_id: uuid.UUID,
    body: TripCreate,
    *,
    destination_name: str,
    lat: float,
    lon: float,
    is_seed: bool = False,
    stops: "list[ResolvedStop] | None" = None,
    title: str | None = None,
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
            "title": title or body.title,
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
    if stops:
        write_stops(conn, trip_id, stops)
    return require_trip(conn, installation_id, trip_id)


class ResolvedStop:
    """A stop checked against the gazetteer: its snapshot as stored."""

    def __init__(
        self, city_id: int, name: str, country_iso2: str | None, lat: float, lon: float, days: int
    ) -> None:
        self.city_id = city_id
        self.name = name
        self.country_iso2 = country_iso2
        self.lat = lat
        self.lon = lon
        self.days = days


def write_stops(conn: Connection, trip_id: uuid.UUID, stops: list[ResolvedStop]) -> None:
    """Replace a trip's stops with these, in order."""
    conn.execute(text("DELETE FROM app.trip_stop WHERE trip_id = :t"), {"t": trip_id})
    for position, s in enumerate(stops, start=1):
        conn.execute(
            text(
                "INSERT INTO app.trip_stop (id, trip_id, position, city_id, city_name,"
                " country_iso2, point, days) VALUES (:id, :t, :p, :c, :n, :iso,"
                " ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), :d)"
            ),
            {
                "id": uuid.uuid4(),
                "t": trip_id,
                "p": position,
                "c": s.city_id,
                "n": s.name,
                "iso": s.country_iso2,
                "lat": s.lat,
                "lon": s.lon,
                "d": s.days,
            },
        )


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
            text(
                "SELECT it.stops_version, t.stops_version AS trip_version, t.destination_kind"
                " FROM app.itinerary it JOIN app.trip t ON t.id = it.trip_id"
                " WHERE it.id = :i AND it.trip_id = :t"
            ),
            {"i": itinerary_id, "t": trip_id},
        ).first()
        if owned is None:
            raise invalid(
                "itinerary_not_in_trip", "selected_itinerary_id is not an itinerary of this trip"
            )
        # A plan made for a multi-city trip's earlier stops cannot be chosen (ADR 024).
        if owned.destination_kind == "route" and (owned.stops_version or 0) != owned.trip_version:
            raise conflict(
                "stops_changed", "this plan was made for the trip's earlier cities; make new ones"
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
    """Deletes the trip with its itineraries, days, items, transfers and archive rows. User places
    stay (they belong to the installation)."""
    result = conn.execute(
        text("DELETE FROM app.trip WHERE id = :t AND installation_id = :i"),
        {"t": trip_id, "i": installation_id},
    )
    if result.rowcount == 0:
        raise not_found("trip")


# -- archive (ADR 006) -------------------------------------------------------------------------

# A trip becomes past by itself this many days after its last day. The last day is a calendar date
# without a time zone and trips are anywhere on Earth, so two days make sure that day is over
# everywhere (UTC-12 to UTC+14) before anything is deleted.
AUTO_ARCHIVE_GRACE_DAYS = 2

log = structlog.get_logger("detour.archive")


def today_utc() -> date:
    return datetime.now(UTC).date()


def _collect_visits(conn: Connection, trip: Trip) -> list[dict[str, Any]]:
    """The day record of the selected itinerary, as snapshots (ADR 026): every stop with its day,
    order, start and length, the user's restaurants and cafes included; free time is not a stop.
    Each base city is listed once, however many days are spent there, without a time."""
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
                "position": None,
                "start": None,
                "minutes": None,
            }
            for c in cities
        ]
        items = conn.execute(
            text(
                """
                SELECT d.day_index, i.position, i.display_name, i.place_id, i.type,
                       i.start_time, i.duration_minutes,
                       ST_Y(i.display_point) lat, ST_X(i.display_point) lon, up.kind AS up_kind
                FROM app.itinerary_item i
                JOIN app.itinerary_day d ON d.id = i.day_id
                LEFT JOIN app.user_place up ON up.id = i.user_place_id
                WHERE d.itinerary_id = :it AND i.type IN ('visit', 'meal')
                  AND i.display_point IS NOT NULL
                ORDER BY d.day_index, i.position
                """
            ),
            {"it": trip.selected_itinerary_id},
        ).all()
        # A town the user added by hand may be a base city already listed (or added twice).
        listed_cities = {v["name"].casefold() for v in visits}
        for it in items:
            is_city = it.type == "visit" and it.up_kind == "city"
            if is_city:
                if it.display_name.casefold() in listed_cities:
                    continue
                listed_cities.add(it.display_name.casefold())
            visits.append(
                {
                    "kind": (
                        "city"
                        if is_city
                        else it.up_kind
                        if it.type == "meal" and it.up_kind in ("restaurant", "cafe")
                        else "restaurant"
                        if it.type == "meal"
                        else "attraction"
                    ),
                    "name": it.display_name,
                    "lat": it.lat,
                    "lon": it.lon,
                    "ref": None if it.place_id is None else str(it.place_id),
                    "day": it.day_index,
                    "position": it.position,
                    "start": it.start_time,
                    "minutes": it.duration_minutes,
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
                "position": None,
                "start": None,
                "minutes": None,
            },
        )
    return visits


def _archive(conn: Connection, trip: Trip, reason: str) -> bool:
    """Writes the archive and deletes the plans. False if the trip was already past (a concurrent
    request got there first)."""
    status = conn.execute(
        text("SELECT status FROM app.trip WHERE id = :t FOR UPDATE"), {"t": trip.id}
    ).scalar_one()
    if status == "past":
        return False
    visits = _collect_visits(conn, trip)
    for v in visits:
        conn.execute(
            text(
                "INSERT INTO app.trip_visit (id, trip_id, kind, name, point, geo_place_ref,"
                " day_number, position, start_time, duration_minutes) VALUES (:id, :t, :k, :n,"
                " ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), :ref, :d, :pos, :st, :min)"
            ),
            {
                "id": uuid.uuid4(),
                "t": trip.id,
                "k": v["kind"],
                "n": v["name"],
                "lon": v["lon"],
                "lat": v["lat"],
                "ref": v["ref"],
                "d": v["day"],
                "pos": v["position"],
                "st": v["start"],
                "min": v["minutes"],
            },
        )
    conn.execute(
        text("UPDATE app.trip SET selected_itinerary_id = NULL WHERE id = :t"), {"t": trip.id}
    )
    # Days, items, transfers (with their route geometry), itinerary versions and change sets go
    # with their itinerary (ON DELETE CASCADE).
    deleted = conn.execute(text("DELETE FROM app.itinerary WHERE trip_id = :t"), {"t": trip.id})
    conn.execute(
        text(
            "UPDATE app.trip SET status = 'past', archived_at = now(), updated_at = now() WHERE id = :t"
        ),
        {"t": trip.id},
    )
    info = archive_info(conn, trip.id)
    log.info(
        "trip_archived",
        reason=reason,
        itineraries_deleted=deleted.rowcount,
        visits=info.cities + info.attractions,
        size_bytes=info.size_bytes,
    )
    return True


def archive_trip(conn: Connection, installation_id: uuid.UUID, trip_id: uuid.UUID) -> Trip:
    """Turn a trip into a past trip, on the user's request.

    Keeps the title, destination, dates and duration, and one snapshot row per stop of the
    *selected* itinerary (day, order, start and length) and per base city; deletes every
    itinerary (and with them transfers, route geometry, versions and seeds).
    """
    trip = require_trip(conn, installation_id, trip_id)
    if trip.status == "past" or not _archive(conn, trip, "user"):
        raise conflict("already_archived", "the trip is already a past trip")
    return require_trip(conn, installation_id, trip_id)


def archive_due_trips(
    conn: Connection, installation_id: uuid.UUID, today: date | None = None
) -> list[uuid.UUID]:
    """Archives the installation's active trips whose last day ended
    ``AUTO_ARCHIVE_GRACE_DAYS`` ago. Trips without a start date never become past by themselves
    (there is no last day), and neither does the seed trip, which is illustrative. A trip created
    after its last day (a journey already taken, ADR 026) is not archived by itself either.

    Called when the trips are read, so no scheduled job is needed."""
    due = conn.execute(
        text(
            "SELECT id FROM app.trip WHERE installation_id = :i AND status = 'active' AND NOT is_seed"
            " AND start_date IS NOT NULL"
            " AND start_date + (duration_days - 1 + :g) <= CAST(:today AS date)"
            # A trip made after its last day was entered as a journey already taken: the user
            # fills it and marks it past (ADR 026 decision 23).
            " AND CAST(created_at AS date) <= start_date + (duration_days - 1 + :g) ORDER BY id"
        ),
        {"i": installation_id, "g": AUTO_ARCHIVE_GRACE_DAYS, "today": today or today_utc()},
    ).all()
    archived: list[uuid.UUID] = []
    for row in due:
        trip = get_trip(conn, installation_id, row.id)
        if trip is not None and _archive(conn, trip, "after_last_day"):
            archived.append(row.id)
    return archived


def archive_info(conn: Connection, trip_id: uuid.UUID) -> ArchiveInfo:
    row = conn.execute(
        text(
            """
            SELECT
              count(*) FILTER (WHERE v.kind = 'city') AS cities,
              count(*) FILTER (WHERE v.kind = 'attraction') AS attractions,
              count(*) FILTER (WHERE v.kind IN ('restaurant', 'cafe')) AS eateries,
              count(*) FILTER (WHERE NOT v.confirmed) AS skipped,
              coalesce(sum(pg_column_size(v.*)), 0)
                + (SELECT pg_column_size(t.*) FROM app.trip t WHERE t.id = :t) AS size_bytes
            FROM app.trip_visit v WHERE v.trip_id = :t
            """
        ),
        {"t": trip_id},
    ).one()
    return ArchiveInfo(
        trip_id=trip_id,
        cities=row.cities,
        attractions=row.attractions,
        places_to_eat=row.eateries,
        skipped=row.skipped,
        size_bytes=int(row.size_bytes),
    )


def get_archive_info(
    conn: Connection, installation_id: uuid.UUID, trip_id: uuid.UUID
) -> ArchiveInfo:
    trip = require_trip(conn, installation_id, trip_id)
    if trip.status != "past":
        raise conflict("not_archived", "only a past trip has an archive")
    return archive_info(conn, trip_id)


def list_visits(
    conn: Connection, installation_id: uuid.UUID, trip_id: uuid.UUID
) -> list[TripVisit]:
    require_trip(conn, installation_id, trip_id)
    rows = conn.execute(
        text(
            "SELECT id, kind, name, ST_Y(point) lat, ST_X(point) lon, geo_place_ref, day_number,"
            " position, to_char(start_time, 'HH24:MI') AS start_time, duration_minutes, confirmed"
            " FROM app.trip_visit WHERE trip_id = :t"
            " ORDER BY day_number, (kind = 'city') DESC, position NULLS FIRST, name, id"
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
            position=r.position,
            start_time=r.start_time,
            duration_minutes=r.duration_minutes,
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


def cover_destinations(conn: Connection, trip_id: uuid.UUID) -> list[tuple[str, str]]:
    """The destinations whose photos a trip's cover may be chosen from: its city or area, or each
    stop's city for a multi-city trip (ADR 024)."""
    row = conn.execute(
        text("SELECT destination_kind, destination_ref FROM app.trip WHERE id = :id"),
        {"id": trip_id},
    ).one()
    if row[0] in ("city", "area"):
        return [(row[0], row[1])]
    stops = conn.execute(
        text("SELECT city_id::text FROM app.trip_stop WHERE trip_id = :id ORDER BY position"),
        {"id": trip_id},
    ).all()
    return [("city", r[0]) for r in stops]
