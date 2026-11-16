"""Itineraries, days and items.

Manual itineraries are stored and edited by hand (Phase 2); engine itineraries are written by
``repo/planning.py`` (Phase 4) and read here. Every function takes the installation id and returns
nothing about rows that belong to someone else: a foreign or unknown identifier is simply "not
found".

Hand edits do not recompute transfers (recalculation is the change-set flow, ``repo/changes.py``).
A transfer that no longer joins two consecutive items of a day is deleted, so a stale travel time
is never shown. Each hand edit keeps the version it replaces (``app.itinerary_version``).
"""

import uuid
from datetime import UTC, datetime, time, timedelta
from typing import Any

from sqlalchemy import Connection, text

from detour_api.errors import conflict, invalid, not_found
from detour_api.models.common import PlaceName
from detour_api.models.trips import (
    Arrival,
    Day,
    Item,
    ItemCreate,
    ItemUpdate,
    Itinerary,
    ItinerarySummary,
    PlanNote,
    PlanStats,
    RestaurantInfo,
    Transfer,
    TransportInfo,
)
from detour_api.names.api import to_api
from detour_api.names.resolver import ResolvedName
from detour_api.names.store import resolve_places
from detour_api.planner.durations import VENUE_MINUTES, visit_minutes
from detour_api.planner.reasons import ITEM_TEMPLATES, NOTE_TEMPLATES, item_text, note_text
from detour_api.repo import geo, images, plan_state, trips, user_places

MAX_ITINERARIES_PER_TRIP = 5
MAX_ITEMS_PER_DAY = 40
MANUAL_VERSION = "manual"

_ITEM_COLUMNS = """
    i.id, i.day_id, i.position, i.type, i.place_id, i.user_place_id, i.display_name,
    ST_Y(i.display_point) AS lat, ST_X(i.display_point) AS lon, i.start_time, i.end_time,
    i.duration_minutes, i.duration_source, i.origin, i.locked, i.reasons, i.transport,
    up.kind AS r_venue, gp.default_visit_minutes AS g_default, gp.category AS g_category
"""
# The kind of a restaurant or cafe stop is read from the user's place at read time (ADR 026).
_ITEM_JOINS = """
    LEFT JOIN app.user_place up ON i.type = 'meal' AND up.id = i.user_place_id
    LEFT JOIN geo.place gp ON gp.id = i.place_id
"""


_ITINERARY_COLUMNS = """
    it.id, it.trip_id, it.generation_id, it.profile, it.status, it.version, it.engine_version,
    it.config_version, it.import_run_id, it.seed, it.diversity_score, it.summary, it.created_at,
    it.stops_version
"""


def render_reason(code: str) -> str | None:
    """A stored reason code through its fixed template. A code with no template (a meal or
    cuisine reason of a plan made before ADR 026) is not shown: never the raw code."""
    return item_text(code) if code in ITEM_TEMPLATES else None


def render_note(code: str, params: dict[str, Any]) -> PlanNote | None:
    """A stored note through its fixed template, or None for a retired code (ADR 026) or
    parameters that no longer fit the template."""
    if code not in NOTE_TEMPLATES:
        return None
    try:
        return PlanNote(code=code, text=note_text(code, params))
    except (KeyError, IndexError, ValueError):
        return None


def render_notes(notes: list[Any]) -> list[PlanNote]:
    """Stored notes (dicts with ``code`` and ``params``) as shown: retired codes left out."""
    out: list[PlanNote] = []
    for n in notes:
        note = render_note(n["code"], n.get("params", {}))
        if note is not None:
            out.append(note)
    return out


def _summary(row: Any) -> ItinerarySummary:
    summary = row.summary or {}
    stats = summary.get("stats")
    return ItinerarySummary(
        id=row.id,
        trip_id=row.trip_id,
        generation_id=row.generation_id,
        profile=row.profile,
        status=row.status,
        version=row.version,
        engine_version=row.engine_version,
        config_version=row.config_version,
        import_run_id=row.import_run_id,
        seed=row.seed,
        diversity_score=None if row.diversity_score is None else float(row.diversity_score),
        notes=render_notes(summary.get("notes", [])),
        stats=None if stats is None else PlanStats(**stats),
        created_at=row.created_at,
        stops_version=row.stops_version,
    )


