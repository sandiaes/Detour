"""An itinerary's plan as stored rows: read, write, snapshot and restore (Phase 7, ADR 018).

A **state** is a JSON-safe dict of an itinerary's days, items and transfers as rows, with its
summary and the engine, configuration and data versions:

    {"days": [{id, day_index, date, base_city_id, base_city_name, arrival}],
     "items": [{id, day_id, position, type, place_id, user_place_id, display_name,
                lat, lon, start_minute, end_minute, duration_minutes, duration_source, origin,
                locked, reasons}],
     "transfers": [{from_item_id, to_item_id, mode, seconds, meters, confidence}],
     "summary": {...}, "engine_version", "config_version", "import_run_id"}

Items keep only their own snapshots (name and point); restaurant attributes stay in ``geo`` and
are joined at read time (data model section 1). The same writer applies an accepted proposal and
restores an earlier version, so what is applied is exactly what was previewed.
"""

import json
import math
import uuid
from datetime import date, time
from typing import Any, cast

from sqlalchemy import Connection, text

from detour_api.planner.recalc import Entry, RDay, RPlan, entry_key
from detour_api.planner.types import Issue, Leg

# Versions kept per itinerary (the oldest are removed first).
MAX_VERSIONS = 30
# A past trip keeps fewer undo versions (ADR 006, amendment of 2026-11-16).
MAX_VERSIONS_PAST = 5

State = dict[str, Any]


def _minute(t: time | None) -> int | None:
    return None if t is None else t.hour * 60 + t.minute


