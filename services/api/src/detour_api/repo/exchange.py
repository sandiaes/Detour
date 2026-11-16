"""Trip export and import (ADR 028).

Export reads one installation's trips into the file shape. Import writes every trip of a file as
a *new* trip with new identifiers (never a merge), as a snapshot place trip (ADR 027) whose plan is
a manual itinerary of the user's own places. Nothing in the file is looked up in the imported data.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Connection, text

from detour_api.errors import ApiError, invalid
from detour_api.models.exchange import (
    FORMAT_VERSION,
    FileDay,
    FileDestination,
    FileItem,
    FileStay,
    FileStop,
    FileTrip,
    FileVisit,
    ImportedTrip,
    ImportResult,
    TripFile,
)
from detour_api.models.trips import (
    PLACE_REF,
    ItemCreate,
    StayCreate,
    TransportInfo,
    Trip,
    TripCreate,
    UserPlaceCreate,
)
from detour_api.repo import itineraries, stays, trips, user_places

# -- export ------------------------------------------------------------------------------------


def _reference(conn: Connection, trip: Trip) -> str | None:
    """The provider reference of the destination, when one is known."""
    kind, ref = trip.destination.kind, trip.destination.ref
    if kind == "place":
        return ref if PLACE_REF.fullmatch(ref) else None
    if kind == "city" or kind == "route":
        return f"geonames:{ref}" if ref.isdigit() else None  # geo.city.id is the GeoNames id
    if kind == "area":
        return f"area:{ref}" if PLACE_REF.fullmatch(f"area:{ref}") else None
    return None


def _item_kind(type_: str, up_kind: str | None, place_id: Any, venue: str | None) -> str:
    if type_ == "transport":
        return "transport"
    if type_ == "meal":
        return up_kind if up_kind in ("restaurant", "cafe") else "restaurant"
    if up_kind == "city":
        return "city"
    return "sight" if place_id is not None else "place"


def _days(conn: Connection, itinerary_id: uuid.UUID) -> list[FileDay]:
    rows = conn.execute(
        text(
            """
            SELECT d.day_index, d.base_city_name, i.position, i.type, i.display_name,
                   ST_Y(i.display_point) AS lat, ST_X(i.display_point) AS lon, i.start_time,
                   i.duration_minutes, i.duration_source, i.locked, i.place_id, i.transport,
                   up.kind AS up_kind
            FROM app.itinerary_day d
            LEFT JOIN app.itinerary_item i ON i.day_id = d.id
                AND ((i.type IN ('visit', 'meal') AND i.display_point IS NOT NULL)
                     OR i.type = 'transport')
            LEFT JOIN app.user_place up ON up.id = i.user_place_id
            WHERE d.itinerary_id = :it ORDER BY d.day_index, i.position
            """
        ),
        {"it": itinerary_id},
    ).all()
    days: dict[int, FileDay] = {}
    for r in rows:
        day = days.setdefault(
            r.day_index, FileDay(day_index=r.day_index, base_city_name=r.base_city_name)
        )
        if r.position is None:
            continue
        day.items.append(
            FileItem(
                position=len(day.items) + 1,
                kind=_item_kind(r.type, r.up_kind, r.place_id, None),
                name=r.display_name,
                lat=r.lat,
                lon=r.lon,
                start_time=r.start_time,
                duration_minutes=r.duration_minutes,
                duration_is_user=r.duration_source == "user",
                locked=r.locked,
                transport=None if r.transport is None else TransportInfo(**r.transport),
            )
        )
    return [days[k] for k in sorted(days)]


def _visits(conn: Connection, trip_id: uuid.UUID) -> list[FileVisit]:
    return [
        FileVisit(
            kind=v.kind,
            name=v.name,
            lat=v.lat,
            lon=v.lon,
            day_number=v.day_number,
            position=v.position,
            start_time=None
            if v.start_time is None
            else datetime.strptime(v.start_time, "%H:%M").time(),
            duration_minutes=v.duration_minutes,
            confirmed=v.confirmed,
        )
        for v in trips.list_visits_of(conn, trip_id)
    ]


def export_trip(conn: Connection, trip: Trip) -> FileTrip:
    """One trip in the file shape: the chosen plan only, or the archive of a past trip."""
    days = [] if trip.selected_itinerary_id is None else _days(conn, trip.selected_itinerary_id)
    d = trip.destination
    return FileTrip(
        title=trip.title,
        destination=FileDestination(
            kind=d.kind,
            ref=_reference(conn, trip),
            name=d.name,
            lat=d.lat,
            lon=d.lon,
            country_iso2=d.country_iso2,
        ),
        duration_days=trip.duration_days,
        start_date=trip.start_date,
        status=trip.status,
        archived_at=trip.archived_at,
        stops=[
            FileStop(name=s.name, lat=s.lat, lon=s.lon, days=s.days, country_iso2=s.country_iso2)
            for s in trip.stops
        ],
        days=days,
        visits=_visits(conn, trip.id) if trip.status == "past" and not days else [],
        stays=[
            FileStay(name=s.name, lat=s.lat, lon=s.lon, first_day=s.first_day, last_day=s.last_day)
            for s in stays.list_for_trip(conn, trip.id)
        ],
        uses_car=trip.uses_car,
    )


def export_file(trip_list: list[FileTrip]) -> TripFile:
    return TripFile(format_version=FORMAT_VERSION, exported_at=datetime.now(UTC), trips=trip_list)


# -- import ------------------------------------------------------------------------------------

_PLACE_KIND = {"sight": "location", "place": "location", "city": "city"}


def _check_file(file: TripFile) -> None:
    if file.format_version > FORMAT_VERSION:
        raise ApiError(
            422,
            "format_too_new",
            "this file was made by a newer version of Detour: update the app to open it",
        )
    for n, t in enumerate(file.trips):
        seen: set[int] = set()
        for day in t.days:
            if day.day_index > t.duration_days:
                raise invalid("bad_file", f"trip {n + 1}: a day is beyond the trip's length")
            if day.day_index in seen:
                raise invalid("bad_file", f"trip {n + 1}: day {day.day_index} appears twice")
            seen.add(day.day_index)
        if t.days and t.visits:
            raise invalid("bad_file", f"trip {n + 1}: a trip has a plan or visits, not both")
        if t.status == "active" and t.visits:
            raise invalid("bad_file", f"trip {n + 1}: only a past trip has visits")
        for stay in t.stays:
            if stay.last_day < stay.first_day or stay.last_day > t.duration_days:
                raise invalid("bad_file", f"trip {n + 1}: a stay is outside the trip's days")


def _destination_ref(d: FileDestination) -> str:
    return d.ref if d.ref is not None and PLACE_REF.fullmatch(d.ref) else "manual"


def _import_trip(conn: Connection, installation_id: uuid.UUID, t: FileTrip) -> ImportedTrip:
    d = t.destination
    body = TripCreate(
        title=t.title,
        destination_kind="place",
        destination_ref=_destination_ref(d),
        destination_name=d.name,
        destination_lat=d.lat,
        destination_lon=d.lon,
        destination_country=d.country_iso2,
        duration_days=t.duration_days,
        start_date=t.start_date,
        # A version 1 file has no Car choice: the trip keeps a car, as it did before (ADR 032).
        uses_car=True if t.uses_car is None else t.uses_car,
    )
    trip = trips.create_trip(
        conn, installation_id, body, destination_name=d.name, lat=d.lat, lon=d.lon
    )
    stops = 0
    if t.days:
        stops = _write_plan(conn, installation_id, trip, t.days)
    for stay in t.stays:
        stays.create(
            conn,
            installation_id,
            trip.id,
            StayCreate(
                name=stay.name,
                lat=stay.lat,
                lon=stay.lon,
                first_day=stay.first_day,
                last_day=stay.last_day,
            ),
        )
    if t.status == "past":
        _write_visits(conn, trip.id, t.visits)
        conn.execute(
            text(
                "UPDATE app.trip SET status = 'past', archived_at = COALESCE(:at, now()),"
                " updated_at = now() WHERE id = :t"
            ),
            {"at": t.archived_at, "t": trip.id},
        )
    return ImportedTrip(
        index=0,
        trip_id=str(trip.id),
        title=trip.title,
        days=sum(1 for day in t.days if day.items),
        stops=stops,
    )


def _write_visits(conn: Connection, trip_id: uuid.UUID, visits: list[FileVisit]) -> None:
    for v in visits:
        conn.execute(
            text(
                "INSERT INTO app.trip_visit (id, trip_id, kind, name, point, geo_place_ref,"
                " day_number, position, start_time, duration_minutes, confirmed) VALUES (:id, :t,"
                " :k, :n, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), NULL, :d, :pos, :st, :min,"
                " :c)"
            ),
            {
                "id": uuid.uuid4(),
                "t": trip_id,
                "k": v.kind,
                "n": v.name,
                "lon": v.lon,
                "lat": v.lat,
                "d": v.day_number,
                "pos": v.position,
                "st": v.start_time,
                "min": v.duration_minutes,
                "c": v.confirmed,
            },
        )


def _write_plan(
    conn: Connection, installation_id: uuid.UUID, trip: Trip, days: list[FileDay]
) -> int:
    """A manual itinerary of the trip, chosen, with every stop as the user's own place."""
    plan = itineraries.create_manual(conn, installation_id, trip.id)
    conn.execute(
        text("UPDATE app.trip SET selected_itinerary_id = :i WHERE id = :t"),
        {"i": plan.id, "t": trip.id},
    )
    conn.execute(text("UPDATE app.itinerary SET status = 'selected' WHERE id = :i"), {"i": plan.id})
    made: dict[tuple[str, str, float, float], uuid.UUID] = {}
    count = 0
    for day in days:
        if day.base_city_name:
            conn.execute(
                text(
                    "UPDATE app.itinerary_day SET base_city_name = :n"
                    " WHERE itinerary_id = :i AND day_index = :d"
                ),
                {"n": day.base_city_name, "i": plan.id, "d": day.day_index},
            )
        placed = 0
        for it in sorted(day.items, key=lambda x: x.position):
            if it.transport is not None:
                # A leg comes back as a leg of the manual plan, as entered (ADR 032).
                itineraries.create_item(
                    conn,
                    installation_id,
                    plan.id,
                    day.day_index,
                    ItemCreate(
                        type="transport",
                        transport=it.transport,
                        start_time=it.start_time,
                        duration_minutes=it.duration_minutes,
                        # In the file's order: a journey leg would otherwise go first.
                        position=placed + 1,
                    ),
                )
                count += 1
                placed += 1
                continue
            assert it.lat is not None and it.lon is not None  # noqa: S101 - FileItem checks
            kind = it.kind if it.kind in ("restaurant", "cafe") else _PLACE_KIND[it.kind]
            key = (kind, it.name.casefold(), round(it.lat, 6), round(it.lon, 6))
            if key not in made:
                place = user_places.create(
                    conn,
                    installation_id,
                    UserPlaceCreate(
                        kind=kind,
                        name=it.name,
                        lat=it.lat,
                        lon=it.lon,
                        source="manual_pin",
                    ),
                )
                made[key] = place.id
            item = itineraries.create_item(
                conn,
                installation_id,
                plan.id,
                day.day_index,
                ItemCreate(
                    type="meal" if kind in ("restaurant", "cafe") else "visit",
                    user_place_id=made[key],
                    start_time=it.start_time,
                    duration_minutes=it.duration_minutes,
                    locked=it.locked,
                ),
            )
            if not it.duration_is_user:
                conn.execute(
                    text(
                        "UPDATE app.itinerary_item SET duration_source = 'category_default'"
                        " WHERE id = :i"
                    ),
                    {"i": item.id},
                )
            count += 1
            placed += 1
    return count


def import_file(conn: Connection, installation_id: uuid.UUID, file: TripFile) -> ImportResult:
    """Write every trip of the file as a new trip, all or nothing (the caller's transaction)."""
    _check_file(file)
    trips.ensure_installation(conn, installation_id)
    done: list[ImportedTrip] = []
    for index, t in enumerate(file.trips):
        result = _import_trip(conn, installation_id, t)
        result.index = index
        done.append(result)
    return ImportResult(trips=done)