def _transfers(conn: Connection, item_ids: list[uuid.UUID]) -> dict[uuid.UUID, Transfer]:
    if not item_ids:
        return {}
    rows = conn.execute(
        text(
            "SELECT from_item_id, to_item_id, mode, seconds, meters, confidence FROM app.transfer"
            " WHERE from_item_id = ANY(:ids)"
        ),
        {"ids": item_ids},
    ).all()
    return {
        r.from_item_id: Transfer(
            to_item_id=r.to_item_id,
            mode=r.mode,
            seconds=r.seconds,
            meters=r.meters,
            confidence=r.confidence,
        )
        for r in rows
    }


def drop_stale_transfers(conn: Connection, day_ids: list[uuid.UUID]) -> None:
    """Delete transfers of these days that no longer join an item to the next one."""
    conn.execute(
        text(
            """
            DELETE FROM app.transfer t USING app.itinerary_item f, app.itinerary_item n
            WHERE t.from_item_id = f.id AND t.to_item_id = n.id AND f.day_id = ANY(:days)
              AND NOT (n.day_id = f.day_id AND n.position = f.position + 1)
            """
        ),
        {"days": day_ids},
    )


def _default_minutes(row: Any) -> int | None:
    """The length "use the default" gives the item: an imported sight's own or its category's,
    a restaurant's or cafe's (ADR 026), and none for anything else (a place the user pinned has
    no known typical length)."""
    if row.type in ("free_time", "transport"):
        return None
    if row.place_id is not None:
        return row.g_default if row.g_default is not None else visit_minutes(row.g_category)
    if row.type == "meal":
        return VENUE_MINUTES.get(row.r_venue)
    return None


def _item(row: Any, transfer: Transfer | None = None) -> Item:
    return Item(
        id=row.id,
        day_id=row.day_id,
        position=row.position,
        type=row.type,
        place_id=row.place_id,
        user_place_id=row.user_place_id,
        display_name=row.display_name,
        lat=row.lat,
        lon=row.lon,
        start_time=row.start_time,
        end_time=row.end_time,
        duration_minutes=row.duration_minutes,
        duration_source=row.duration_source,
        default_duration_minutes=_default_minutes(row),
        origin=row.origin,
        locked=row.locked,
        reasons=list(row.reasons),
        reason_texts=[t for t in (render_reason(c) for c in row.reasons) if t is not None],
        transfer=transfer,
        restaurant=(
            RestaurantInfo(
                venue_type=row.r_venue if row.r_venue in ("restaurant", "cafe") else None
            )
            if row.type == "meal"
            else None
        ),
        transport=None if row.transport is None else TransportInfo(**row.transport),
    )


# -- itineraries -------------------------------------------------------------------------------


def create_manual(conn: Connection, installation_id: uuid.UUID, trip_id: uuid.UUID) -> Itinerary:
    """An empty itinerary with one day per trip day, to be filled by hand."""
    trip = trips.require_trip(conn, installation_id, trip_id)
    count = conn.execute(
        text("SELECT count(*) FROM app.itinerary WHERE trip_id = :t"), {"t": trip_id}
    ).scalar_one()
    if count >= MAX_ITINERARIES_PER_TRIP:
        raise conflict("limit_reached", f"at most {MAX_ITINERARIES_PER_TRIP} itineraries per trip")
    itinerary_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO app.itinerary (id, trip_id, generation_id, profile, engine_version,"
            " config_version, stops_version) VALUES (:i, :t, :g, 'manual', :v, :v, :sv)"
        ),
        {
            "i": itinerary_id,
            "t": trip_id,
            "g": uuid.uuid4(),
            "v": MANUAL_VERSION,
            "sv": trip.stops_version if trip.destination.kind == "route" else None,
        },
    )
    # A multi-city trip's empty days carry their stop's city (ADR 024); there is no travel time.
    bases = [(s.city_id, s.name) for s in trip.stops for _ in range(s.days)]
    for index in range(1, trip.duration_days + 1):
        day_date = None if trip.start_date is None else trip.start_date + timedelta(days=index - 1)
        base = bases[index - 1] if index <= len(bases) else (None, None)
        conn.execute(
            text(
                "INSERT INTO app.itinerary_day (id, itinerary_id, day_index, date, base_city_id,"
                " base_city_name) VALUES (:d, :i, :n, :date, :city, :cname)"
            ),
            {
                "d": uuid.uuid4(),
                "i": itinerary_id,
                "n": index,
                "date": day_date,
                "city": base[0],
                "cname": base[1],
            },
        )
    return require_itinerary(conn, installation_id, itinerary_id)