def _time(m: int | None) -> time | None:
    return None if m is None else time(m // 60, m % 60)


def read_state(conn: Connection, itinerary_id: uuid.UUID) -> State:
    it = conn.execute(
        text(
            "SELECT engine_version, config_version, import_run_id, summary FROM app.itinerary"
            " WHERE id = :i"
        ),
        {"i": itinerary_id},
    ).one()
    days = conn.execute(
        text(
            "SELECT id, day_index, date, base_city_id, base_city_name, arrival_mode,"
            " arrival_seconds, arrival_meters, arrival_confidence FROM app.itinerary_day"
            " WHERE itinerary_id = :i ORDER BY day_index"
        ),
        {"i": itinerary_id},
    ).all()
    items = conn.execute(
        text(
            "SELECT i.id, i.day_id, i.position, i.type, i.place_id, i.user_place_id,"
            " i.display_name, ST_Y(i.display_point) AS lat, ST_X(i.display_point) AS lon,"
            " i.start_time, i.end_time, i.duration_minutes, i.duration_source, i.origin,"
            " i.locked, i.reasons FROM app.itinerary_item i"
            " JOIN app.itinerary_day d ON d.id = i.day_id WHERE d.itinerary_id = :i"
            " ORDER BY d.day_index, i.position"
        ),
        {"i": itinerary_id},
    ).all()
    transfers = conn.execute(
        text(
            "SELECT t.from_item_id, t.to_item_id, t.mode, t.seconds, t.meters, t.confidence"
            " FROM app.transfer t JOIN app.itinerary_item i ON i.id = t.from_item_id"
            " JOIN app.itinerary_day d ON d.id = i.day_id WHERE d.itinerary_id = :i"
            " ORDER BY t.from_item_id"
        ),
        {"i": itinerary_id},
    ).all()
    return {
        "engine_version": it.engine_version,
        "config_version": it.config_version,
        "import_run_id": None if it.import_run_id is None else str(it.import_run_id),
        "summary": it.summary or {},
        "days": [
            {
                "id": str(d.id),
                "day_index": d.day_index,
                "date": None if d.date is None else d.date.isoformat(),
                "base_city_id": d.base_city_id,
                "base_city_name": d.base_city_name,
                "arrival": None
                if d.arrival_mode is None
                else {
                    "mode": d.arrival_mode,
                    "seconds": d.arrival_seconds,
                    "meters": d.arrival_meters,
                    "confidence": d.arrival_confidence,
                },
            }
            for d in days
        ],
        "items": [
            {
                "id": str(r.id),
                "day_id": str(r.day_id),
                "position": r.position,
                "type": r.type,
                "place_id": None if r.place_id is None else str(r.place_id),
                "user_place_id": None if r.user_place_id is None else str(r.user_place_id),
                "display_name": r.display_name,
                "lat": r.lat,
                "lon": r.lon,
                "start_minute": _minute(r.start_time),
                "end_minute": _minute(r.end_time),
                "duration_minutes": r.duration_minutes,
                "duration_source": r.duration_source,
                "origin": r.origin,
                "locked": r.locked,
                "reasons": list(r.reasons),
            }
            for r in items
        ],
        "transfers": [
            {
                "from_item_id": str(t.from_item_id),
                "to_item_id": str(t.to_item_id),
                "mode": t.mode,
                "seconds": t.seconds,
                "meters": t.meters,
                "confidence": t.confidence,
            }
            for t in transfers
        ],
    }


def write_state(conn: Connection, itinerary_id: uuid.UUID, state: State) -> None:
    """Make the itinerary's days, items and transfers exactly the state's. Day rows are kept and
    updated; a stop edit (ADR 024) adds or removes days, so rows the state does not have are
    deleted (with their items) and new ones inserted. The caller sets version and summary."""
    keep = [d["id"] for d in state["days"]]
    conn.execute(
        text(
            "DELETE FROM app.itinerary_day WHERE itinerary_id = :i"
            " AND NOT (id = ANY(CAST(:keep AS uuid[])))"
        ),
        {"i": itinerary_id, "keep": keep},
    )
    # Day numbers are unique per plan: move the kept rows out of the way before renumbering.
    conn.execute(
        text("UPDATE app.itinerary_day SET day_index = day_index + 1000 WHERE itinerary_id = :i"),
        {"i": itinerary_id},
    )
    for d in state["days"]:
        conn.execute(
            text(
                "INSERT INTO app.itinerary_day (id, itinerary_id, day_index, date)"
                " VALUES (:d, :i, :n, :date)"
                " ON CONFLICT (id) DO UPDATE SET day_index = EXCLUDED.day_index,"
                " date = EXCLUDED.date"
            ),
            {
                "d": uuid.UUID(d["id"]),
                "i": itinerary_id,
                "n": d["day_index"],
                "date": d["date"],
            },
        )
    for d in state["days"]:
        arrival = d["arrival"]
        conn.execute(
            text(
                "UPDATE app.itinerary_day SET base_city_id = :city, base_city_name = :name,"
                " arrival_mode = :am, arrival_seconds = :asec, arrival_meters = :amet,"
                " arrival_confidence = :aconf WHERE id = :d AND itinerary_id = :i"
            ),
            {
                "d": uuid.UUID(d["id"]),
                "i": itinerary_id,
                "city": d["base_city_id"],
                "name": d["base_city_name"],
                "am": None if arrival is None else arrival["mode"],
                "asec": None if arrival is None else arrival["seconds"],
                "amet": None if arrival is None else arrival["meters"],
                "aconf": None if arrival is None else arrival["confidence"],
            },
        )
    conn.execute(
        text(
            "DELETE FROM app.itinerary_item WHERE day_id IN"
            " (SELECT id FROM app.itinerary_day WHERE itinerary_id = :i)"
        ),
        {"i": itinerary_id},
    )
    for r in state["items"]:
        conn.execute(
            text(
                """
                INSERT INTO app.itinerary_item (id, day_id, position, type, place_id,
                    user_place_id, display_name, display_point, start_time, end_time,
                    duration_minutes, duration_source, origin, locked, reasons)
                VALUES (:id, :d, :pos, :type, :place, :uplace, :name,
                    CASE WHEN CAST(:lat AS float8) IS NULL THEN NULL
                         ELSE ST_SetSRID(ST_MakePoint(:lon, :lat), 4326) END,
                    :start, :end, :minutes, :source, :origin, :locked, :reasons)
                """
            ),
            {
                "id": uuid.UUID(r["id"]),
                "d": uuid.UUID(r["day_id"]),
                "pos": r["position"],
                "type": r["type"],
                "place": None if r["place_id"] is None else uuid.UUID(r["place_id"]),
                "uplace": None if r["user_place_id"] is None else uuid.UUID(r["user_place_id"]),
                "name": r["display_name"],
                "lat": r["lat"],
                "lon": r["lon"],
                "start": _time(r["start_minute"]),
                "end": _time(r["end_minute"]),
                "minutes": r["duration_minutes"],
                "source": r["duration_source"],
                "origin": r["origin"],
                "locked": r["locked"],
                "reasons": r["reasons"],
            },
        )
    for t in state["transfers"]:
        conn.execute(
            text(
                "INSERT INTO app.transfer (id, from_item_id, to_item_id, mode, seconds, meters,"
                " confidence) VALUES (:id, :f, :t, :m, :s, :me, :c)"
            ),
            {
                "id": uuid.uuid4(),
                "f": uuid.UUID(t["from_item_id"]),
                "t": uuid.UUID(t["to_item_id"]),
                "m": t["mode"],
                "s": t["seconds"],
                "me": t["meters"],
                "c": t["confidence"],
            },
        )


def snapshot(
    conn: Connection, itinerary_id: uuid.UUID, change_set_id: uuid.UUID | None = None
) -> None:
    """Keep the itinerary's current version before it is replaced, then drop versions beyond
    ``MAX_VERSIONS`` (oldest first)."""
    version = conn.execute(
        text("SELECT version FROM app.itinerary WHERE id = :i"), {"i": itinerary_id}
    ).scalar_one()
    conn.execute(
        text(
            "INSERT INTO app.itinerary_version (itinerary_id, version, state, change_set_id)"
            " VALUES (:i, :v, CAST(:s AS jsonb), :c)"
            " ON CONFLICT (itinerary_id, version) DO UPDATE SET state = EXCLUDED.state,"
            " change_set_id = EXCLUDED.change_set_id, replaced_at = now()"
        ),
        {
            "i": itinerary_id,
            "v": version,
            "s": json.dumps(read_state(conn, itinerary_id), sort_keys=True),
            "c": change_set_id,
        },
    )
    past = conn.execute(
        text(
            "SELECT t.status = 'past' FROM app.itinerary i JOIN app.trip t ON t.id = i.trip_id"
            " WHERE i.id = :i"
        ),
        {"i": itinerary_id},
    ).scalar_one()
    conn.execute(
        text("DELETE FROM app.itinerary_version WHERE itinerary_id = :i AND version <= :v - :n"),
        {"i": itinerary_id, "v": version, "n": MAX_VERSIONS_PAST if past else MAX_VERSIONS},
    )


def prune_versions(conn: Connection, trip_id: uuid.UUID, keep: int = MAX_VERSIONS_PAST) -> int:
    """Keeps only the newest ``keep`` versions of every itinerary of a trip (when it becomes
    past). Returns how many were deleted."""
    deleted = conn.execute(
        text(
            "DELETE FROM app.itinerary_version v USING app.itinerary i WHERE v.itinerary_id = i.id"
            " AND i.trip_id = :t AND v.version <= i.version - :n - 1"
        ),
        {"t": trip_id, "n": keep},
    )
    return deleted.rowcount


def stored_version(conn: Connection, itinerary_id: uuid.UUID, version: int) -> State | None:
    row = conn.execute(
        text("SELECT state FROM app.itinerary_version WHERE itinerary_id = :i AND version = :v"),
        {"i": itinerary_id, "v": version},
    ).first()
    return None if row is None else cast(State, row.state)


# -- between stored rows and the recalculation's plan ---------------------------------------------


def _leg(t: dict[str, Any]) -> Leg:
    return Leg(
        mode=t["mode"],
        seconds=t["seconds"],
        meters=t["meters"],
        minutes=math.ceil(t["seconds"] / 60),
        confidence=t["confidence"],
        estimate_reason=None,
    )


def unscheduled(state: State) -> list[Issue]:
    """Days with items the recalculation cannot lay out: free time, or an item without a time or
    a place (only hand edits make these)."""
    by_day: dict[str, list[str]] = {}
    for r in state["items"]:
        if r["type"] == "free_time" or r["start_minute"] is None or r["lat"] is None:
            by_day.setdefault(r["day_id"], []).append(r["display_name"])
    return [
        Issue("UNSCHEDULED_ITEMS", {"day": d["day_index"], "items": ", ".join(by_day[d["id"]])})
        for d in state["days"]
        if d["id"] in by_day
    ]


def to_rplan(state: State, profile: str, categories: dict[str, str] | None = None) -> RPlan:
    """The state as the recalculation sees it (``unscheduled`` must be empty). Categories come
    from ``geo`` at read time, when given. Restaurant and café stops carry no venue type or cuisine
    here: the recalculation keeps them as they are (ADR 026)."""
    cats = categories or {}
    transfers = {t["from_item_id"]: t for t in state["transfers"]}
    by_day: dict[str, list[dict[str, Any]]] = {}
    for r in state["items"]:
        by_day.setdefault(r["day_id"], []).append(r)
    days: list[RDay] = []
    for d in state["days"]:
        entries: list[Entry] = []
        for r in sorted(by_day.get(d["id"], []), key=lambda r: r["position"]):
            kind = r["type"]
            t = transfers.get(r["id"])
            entries.append(
                Entry(
                    key=entry_key(kind, r["place_id"], r["user_place_id"]),
                    kind=kind,
                    name=r["display_name"],
                    lat=r["lat"],
                    lon=r["lon"],
                    start_minute=r["start_minute"],
                    end_minute=r["end_minute"],
                    duration_minutes=r["duration_minutes"],
                    duration_source=r["duration_source"],
                    origin=r["origin"],
                    locked=r["locked"],
                    reasons=tuple(r["reasons"]),
                    transfer=None if t is None else _leg(t),
                    place_id=r["place_id"],
                    user_place_id=r["user_place_id"],
                    category=None if kind == "meal" else cats.get(r["place_id"] or ""),
                    item_id=r["id"],
                )
            )
        arrival = d["arrival"]
        # A leg with no known time (ADR 024) has no figures: it is a flag, not a Leg.
        unknown = arrival is not None and arrival["mode"] == "unknown"
        days.append(
            RDay(
                day_index=d["day_index"],
                date=None if d["date"] is None else date.fromisoformat(d["date"]),
                base_city_id=d["base_city_id"],
                base_city_name=d["base_city_name"],
                items=tuple(entries),
                arrival=None if arrival is None or unknown else _leg(arrival),
                arrival_unknown=unknown,
            )
        )
    return RPlan(profile, tuple(days))


def from_rplan(
    plan: RPlan, current: State, summary: dict[str, Any], versions: dict[str, Any]
) -> State:
    """A state for the recalculated plan: the current day rows, an id for every new item."""
    # A stop edit (ADR 024) may add days: they get new ids; days beyond the plan are dropped by
    # write_state.
    day_ids = {d["day_index"]: d["id"] for d in current["days"]}
    days: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    transfers: list[dict[str, Any]] = []
    for d in plan.days:
        day_id = day_ids.get(d.day_index) or str(uuid.uuid4())
        a = d.arrival
        days.append(
            {
                "id": day_id,
                "day_index": d.day_index,
                "date": None if d.date is None else d.date.isoformat(),
                "base_city_id": d.base_city_id,
                "base_city_name": d.base_city_name,
                "arrival": {
                    "mode": "unknown",
                    "seconds": None,
                    "meters": None,
                    "confidence": "unknown",
                }
                if d.arrival_unknown
                else None
                if a is None
                else {
                    "mode": a.mode,
                    "seconds": a.seconds,
                    "meters": a.meters,
                    "confidence": a.confidence,
                },
            }
        )
        ids = [e.item_id or str(uuid.uuid4()) for e in d.items]
        for pos, (item_id, e) in enumerate(zip(ids, d.items, strict=True), start=1):
            items.append(
                {
                    "id": item_id,
                    "day_id": day_id,
                    "position": pos,
                    "type": e.kind,
                    "place_id": e.place_id,
                    "user_place_id": e.user_place_id,
                    "display_name": e.name,
                    "lat": e.lat,
                    "lon": e.lon,
                    "start_minute": e.start_minute,
                    "end_minute": e.end_minute,
                    "duration_minutes": e.duration_minutes,
                    "duration_source": e.duration_source,
                    "origin": e.origin,
                    "locked": e.locked,
                    "reasons": list(e.reasons),
                }
            )
            if e.transfer is not None and pos < len(ids):
                transfers.append(
                    {
                        "from_item_id": item_id,
                        "to_item_id": ids[pos],
                        "mode": e.transfer.mode,
                        "seconds": e.transfer.seconds,
                        "meters": e.transfer.meters,
                        "confidence": e.transfer.confidence,
                    }
                )
    return {**versions, "summary": summary, "days": days, "items": items, "transfers": transfers}
