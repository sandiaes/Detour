"""Trips, the past-trip archive (ADR 006) and installations."""

import uuid
from datetime import UTC, date, datetime
from typing import Any

import structlog
from sqlalchemy import Connection, Engine, text

from detour_api.errors import ApiError, conflict, invalid, not_found
from detour_api.models.images import Photo
from detour_api.models.trips import (
    ArchiveInfo,
    Destination,
    Trip,
    TripCreate,
    TripMember,
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
    t.stops_version, t.destination_country, t.uses_car
"""


def ensure_installation(conn: Connection, installation_id: uuid.UUID) -> None:
    """Create the installation row on first use.

    DO NOTHING, never DO UPDATE: an upsert that updates, even one whose WHERE is false, locks the
    existing row until the transaction ends, so every request of one phone waited for the one before
    it, and with a small connection pool that stalled for the pool timeout (2026-11-15).
    """
    conn.execute(
        text("INSERT INTO app.installation (id) VALUES (:i) ON CONFLICT (id) DO NOTHING"),
        {"i": installation_id},
    )


def touch_installation(engine: Engine, installation_id: uuid.UUID) -> None:
    """Note that the installation was seen (at most hourly), in a transaction of its own that ends
    at once, so the row is never locked while a request does its work."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE app.installation SET last_seen_at = now()"
                " WHERE id = :i AND last_seen_at < now() - interval '1 hour'"
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
            country_iso2=row.destination_country,
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
        uses_car=row.uses_car,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def get_trip(conn: Connection, person_id: uuid.UUID, trip_id: uuid.UUID) -> Trip | None:
    row = conn.execute(
        text(
            f"SELECT {_TRIP_COLUMNS} FROM app.trip t WHERE t.id = :t"
            f" AND EXISTS (SELECT 1 FROM app.trip_member tm WHERE tm.trip_id = t.id AND tm.person_id = :i)"
        ),
        {"t": trip_id, "i": person_id},
    ).first()
    if row is None:
        return None
    stops = trip_stops(conn, [row.id]) if row.destination_kind == "route" else {}
    trip = _trip(row, images.trip_covers(conn, [row.id]).get(row.id), stops.get(row.id))
    return _with_members(conn, person_id, [trip])[0]


def check_updated_at(
    conn: Connection, person_id: uuid.UUID, trip_id: uuid.UUID, if_match: str | None
) -> None:
    """Refuse a change to a trip someone else changed after the caller read it (ADR 034, step
    4): ``If-Match`` carries the trip's ``updated_at`` as the API sent it. The row is locked."""
    if if_match is None:
        return
    try:
        expected = datetime.fromisoformat(if_match.strip().strip('"').replace("Z", "+00:00"))
    except ValueError:
        raise invalid("bad_if_match", "If-Match must be the trip's updated_at") from None
    current = conn.execute(
        text(
            "SELECT t.updated_at FROM app.trip t WHERE t.id = :t AND EXISTS (SELECT 1 FROM"
            " app.trip_member tm WHERE tm.trip_id = t.id AND tm.person_id = :p) FOR UPDATE"
        ),
        {"t": trip_id, "p": person_id},
    ).scalar_one_or_none()
    if current is not None and current != expected:
        raise ApiError(
            409,
            "trip_changed",
            "the trip was changed by someone else after you opened it; it was not saved",
        )


def require_trip(conn: Connection, person_id: uuid.UUID, trip_id: uuid.UUID) -> Trip:
    trip = get_trip(conn, person_id, trip_id)
    if trip is None:
        raise not_found("trip")
    return trip


def past_refusal() -> ApiError:
    """A past trip is read-only (ADR 006, amendment of 2026-11-17): its plan, stays, cities, dates
    and name are not changed until the user reopens it. Documents and photo links live on the
    phone and are not affected."""
    return conflict("trip_past", "a past trip cannot be changed: reopen it first")


def refuse_if_past(status: str) -> None:
    if status == "past":
        raise past_refusal()


def require_open_trip(conn: Connection, person_id: uuid.UUID, trip_id: uuid.UUID) -> Trip:
    """The caller's trip, refused with 409 ``trip_past`` when it is a past trip."""
    trip = require_trip(conn, person_id, trip_id)
    refuse_if_past(trip.status)
    return trip


def list_trips(conn: Connection, person_id: uuid.UUID, status: str | None = None) -> list[Trip]:
    rows = conn.execute(
        text(
            f"SELECT {_TRIP_COLUMNS} FROM app.trip t WHERE EXISTS (SELECT 1 FROM app.trip_member tm WHERE tm.trip_id = t.id AND tm.person_id = :i)"
            " AND (CAST(:s AS text) IS NULL OR t.status = :s)"
            " ORDER BY t.created_at DESC, t.id"
        ),
        {"i": person_id, "s": status},
    ).all()
    covers = images.trip_covers(conn, [r.id for r in rows])
    stops = trip_stops(conn, [r.id for r in rows if r.destination_kind == "route"])
    return _with_members(
        conn, person_id, [_trip(r, covers.get(r.id), stops.get(r.id)) for r in rows]
    )


# -- members (ADR 034) ---------------------------------------------------------------------------


def _with_members(conn: Connection, person_id: uuid.UUID, found: list[Trip]) -> list[Trip]:
    """Each trip with its members (the owner first, then by when they were added) and the
    caller's role."""
    if not found:
        return found
    rows = conn.execute(
        text(
            """
            SELECT m.trip_id, m.person_id, m.role, p.display_name FROM app.trip_member m
            JOIN app.person p ON p.id = m.person_id
            WHERE m.trip_id = ANY(CAST(:ids AS uuid[]))
            ORDER BY m.trip_id, m.role = 'owner' DESC, m.added_at, m.person_id
            """
        ),
        {"ids": [str(t.id) for t in found]},
    ).all()
    members: dict[uuid.UUID, list[TripMember]] = {}
    for r in rows:
        members.setdefault(r.trip_id, []).append(
            TripMember(
                person_id=r.person_id,
                name=r.display_name,
                role=r.role,
                you=r.person_id == person_id,
            )
        )
    for trip in found:
        trip.members = members.get(trip.id, [])
        trip.role = next((m.role for m in trip.members if m.you), "owner")
    return found


def _linked(conn: Connection, a: uuid.UUID, b: uuid.UUID) -> bool:
    return (
        conn.execute(
            text("SELECT 1 FROM app.person_link WHERE person_a = :a AND person_b = :b"),
            {"a": min(a, b), "b": max(a, b)},
        ).first()
        is not None
    )


def _require_owner(trip: Trip) -> None:
    if trip.role != "owner":
        raise ApiError(
            403, "not_trip_owner", "only the person who created this trip can change who is on it"
        )


def add_member(
    conn: Connection, person_id: uuid.UUID, trip_id: uuid.UUID, other: uuid.UUID
) -> Trip:
    """Share the trip with a linked person, who can then read and change it (role editor)."""
    trip = require_trip(conn, person_id, trip_id)
    _require_owner(trip)
    if other == person_id or not _linked(conn, person_id, other):
        raise conflict("not_linked", "you can share a trip only with someone linked under People")
    added = conn.execute(
        text(
            """
            INSERT INTO app.trip_member (trip_id, person_id, role, added_by)
            VALUES (:t, :o, 'editor', :p) ON CONFLICT (trip_id, person_id) DO NOTHING RETURNING 1
            """
        ),
        {"t": trip_id, "o": other, "p": person_id},
    ).first()
    if added is None:
        raise conflict("already_member", "this person is already on the trip")
    return require_trip(conn, person_id, trip_id)


def remove_member(
    conn: Connection, person_id: uuid.UUID, trip_id: uuid.UUID, other: uuid.UUID
) -> None:
    """Leave a trip (a member removes themself), or stop sharing it with someone (the owner).
    The owner cannot leave: they delete the trip instead."""
    trip = require_trip(conn, person_id, trip_id)
    if other == person_id:
        if trip.role == "owner":
            raise conflict(
                "owner_cannot_leave", "you created this trip; delete it or stop sharing it instead"
            )
    else:
        _require_owner(trip)
    removed = conn.execute(
        text(
            "DELETE FROM app.trip_member WHERE trip_id = :t AND person_id = :o AND role = 'editor'"
            " RETURNING 1"
        ),
        {"t": trip_id, "o": other},
    ).first()
    if removed is None:
        raise not_found("trip member")


def create_trip(
    conn: Connection,
    person_id: uuid.UUID,
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
        text("SELECT count(*) FROM app.trip WHERE owner_person_id = :i"), {"i": person_id}
    ).scalar_one()
    if count >= MAX_TRIPS_PER_INSTALLATION:
        raise conflict(
            "limit_reached", f"at most {MAX_TRIPS_PER_INSTALLATION} trips per installation"
        )
    trip_id = uuid.uuid4()
    conn.execute(
        text(
            """
            INSERT INTO app.trip (id, owner_person_id, title, destination_kind, destination_ref,
                destination_name, destination_point, duration_days, start_date, is_seed,
                destination_country, uses_car)
            VALUES (:id, :inst, :title, :kind, :ref, :dname,
                ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), :days, :start, :seed, :country,
                :car)
            """
        ),
        {
            "id": trip_id,
            "inst": person_id,
            "title": title or body.title,
            "kind": body.destination_kind,
            "ref": body.destination_ref,
            "dname": destination_name,
            "lat": lat,
            "lon": lon,
            "days": body.duration_days,
            "start": body.start_date,
            "seed": is_seed,
            "country": (body.destination_country or "").upper() or None,
            "car": body.uses_car,
        },
    )
    if stops:
        write_stops(conn, trip_id, stops)
    for other in dict.fromkeys(body.share_with):  # "Who's going" (ADR 034)
        if other == person_id or not _linked(conn, person_id, other):
            raise conflict(
                "not_linked", "you can share a trip only with someone linked under People"
            )
        conn.execute(
            text(
                "INSERT INTO app.trip_member (trip_id, person_id, role, added_by)"
                " VALUES (:t, :o, 'editor', :p)"
            ),
            {"t": trip_id, "o": other, "p": person_id},
        )
    return require_trip(conn, person_id, trip_id)


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
    conn: Connection, person_id: uuid.UUID, trip_id: uuid.UUID, body: TripUpdate
) -> Trip:
    trip = require_open_trip(conn, person_id, trip_id)
    changed = body.model_fields_set
    sets: list[str] = []
    params: dict[str, Any] = {"t": trip_id, "i": person_id}

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
    if "uses_car" in changed:
        if body.uses_car is None:
            raise invalid("uses_car_required", "uses_car cannot be cleared")
        sets.append("uses_car = :car")
        params["car"] = body.uses_car
    if "selected_itinerary_id" in changed:
        _select_itinerary(conn, trip_id, body.selected_itinerary_id)
        sets.append("selected_itinerary_id = :sel")
        params["sel"] = body.selected_itinerary_id
    if sets:
        conn.execute(
            text(f"UPDATE app.trip SET {', '.join(sets)}, updated_at = now() WHERE id = :t"),
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
    return require_trip(conn, person_id, trip_id)


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


def delete_trip(conn: Connection, person_id: uuid.UUID, trip_id: uuid.UUID) -> None:
    """Deletes the trip with its itineraries, days, items, transfers and archive rows, for every
    member. Only its owner may (ADR 034: both edit, the creator deletes); a member is refused with
    403 ``not_trip_owner``. Places stay (they belong to the person who added them)."""
    require_trip(conn, person_id, trip_id)
    result = conn.execute(
        text("DELETE FROM app.trip WHERE id = :t AND owner_person_id = :i"),
        {"t": trip_id, "i": person_id},
    )
    if result.rowcount == 0:
        raise ApiError(403, "not_trip_owner", "only the person who created this trip can delete it")


# -- archive (ADR 006) -------------------------------------------------------------------------

# A trip becomes past by itself this many days after its last day. The last day is a calendar date
# without a time zone and trips are anywhere on Earth, so two days make sure that day is over
# everywhere (UTC-12 to UTC+14) before anything is deleted.
AUTO_ARCHIVE_GRACE_DAYS = 2

log = structlog.get_logger("detour.archive")


def today_utc() -> date:
    return datetime.now(UTC).date()


def _archive(conn: Connection, trip: Trip, reason: str) -> bool:
    """Makes the trip a past trip. Since the amendment of 2026-11-16 nothing is deleted except the
    undo history beyond the newest five versions of each plan: a past trip keeps its plan, routes,
    stays and documents and works like any other trip. False if the trip was already past (a
    concurrent request got there first)."""
    from detour_api.repo import plan_state

    status = conn.execute(
        text("SELECT status FROM app.trip WHERE id = :t FOR UPDATE"), {"t": trip.id}
    ).scalar_one()
    if status == "past":
        return False
    pruned = plan_state.prune_versions(conn, trip.id)
    conn.execute(
        text(
            "UPDATE app.trip SET status = 'past', archived_at = now(), updated_at = now() WHERE id = :t"
        ),
        {"t": trip.id},
    )
    log.info("trip_archived", reason=reason, versions_pruned=pruned)
    return True


def archive_trip(conn: Connection, person_id: uuid.UUID, trip_id: uuid.UUID) -> Trip:
    """Turn a trip into a past trip, on the user's request. The plan is kept; only the undo
    history is cut to five versions."""
    trip = require_trip(conn, person_id, trip_id)
    if trip.status == "past" or not _archive(conn, trip, "user"):
        raise conflict("already_archived", "the trip is already a past trip")
    return require_trip(conn, person_id, trip_id)


def reopen_trip(conn: Connection, person_id: uuid.UUID, trip_id: uuid.UUID) -> Trip:
    """Take a past trip out of the past: it is an ordinary trip again and the two-day rule leaves
    it alone (``reopened_at``), so it does not become past again by itself."""
    trip = require_trip(conn, person_id, trip_id)
    if trip.status != "past":
        raise conflict("not_archived", "only a past trip can be reopened")
    conn.execute(
        text(
            "UPDATE app.trip SET status = 'active', archived_at = NULL, reopened_at = now(),"
            " updated_at = now() WHERE id = :t"
        ),
        {"t": trip_id},
    )
    return require_trip(conn, person_id, trip_id)


def archive_due_trips(
    conn: Connection, person_id: uuid.UUID, today: date | None = None
) -> list[uuid.UUID]:
    """Archives the installation's active trips whose last day ended
    ``AUTO_ARCHIVE_GRACE_DAYS`` ago. Trips without a start date never become past by themselves
    (there is no last day), and neither does the seed trip, which is illustrative. A trip created
    after its last day (a journey already taken, ADR 026) is not archived by itself either.

    Called when the trips are read, so no scheduled job is needed."""
    due = conn.execute(
        text(
            "SELECT id FROM app.trip WHERE id IN (SELECT tm.trip_id FROM app.trip_member tm WHERE tm.person_id = :i)"
            " AND status = 'active' AND NOT is_seed"
            " AND start_date IS NOT NULL AND reopened_at IS NULL"
            " AND start_date + (duration_days - 1 + :g) <= CAST(:today AS date)"
            # A trip made after its last day was entered as a journey already taken: the user
            # fills it and marks it past (ADR 026 decision 23).
            " AND CAST(created_at AS date) <= start_date + (duration_days - 1 + :g) ORDER BY id"
        ),
        {"i": person_id, "g": AUTO_ARCHIVE_GRACE_DAYS, "today": today or today_utc()},
    ).all()
    archived: list[uuid.UUID] = []
    for row in due:
        trip = get_trip(conn, person_id, row.id)
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


def get_archive_info(conn: Connection, person_id: uuid.UUID, trip_id: uuid.UUID) -> ArchiveInfo:
    trip = require_trip(conn, person_id, trip_id)
    if trip.status != "past":
        raise conflict("not_archived", "only a past trip has an archive")
    return archive_info(conn, trip_id)


def list_visits(conn: Connection, person_id: uuid.UUID, trip_id: uuid.UUID) -> list[TripVisit]:
    require_trip(conn, person_id, trip_id)
    return list_visits_of(conn, trip_id)


def list_visits_of(conn: Connection, trip_id: uuid.UUID) -> list[TripVisit]:
    """The archived visits of a trip the caller already owns."""
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
    person_id: uuid.UUID,
    trip_id: uuid.UUID,
    visit_id: uuid.UUID,
    confirmed: bool,
) -> TripVisit:
    require_trip(conn, person_id, trip_id)
    result = conn.execute(
        text("UPDATE app.trip_visit SET confirmed = :c WHERE id = :v AND trip_id = :t"),
        {"c": confirmed, "v": visit_id, "t": trip_id},
    )
    if result.rowcount == 0:
        raise not_found("visit")
    return next(v for v in list_visits(conn, person_id, trip_id) if v.id == visit_id)


def cover_destinations(conn: Connection, trip_id: uuid.UUID) -> list[tuple[str, str]]:
    """The destinations whose photos a trip's cover may be chosen from: its city or area, or each
    stop's city for a multi-city trip (ADR 024)."""
    row = conn.execute(
        text("SELECT destination_kind, destination_ref FROM app.trip WHERE id = :id"),
        {"id": trip_id},
    ).one()
    if row[0] in ("city", "area"):
        return [(row[0], row[1])]
    if row[0] == "place":
        # Only a gazetteer place has photo candidates; Photon and manual ones have none (ADR 027).
        ref = str(row[1])
        if ref.startswith("geonames:"):
            return [("city", ref.removeprefix("geonames:"))]
        if ref.startswith("area:"):
            return [("area", ref.removeprefix("area:"))]
        return []
    stops = conn.execute(
        text("SELECT city_id::text FROM app.trip_stop WHERE trip_id = :id ORDER BY position"),
        {"id": trip_id},
    ).all()
    return [("city", r[0]) for r in stops]