def list_for_trip(
    conn: Connection, installation_id: uuid.UUID, trip_id: uuid.UUID
) -> list[ItinerarySummary]:
    trips.require_trip(conn, installation_id, trip_id)
    rows = conn.execute(
        text(
            f"SELECT {_ITINERARY_COLUMNS} FROM app.itinerary it WHERE it.trip_id = :t"
            " ORDER BY it.created_at, it.id"
        ),
        {"t": trip_id},
    ).all()
    return [_summary(r) for r in rows]


def get_itinerary(
    conn: Connection, installation_id: uuid.UUID, itinerary_id: uuid.UUID
) -> Itinerary | None:
    row = conn.execute(
        text(
            f"SELECT {_ITINERARY_COLUMNS} FROM app.itinerary it"
            " JOIN app.trip t ON t.id = it.trip_id WHERE it.id = :i AND t.installation_id = :n"
        ),
        {"i": itinerary_id, "n": installation_id},
    ).first()
    if row is None:
        return None
    days = conn.execute(
        text(
            "SELECT d.id, d.day_index, d.date, d.base_city_id, d.base_city_name, d.arrival_mode,"
            " d.arrival_seconds, d.arrival_meters, d.arrival_confidence,"
            # The position is read from the gazetteer by identifier, never copied into app.
            " ST_Y(c.geom) AS base_lat, ST_X(c.geom) AS base_lon"
            " FROM app.itinerary_day d LEFT JOIN geo.city c ON c.id = d.base_city_id"
            " WHERE d.itinerary_id = :i ORDER BY d.day_index"
        ),
        {"i": itinerary_id},
    ).all()
    items = conn.execute(
        text(
            f"SELECT {_ITEM_COLUMNS} FROM app.itinerary_item i {_ITEM_JOINS}"
            " JOIN app.itinerary_day d ON d.id = i.day_id WHERE d.itinerary_id = :i"
            " ORDER BY d.day_index, i.position"
        ),
        {"i": itinerary_id},
    ).all()
    transfers = _transfers(conn, [it.id for it in items])
    place_ids = [it.place_id for it in items if it.place_id is not None]
    photos = images.place_photos(conn, place_ids)
    names = resolve_places(conn, place_ids, installation_id)
    by_day: dict[uuid.UUID, list[Item]] = {}
    for it in items:
        item = _item(it, transfers.get(it.id))
        item.image = photos.get(it.place_id) if it.place_id is not None else None
        item.names = _names(names.get(it.place_id)) if it.place_id is not None else None
        by_day.setdefault(it.day_id, []).append(item)
    summary = _summary(row)
    out: list[Day] = []
    for n, d in enumerate(days):
        arrival = None
        if d.arrival_mode is not None:
            before = days[n - 1] if n > 0 else None
            journey = next(
                (
                    i.id
                    for i in by_day.get(d.id, [])
                    if i.transport is not None and i.transport.is_journey
                ),
                None,
            )
            arrival = Arrival(
                from_base_city_id=None if before is None else before.base_city_id,
                from_base_city_name=None if before is None else before.base_city_name,
                mode=d.arrival_mode,
                seconds=d.arrival_seconds,
                meters=d.arrival_meters,
                confidence=d.arrival_confidence,
                covered_by_item_id=journey,
            )
        out.append(
            Day(
                id=d.id,
                day_index=d.day_index,
                date=d.date,
                base_city_id=d.base_city_id,
                base_city_name=d.base_city_name,
                base_city_lat=d.base_lat,
                base_city_lon=d.base_lon,
                arrival=arrival,
                items=by_day.get(d.id, []),
            )
        )
    return Itinerary(**summary.model_dump(), days=out)


def require_itinerary(
    conn: Connection, installation_id: uuid.UUID, itinerary_id: uuid.UUID
) -> Itinerary:
    result = get_itinerary(conn, installation_id, itinerary_id)
    if result is None:
        raise not_found("itinerary")
    return result


def delete_itinerary(conn: Connection, installation_id: uuid.UUID, itinerary_id: uuid.UUID) -> None:
    itinerary = require_itinerary(conn, installation_id, itinerary_id)
    trips.require_trip(conn, installation_id, itinerary.trip_id)
    conn.execute(text("DELETE FROM app.itinerary WHERE id = :i"), {"i": itinerary_id})


# -- items -------------------------------------------------------------------------------------


def _day_context(
    conn: Connection, installation_id: uuid.UUID, itinerary_id: uuid.UUID, day_index: int
) -> Any:
    """Lock the day row and return it with the trip status; 404 if it is not the caller's."""
    row = conn.execute(
        text(
            "SELECT d.id AS day_id, d.itinerary_id, t.status AS trip_status FROM app.itinerary_day d"
            " JOIN app.itinerary it ON it.id = d.itinerary_id JOIN app.trip t ON t.id = it.trip_id"
            " WHERE d.itinerary_id = :i AND d.day_index = :n AND t.installation_id = :inst"
            " FOR UPDATE OF d"
        ),
        {"i": itinerary_id, "n": day_index, "inst": installation_id},
    ).first()
    if row is None:
        raise not_found("itinerary day")
    return row


def _bump(conn: Connection, itinerary_id: uuid.UUID) -> None:
    conn.execute(
        text("UPDATE app.itinerary SET version = version + 1 WHERE id = :i"), {"i": itinerary_id}
    )


DAY_END_MINUTE = 24 * 60


def _end_time(start: time | None, minutes: int | None, *, transport: bool = False) -> time | None:
    """The end of an item that starts at ``start``. A transport leg (ADR 032) has no stored end
    when its length is unknown, or when it arrives after midnight (a night train)."""
    if start is None or minutes is None:
        return None
    base = datetime.combine(datetime(2000, 1, 1, tzinfo=UTC).date(), start)
    end = base + timedelta(minutes=minutes)
    if end.date() != base.date():
        if transport:
            return None
        raise invalid("crosses_midnight", "an item must end on the same day it starts")
    return end.time()


def _minute(t: time) -> int:
    return t.hour * 60 + t.minute


def busy_span(start: time | None, end: time | None, minutes: int | None) -> tuple[int, int] | None:
    """The minutes of the day an item takes, for the overlap check: start to end; to the end of
    the day for a leg that arrives the next day; a single point for a leg of unknown length."""
    if start is None:
        return None
    s = _minute(start)
    if end is not None:
        return s, _minute(end)
    if minutes is None:
        return s, s
    return s, DAY_END_MINUTE


def _clash(a: tuple[int, int], b: tuple[int, int]) -> bool:
    if a[0] == a[1] and b[0] == b[1]:
        return False  # two legs of unknown length at one minute say nothing about each other
    if a[0] == a[1]:
        return b[0] < a[0] < b[1]
    if b[0] == b[1]:
        return a[0] < b[0] < a[1]
    return a[0] < b[1] and b[0] < a[1]


def _check_overlap(
    conn: Connection,
    day_id: uuid.UUID,
    span: tuple[int, int] | None,
    ignore: uuid.UUID | None,
) -> None:
    if span is None:
        return
    rows = conn.execute(
        text(
            "SELECT start_time, end_time, duration_minutes FROM app.itinerary_item"
            " WHERE day_id = :d AND start_time IS NOT NULL"
            " AND (CAST(:x AS uuid) IS NULL OR id <> :x)"
        ),
        {"d": day_id, "x": ignore},
    ).all()
    for r in rows:
        other = busy_span(r.start_time, r.end_time, r.duration_minutes)
        if other is not None and _clash(span, other):
            raise conflict("overlap", "the item overlaps another timed item of the day")


def _resolve_place(
    conn: Connection, installation_id: uuid.UUID, body: ItemCreate
) -> tuple[str, float | None, float | None, int | None]:
    """(display name, lat, lon, default minutes) of the item's place, validating its kind. An
    imported attraction's default is its category's visit duration (planner/durations.py)."""
    want_restaurant = body.type == "meal"
    eating = ("restaurant", "cafe")
    if body.type == "free_time":
        return "Free time", None, None, None
    if body.type == "transport":
        assert body.transport is not None  # noqa: S101 - guaranteed by ItemCreate
        return body.transport.display_name(), None, None, None
    if body.place_id is not None:
        found = geo.place_exists(conn, body.place_id, installation_id)
        if found is None or not found[4]:
            raise invalid("place_not_found", "place_id is not an active place")
        kind, name, lat, lon, _, default_minutes, category = found
        if want_restaurant or kind in eating:
            raise invalid(
                "wrong_place_kind",
                "a restaurant or cafe is added as your own place; a visit needs an attraction",
            )
        if default_minutes is None and kind == "attraction":
            default_minutes = visit_minutes(category)
        return name, lat, lon, default_minutes
    assert body.user_place_id is not None  # noqa: S101 - guaranteed by ItemCreate
    place = user_places.get(conn, installation_id, body.user_place_id)
    if place is None:
        raise invalid("user_place_not_found", "user_place_id is not one of your places")
    if (place.kind in eating) != want_restaurant:
        raise invalid(
            "wrong_place_kind",
            "a meal needs a restaurant or cafe; a visit needs a place that is not one",
        )
    return place.name, place.lat, place.lon, VENUE_MINUTES.get(place.kind)


def create_item(
    conn: Connection,
    installation_id: uuid.UUID,
    itinerary_id: uuid.UUID,
    day_index: int,
    body: ItemCreate,
) -> Item:
    ctx = _day_context(conn, installation_id, itinerary_id, day_index)
    name, lat, lon, default_minutes = _resolve_place(conn, installation_id, body)
    plan_state.snapshot(conn, itinerary_id)
    leg = body.type == "transport"
    minutes: int | None
    if body.duration_minutes is not None:
        minutes, source = body.duration_minutes, "user"
    elif default_minutes is not None:
        minutes, source = default_minutes, "category_default"
    elif leg:
        minutes, source = None, "user"  # a length the user did not enter is unknown (ADR 032)
    else:
        raise invalid(
            "duration_required",
            "duration_minutes is required: no default duration is known for this place",
        )
    end = _end_time(body.start_time, minutes, transport=leg)
    _check_overlap(conn, ctx.day_id, busy_span(body.start_time, end, minutes), None)

    count = conn.execute(
        text("SELECT count(*) FROM app.itinerary_item WHERE day_id = :d"), {"d": ctx.day_id}
    ).scalar_one()
    if count >= MAX_ITEMS_PER_DAY:
        raise conflict("day_full", f"at most {MAX_ITEMS_PER_DAY} items per day")
    journey = leg and body.transport is not None and body.transport.is_journey
    position = body.position or (1 if journey else count + 1)
    if position > count + 1:
        raise invalid("bad_position", f"position must be between 1 and {count + 1}")
    conn.execute(
        text(
            "UPDATE app.itinerary_item SET position = position + 1 WHERE day_id = :d AND position >= :p"
        ),
        {"d": ctx.day_id, "p": position},
    )
    item_id = uuid.uuid4()
    conn.execute(
        text(
            """
            INSERT INTO app.itinerary_item (id, day_id, position, type, place_id,
                user_place_id, display_name, display_point, start_time, end_time,
                duration_minutes, duration_source, origin, locked, transport)
            VALUES (:id, :d, :pos, :type, :place, :uplace, :name,
                CASE WHEN CAST(:lat AS float8) IS NULL THEN NULL
                     ELSE ST_SetSRID(ST_MakePoint(:lon, :lat), 4326) END,
                :start, :end, :minutes, :source, 'user', :locked, CAST(:transport AS jsonb))
            """
        ),
        {
            "id": item_id,
            "d": ctx.day_id,
            "pos": position,
            "type": body.type,
            "place": body.place_id,
            "uplace": body.user_place_id,
            "name": name,
            "lat": lat,
            "lon": lon,
            "start": body.start_time,
            "end": end,
            "minutes": minutes,
            "source": source,
            # A leg is fixed (ADR 032): Optimize and recalculation never move it.
            "locked": True if leg else body.locked,
            "transport": None if body.transport is None else body.transport.model_dump_json(),
        },
    )
    drop_stale_transfers(conn, [ctx.day_id])
    _bump(conn, itinerary_id)
    return require_item(conn, installation_id, item_id)


def get_item(conn: Connection, installation_id: uuid.UUID, item_id: uuid.UUID) -> Item | None:
    row = conn.execute(
        text(
            f"SELECT {_ITEM_COLUMNS} FROM app.itinerary_item i {_ITEM_JOINS}"
            " JOIN app.itinerary_day d ON d.id = i.day_id JOIN app.itinerary it ON it.id = d.itinerary_id"
            " JOIN app.trip t ON t.id = it.trip_id WHERE i.id = :i AND t.installation_id = :n"
        ),
        {"i": item_id, "n": installation_id},
    ).first()
    if row is None:
        return None
    item = _item(row, _transfers(conn, [row.id]).get(row.id))
    if row.place_id is not None:
        item.image = images.place_photos(conn, [row.place_id]).get(row.place_id)
        item.names = _names(resolve_places(conn, [row.place_id], installation_id).get(row.place_id))
    return item


def _names(resolved: ResolvedName | None) -> PlaceName | None:
    return to_api(resolved) if resolved is not None and resolved.display else None


def require_item(conn: Connection, installation_id: uuid.UUID, item_id: uuid.UUID) -> Item:
    item = get_item(conn, installation_id, item_id)
    if item is None:
        raise not_found("item")
    return item


def update_item(
    conn: Connection, installation_id: uuid.UUID, item_id: uuid.UUID, body: ItemUpdate
) -> Item:
    row = conn.execute(
        text(
            "SELECT i.id, i.day_id, i.position, i.type, i.start_time, i.duration_minutes,"
            " i.duration_source, i.place_id, i.user_place_id, i.transport, d.itinerary_id,"
            " d.day_index,"
            " t.status AS trip_status"
            " FROM app.itinerary_item i JOIN app.itinerary_day d ON d.id = i.day_id"
            " JOIN app.itinerary it ON it.id = d.itinerary_id JOIN app.trip t ON t.id = it.trip_id"
            " WHERE i.id = :i AND t.installation_id = :n FOR UPDATE OF i"
        ),
        {"i": item_id, "n": installation_id},
    ).first()
    if row is None:
        raise not_found("item")
    changed = body.model_fields_set
    leg = row.type == "transport"
    if "transport" in changed and not leg:
        raise invalid("not_transport", "transport is changed only on a transport leg")
    plan_state.snapshot(conn, row.itinerary_id)

    minutes: int | None = row.duration_minutes
    source = row.duration_source
    if body.use_default_duration:
        # "Stick to the default": the length the item would have had when it was added.
        current = require_item(conn, installation_id, item_id)
        if current.default_duration_minutes is None:
            raise invalid("no_default_duration", "this stop has no default duration")
        minutes, source = current.default_duration_minutes, "category_default"
    elif "duration_minutes" in changed:
        if body.duration_minutes is None and not leg:
            raise invalid("duration_required", "duration_minutes cannot be cleared")
        minutes, source = body.duration_minutes, "user"
    start = body.start_time if "start_time" in changed else row.start_time
    end = _end_time(start, minutes, transport=leg)

    target_day_id = row.day_id
    if "day_index" in changed and body.day_index is not None and body.day_index != row.day_index:
        target = conn.execute(
            text(
                "SELECT id FROM app.itinerary_day WHERE itinerary_id = :i AND day_index = :n FOR UPDATE"
            ),
            {"i": row.itinerary_id, "n": body.day_index},
        ).first()
        if target is None:
            raise invalid("bad_day", "day_index is not a day of this itinerary")
        target_day_id = target.id
    moving_day = target_day_id != row.day_id
    _check_overlap(conn, target_day_id, busy_span(start, end, minutes), item_id)

    if moving_day or ("position" in changed and body.position is not None):
        count = conn.execute(
            text("SELECT count(*) FROM app.itinerary_item WHERE day_id = :d"), {"d": target_day_id}
        ).scalar_one()
        limit = count + 1 if moving_day else count
        if moving_day and count >= MAX_ITEMS_PER_DAY:
            raise conflict("day_full", f"at most {MAX_ITEMS_PER_DAY} items per day")
        new_position = body.position if body.position is not None else limit
        if new_position > limit:
            raise invalid("bad_position", f"position must be between 1 and {limit}")
        # Take the item out of its day (compacting it), then open a gap in the target day.
        conn.execute(
            text(
                "UPDATE app.itinerary_item SET position = position - 1 WHERE day_id = :d AND position > :p"
            ),
            {"d": row.day_id, "p": row.position},
        )
        conn.execute(
            text(
                "UPDATE app.itinerary_item SET position = position + 1 WHERE day_id = :d AND position >= :p AND id <> :i"
            ),
            {"d": target_day_id, "p": new_position, "i": item_id},
        )
        conn.execute(
            text("UPDATE app.itinerary_item SET day_id = :d, position = :p WHERE id = :i"),
            {"d": target_day_id, "p": new_position, "i": item_id},
        )
    sets = [
        "start_time = :start",
        "end_time = :end",
        "duration_minutes = :minutes",
        "duration_source = :source",
        "updated_at = now()",
    ]
    params: dict[str, Any] = {
        "i": item_id,
        "start": start,
        "end": end,
        "minutes": minutes,
        "source": source,
    }
    if "locked" in changed and body.locked is not None and not leg:
        sets.append("locked = :locked")
        params["locked"] = body.locked
    if "transport" in changed and body.transport is not None:
        sets += ["transport = CAST(:transport AS jsonb)", "display_name = :name"]
        params["transport"] = body.transport.model_dump_json()
        params["name"] = body.transport.display_name()
    conn.execute(text(f"UPDATE app.itinerary_item SET {', '.join(sets)} WHERE id = :i"), params)
    drop_stale_transfers(conn, [row.day_id, target_day_id])
    _bump(conn, row.itinerary_id)
    return require_item(conn, installation_id, item_id)


def delete_item(conn: Connection, installation_id: uuid.UUID, item_id: uuid.UUID) -> None:
    row = conn.execute(
        text(
            "SELECT i.day_id, i.position, d.itinerary_id, t.status AS trip_status"
            " FROM app.itinerary_item i JOIN app.itinerary_day d ON d.id = i.day_id"
            " JOIN app.itinerary it ON it.id = d.itinerary_id JOIN app.trip t ON t.id = it.trip_id"
            " WHERE i.id = :i AND t.installation_id = :n FOR UPDATE OF i"
        ),
        {"i": item_id, "n": installation_id},
    ).first()
    if row is None:
        raise not_found("item")
    plan_state.snapshot(conn, row.itinerary_id)
    conn.execute(text("DELETE FROM app.itinerary_item WHERE id = :i"), {"i": item_id})
    conn.execute(
        text(
            "UPDATE app.itinerary_item SET position = position - 1 WHERE day_id = :d AND position > :p"
        ),
        {"d": row.day_id, "p": row.position},
    )
    drop_stale_transfers(conn, [row.day_id])
    _bump(conn, row.itinerary_id)
