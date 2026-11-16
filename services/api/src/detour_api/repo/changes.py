"""Change sets and itinerary versions (Phase 7, ADR 018): the database side of recalculation.

``load_context`` reads what a preview needs (the itinerary's current state, the place to add or
the item to remove, the sights around the plan's bases and the addition, the towns near the
addition). ``save`` stores a previewed change set; ``apply`` keeps the current
version in ``app.itinerary_version`` and writes the proposal exactly as previewed; ``discard``
closes it. The recalculation itself runs between ``load_context`` and ``save``, outside any
transaction, because it may wait on the routing provider.
"""

import json
import math
import uuid
from dataclasses import dataclass
from datetime import time
from typing import Any, Literal

from sqlalchemy import Connection, text

from detour_api.errors import ApiError, conflict, invalid, not_found
from detour_api.models.changes import (
    ChangeDiff,
    ChangeSet,
    ChangeSetApplied,
    ChangeSetCreate,
    DiffBase,
    DiffItem,
    DiffLeg,
    DiffMove,
    DiffRetime,
    ItineraryVersion,
    ProposedPlan,
    ProposedStart,
    ProposedStop,
    ProposedTransfer,
)
from detour_api.planner.config import PlannerConfig
from detour_api.planner.diff import PlanDiff
from detour_api.planner.durations import visit_minutes
from detour_api.planner.reasons import issue_text
from detour_api.planner.recalc import Addition, RecalcConfig, RecalcInput, entry_key
from detour_api.planner.types import BaseCity, Candidate, Issue, Note
from detour_api.repo import geo, itineraries, planning, trips, user_places
from detour_api.repo.geo import METERS_PER_DEGREE
from detour_api.repo.plan_state import (
    State,
    read_state,
    snapshot,
    stored_version,
    unscheduled,
    write_state,
)
from detour_api.repo.plan_state import to_rplan as _to_rplan

# Codes of the notes that describe one change (shown with the preview).
CHANGE_NOTES = frozenset(
    {
        "PLACE_ADDED",
        "PLACE_REMOVED",
        "PLAN_RESTORED",
        "NEW_BASE_DAY",
        "VISITS_MOVED",
        "VISITS_DROPPED",
        "STOP_REMOVED_ITEMS",
        "STOPS_CHANGED",
        "OPTIMIZED",
        "OPTIMIZE_ESTIMATED",
        "OPTIMIZE_NOT_SHORTEST",
        "OPTIMIZE_NO_HOURS",
        "OPTIMIZE_KEPT",
        "OPTIMIZE_FAR_KEPT",
        "OPTIMIZE_UNDONE",
    }
)


@dataclass(frozen=True)
class Context:
    itinerary_id: uuid.UUID
    version: int
    profile: str
    state: State
    action: str
    target_name: str
    data_version: str | None
    recalc: RecalcInput | None  # None when the change restores a stored version
    addition: Addition | None = None
    removed_key: str | None = None
    place_id: uuid.UUID | None = None
    user_place_id: uuid.UUID | None = None
    item_id: uuid.UUID | None = None
    duration_minutes: int | None = None
    restores: tuple[int, State] | None = None
    # add_place: only this day was allowed (stored as ``slot_day``; ADR 021, step 4)
    only_day: int | None = None


def impossible(issues: list[Issue]) -> ApiError:

    params = [{"code": i.code, "text": issue_text(i.code, i.params)} for i in issues]
    return ApiError(
        422,
        "recalculation_impossible",
        " ".join(p["text"] for p in params),
        extra={"issues": params},
    )


def _itinerary_row(conn: Connection, person_id: uuid.UUID, itinerary_id: uuid.UUID) -> Any:
    row = conn.execute(
        text(
            "SELECT it.id, it.profile, it.version, t.status AS trip_status, t.destination_kind,"
            " t.destination_ref FROM app.itinerary it JOIN app.trip t ON t.id = it.trip_id"
            " WHERE it.id = :i AND EXISTS (SELECT 1 FROM app.trip_member tm WHERE tm.trip_id = t.id AND tm.person_id = :n)"
        ),
        {"i": itinerary_id, "n": person_id},
    ).first()
    if row is None:
        raise not_found("itinerary")
    trips.refuse_if_past(row.trip_status)
    return row


def _box(lat: float, lon: float, radius_m: float) -> dict[str, float]:
    dlat = radius_m / METERS_PER_DEGREE
    dlon = radius_m / (METERS_PER_DEGREE * max(math.cos(math.radians(lat)), 0.01))
    return {"x1": lon - dlon, "y1": lat - dlat, "x2": lon + dlon, "y2": lat + dlat}


def _cities(conn: Connection, ids: list[int]) -> dict[int, BaseCity]:
    rows = conn.execute(
        text(
            "SELECT id, name, ST_Y(geom) AS lat, ST_X(geom) AS lon, population FROM geo.city"
            " WHERE id = ANY(:ids)"
        ),
        {"ids": ids},
    ).all()
    return {int(r.id): BaseCity(int(r.id), r.name, r.lat, r.lon, r.population) for r in rows}


def _towns_near(conn: Connection, lat: float, lon: float, radius_m: int) -> list[BaseCity]:
    rows = conn.execute(
        text(
            "SELECT id, name, ST_Y(geom) AS lat, ST_X(geom) AS lon, population FROM geo.city"
            " WHERE geom && ST_MakeEnvelope(:x1, :y1, :x2, :y2, 4326)"
            " AND NOT (COALESCE(feature_code, '') = ANY (:sections)) ORDER BY id"
        ),
        {**_box(lat, lon, radius_m), "sections": list(planning.NOT_A_BASE)},
    ).all()
    return [BaseCity(int(r.id), r.name, r.lat, r.lon, r.population) for r in rows]


def _head(
    conn: Connection, person_id: uuid.UUID, itinerary_id: uuid.UUID
) -> tuple[Any, geo.ResolvedDestination, State, dict[str, Any]]:
    row = _itinerary_row(conn, person_id, itinerary_id)
    if row.profile not in ("essentials", "wider"):
        raise conflict(
            "not_recalculable", "only planned itineraries are recalculated; edit this one by hand"
        )
    if row.destination_kind == "place":
        raise ApiError(
            409,
            "destination_not_plannable",
            "a trip to a place outside the imported regions is edited by hand",
        )
    # A multi-city trip's destination_ref is its first stop's city (ADR 024).
    kind = "city" if row.destination_kind == "route" else row.destination_kind
    dest = geo.resolve_destination(conn, kind, row.destination_ref)
    if dest is None:
        raise invalid("destination_not_found", "the trip's destination is no longer in the data")
    if dest.region_id is None or dest.region_status != "available":
        raise ApiError(409, "region_not_available", "this destination's region is not available")
    run = conn.execute(
        text("SELECT current_import_run_id FROM geo.region WHERE id = :r"), {"r": dest.region_id}
    ).scalar_one_or_none()
    state = read_state(conn, itinerary_id)
    common: dict[str, Any] = {
        "itinerary_id": itinerary_id,
        "version": row.version,
        "profile": row.profile,
        "state": state,
        "data_version": None if run is None else str(run),
    }
    return row, dest, state, common


def load_context(
    conn: Connection,
    person_id: uuid.UUID,
    itinerary_id: uuid.UUID,
    body: ChangeSetCreate,
    config: PlannerConfig,
    rconfig: RecalcConfig,
) -> Context:
    row, dest, state, common = _head(conn, person_id, itinerary_id)

    addition: Addition | None = None
    removed_key: str | None = None
    if body.action == "remove_place":
        item = next((r for r in state["items"] if r["id"] == str(body.item_id)), None)
        if item is None:
            raise not_found("item")
        removed_key = entry_key(item["type"], item["place_id"], item["user_place_id"])
        restored = _restorable(conn, itinerary_id, row.version, item)
        if restored is not None:
            return Context(
                **common,
                action="remove_place",
                target_name=item["display_name"],
                recalc=None,
                removed_key=removed_key,
                item_id=body.item_id,
                restores=restored,
            )
        point = (item["lat"], item["lon"]) if item["lat"] is not None else None
        target_name = item["display_name"]
    else:
        addition = _addition(conn, person_id, body)
        point = (addition.lat, addition.lon)
        target_name = addition.name

    recalc_input = _plan_input(conn, row, dest, state, point, addition, config, rconfig)
    return Context(
        **common,
        action=body.action,
        target_name=target_name,
        recalc=recalc_input,
        addition=addition,
        removed_key=removed_key,
        place_id=body.place_id,
        user_place_id=body.user_place_id,
        item_id=body.item_id,
        duration_minutes=body.duration_minutes,
        only_day=body.day,
    )


def _plan_input(
    conn: Connection,
    row: Any,
    dest: geo.ResolvedDestination,
    state: State,
    point: tuple[float, float] | None,
    addition: Addition | None,
    config: PlannerConfig,
    rconfig: RecalcConfig,
) -> RecalcInput:
    issues = unscheduled(state)
    if issues:
        raise impossible(issues)
    assert dest.region_id is not None  # noqa: S101 - checked by _head
    rplan = _to_rplan(state, row.profile)
    base_ids = sorted({d.base_city_id for d in rplan.days if d.base_city_id is not None})
    bases = _cities(conn, base_ids)
    missing = [b for b in base_ids if b not in bases]
    if missing:
        raise invalid("base_city_not_found", "a base city of this plan is no longer in the data")
    radius = max(p.radius_m for p in config.profiles)
    points = [(b.lat, b.lon) for b in bases.values()]
    if point is not None:
        points.append(point)
    route = row.destination_kind == "route"
    countries = _countries(conn, base_ids)
    # A multi-city trip may span regions: each base's own region is read too (ADR 024).
    regions = [dest.region_id]
    if route:
        for code in sorted({c for c in countries.values() if c}):
            covering = geo.region_for_country(conn, code)
            if covering and covering[1] == "available" and covering[0] not in regions:
                regions.append(covering[0])
    cands: dict[str, Candidate] = {}
    for region in regions:
        for lat, lon in points:
            for c in planning.load_candidates(conn, region, lat, lon, radius):
                cands.setdefault(c.place_id, c)
    towns: list[BaseCity] = []
    if addition is not None:
        towns = _towns_near(conn, addition.lat, addition.lon, rconfig.new_base_town_m)
    return RecalcInput(
        plan=rplan,
        notes=tuple(
            Note(n["code"], n.get("params", {})) for n in state["summary"].get("notes", [])
        ),
        bases=bases,
        candidates=tuple(cands[k] for k in sorted(cands)),
        towns=tuple(towns),
        single_city=not route and not geo.area_planning_allowed(dest),
        route=route,
        rail_bases=frozenset(b for b, c in countries.items() if c in config.single_city_countries),
    )


def cities(conn: Connection, ids: list[int]) -> dict[int, BaseCity]:
    return _cities(conn, ids)


def countries(conn: Connection, ids: list[int]) -> dict[int, str | None]:
    return _countries(conn, ids)


def region_of(conn: Connection, country_iso2: str | None) -> str | None:
    """The available region that covers a country, if any."""
    if country_iso2 is None:
        return None
    covering = geo.region_for_country(conn, country_iso2)
    return covering[0] if covering and covering[1] == "available" else None


def _countries(conn: Connection, ids: list[int]) -> dict[int, str | None]:
    """The country of each base city: whether a leg into or out of it has a time (ADR 024)."""
    if not ids:
        return {}
    rows = conn.execute(
        text("SELECT id, country_iso2 FROM geo.city WHERE id = ANY(:ids)"), {"ids": ids}
    ).all()
    return {int(r.id): r.country_iso2 for r in rows}


def _addition(conn: Connection, person_id: uuid.UUID, body: ChangeSetCreate) -> Addition:
    if body.place_id is not None:
        found = geo.place_exists(conn, body.place_id, person_id)
        if found is None or not found[4]:
            raise invalid("place_not_found", "place_id is not an active place")
        kind, name, lat, lon, _, default_minutes, category = found
        if kind != "attraction":
            raise invalid(
                "wrong_place_kind", "only sights and your own places can be added to a plan here"
            )
        source: Literal["category_default", "user"] = "category_default"
        minutes = default_minutes or visit_minutes(category)
        if body.duration_minutes is not None:
            minutes, source = body.duration_minutes, "user"
        return Addition(
            key=entry_key("visit", str(body.place_id), None),
            name=name,
            lat=lat,
            lon=lon,
            duration_minutes=minutes,
            duration_source=source,
            place_id=str(body.place_id),
            category=category,
        )
    assert body.user_place_id is not None  # noqa: S101 - guaranteed by ChangeSetCreate
    place = user_places.get(conn, person_id, body.user_place_id)
    if place is None:
        raise invalid("user_place_not_found", "user_place_id is not one of your places")
    if place.kind in ("restaurant", "cafe"):
        raise invalid(
            "wrong_place_kind",
            "a restaurant or café is added by choosing its day and time, not through a recalculation",
        )
    if body.duration_minutes is None:
        raise invalid("duration_required", "say how long to stay at your own place")
    return Addition(
        key=entry_key("visit", None, str(body.user_place_id)),
        name=place.name,
        lat=place.lat,
        lon=place.lon,
        duration_minutes=body.duration_minutes,
        duration_source="user",
        user_place_id=str(body.user_place_id),
    )


def _restorable(
    conn: Connection, itinerary_id: uuid.UUID, version: int, item: dict[str, Any]
) -> tuple[int, State] | None:
    """Undo through versioning: removing the place the latest accepted change set added, with no
    change since, restores the version before it."""
    row = conn.execute(
        text(
            "SELECT base_version FROM app.change_set WHERE itinerary_id = :i AND status = 'applied'"
            " AND action = 'add_place' AND result_version = :v"
            " AND (place_id = CAST(:p AS uuid) OR user_place_id = CAST(:u AS uuid))"
        ),
        {"i": itinerary_id, "v": version, "p": item["place_id"], "u": item["user_place_id"]},
    ).first()
    if row is None or item["type"] != "visit":
        return None
    state = stored_version(conn, itinerary_id, row.base_version)
    return None if state is None else (row.base_version, state)


# -- the diff as the API shows it ------------------------------------------------------------------


def clock(minute: int) -> time:
    """A minute of the day as a time (the diff's and suggestions' clock)."""
    return _t(minute)


def _t(minute: int) -> time:
    return time(minute // 60, minute % 60)


def diff_model(d: PlanDiff) -> ChangeDiff:
    return ChangeDiff(
        added=[
            DiffItem(
                day=i.day,
                kind=i.kind,
                name=i.name,
                start_time=_t(i.start_minute),
                end_time=_t(i.end_minute),
                added_by_you=i.origin == "user",
            )
            for i in d.added
        ],
        removed=[
            DiffItem(
                day=i.day,
                kind=i.kind,
                name=i.name,
                start_time=_t(i.start_minute),
                end_time=_t(i.end_minute),
                added_by_you=i.origin == "user",
            )
            for i in d.removed
        ],
        moved=[
            DiffMove(
                kind=m.kind,
                name=m.name,
                from_day=m.from_day,
                to_day=m.to_day,
                old_start_time=_t(m.old_start_minute),
                new_start_time=_t(m.new_start_minute),
            )
            for m in d.moved
        ],
        retimed=[
            DiffRetime(
                kind=r.kind,
                name=r.name,
                day=r.day,
                old_start_time=_t(r.old_start_minute),
                new_start_time=_t(r.new_start_minute),
            )
            for r in d.retimed
        ],
        base_changes=[
            DiffBase(day=b.day, old_base_name=b.old_name, new_base_name=b.new_name)
            for b in d.base_changes
        ],
        days_changed=list(d.days_changed),
        travel_minutes_before=d.travel_minutes_before,
        travel_minutes_after=d.travel_minutes_after,
        travel_minutes_added=d.travel_minutes_added,
        estimated_legs=[
            DiffLeg(
                day=leg.day,
                from_name=leg.from_name,
                to_name=leg.to_name,
                mode=leg.mode,
                minutes=leg.minutes,
            )
            for leg in d.estimated_legs
        ],
    )


# -- change sets ---------------------------------------------------------------------------------

_CHANGE_COLUMNS = (
    "id, itinerary_id, action, target_name, status, base_version, restores_version,"
    " result_version, diff, notes, created_at, decided_at"
)


def _proposed(row: Any) -> ProposedPlan | None:
    """The proposed order of an open Optimize preview, from the stored proposal."""
    proposal = getattr(row, "proposal", None)
    if row.action != "optimize" or row.status != "pending" or not proposal:
        return None
    day_of = {d["id"]: d["day_index"] for d in proposal["days"]}
    return ProposedPlan(
        stops=[
            ProposedStop(
                item_id=r["id"],
                day_index=day_of[r["day_id"]],
                position=r["position"],
                start_time=None if r["start_minute"] is None else clock(r["start_minute"]),
                end_time=None if r["end_minute"] is None else clock(r["end_minute"]),
            )
            for r in proposal["items"]
        ],
        transfers=[ProposedTransfer.model_validate(t) for t in proposal["transfers"]],
        starts=[ProposedStart.model_validate(t) for t in proposal.get("starts", [])],
    )


def _change_set(row: Any) -> ChangeSet:
    return ChangeSet(
        id=row.id,
        itinerary_id=row.itinerary_id,
        action=row.action,
        target_name=row.target_name,
        status=row.status,
        base_version=row.base_version,
        restores_version=row.restores_version,
        result_version=row.result_version,
        diff=ChangeDiff.model_validate(row.diff),
        notes=itineraries.render_notes(row.notes),
        proposed=_proposed(row),
        created_at=row.created_at,
        decided_at=row.decided_at,
    )


def save(
    conn: Connection,
    person_id: uuid.UUID,
    ctx: Context,
    proposal: State,
    diff: ChangeDiff,
    notes: list[Note],
) -> ChangeSet:
    _itinerary_row(conn, person_id, ctx.itinerary_id)
    current = conn.execute(
        text("SELECT version FROM app.itinerary WHERE id = :i FOR UPDATE"), {"i": ctx.itinerary_id}
    ).scalar_one()
    if current != ctx.version:
        raise conflict("change_set_stale", "the plan changed while the preview was made; try again")
    # One open preview per itinerary: an older one can no longer be applied.
    conn.execute(
        text(
            "UPDATE app.change_set SET status = 'expired', proposal = NULL, decided_at = now()"
            " WHERE itinerary_id = :i AND status = 'pending'"
        ),
        {"i": ctx.itinerary_id},
    )
    change_id = uuid.uuid4()
    conn.execute(
        text(
            """
            INSERT INTO app.change_set (id, itinerary_id, base_version, action, place_id,
                user_place_id, item_id, duration_minutes, target_name, restores_version,
                slot_day, proposal, diff, notes)
            VALUES (:id, :i, :v, :a, :p, :u, :item, :minutes, :name, :restores,
                :slot_day,
                CAST(:proposal AS jsonb), CAST(:diff AS jsonb), CAST(:notes AS jsonb))
            """
        ),
        {
            "id": change_id,
            "i": ctx.itinerary_id,
            "v": ctx.version,
            "a": ctx.action,
            "p": ctx.place_id,
            "u": ctx.user_place_id,
            "item": ctx.item_id,
            "minutes": ctx.duration_minutes,
            "name": ctx.target_name,
            "restores": None if ctx.restores is None else ctx.restores[0],
            "slot_day": ctx.only_day,
            "proposal": json.dumps(proposal, sort_keys=True),
            "diff": diff.model_dump_json(),
            "notes": json.dumps([{"code": n.code, "params": n.params} for n in notes]),
        },
    )
    return require(conn, person_id, change_id)


def _row(conn: Connection, person_id: uuid.UUID, change_id: uuid.UUID, lock: bool) -> Any:
    row = conn.execute(
        text(
            f"SELECT c.{_CHANGE_COLUMNS.replace(', ', ', c.')}, c.proposal, t.status AS trip_status"
            " FROM app.change_set c JOIN app.itinerary it ON it.id = c.itinerary_id"
            " JOIN app.trip t ON t.id = it.trip_id WHERE c.id = :c AND EXISTS (SELECT 1 FROM app.trip_member tm WHERE tm.trip_id = t.id AND tm.person_id = :n)"
            + (" FOR UPDATE OF c" if lock else "")
        ),
        {"c": change_id, "n": person_id},
    ).first()
    if row is None:
        raise not_found("change set")
    return row


def require(conn: Connection, person_id: uuid.UUID, change_id: uuid.UUID) -> ChangeSet:
    return _change_set(_row(conn, person_id, change_id, lock=False))


def _close(conn: Connection, change_id: uuid.UUID, status: str) -> None:
    conn.execute(
        text(
            "UPDATE app.change_set SET status = :s, proposal = NULL, decided_at = now()"
            " WHERE id = :c"
        ),
        {"c": change_id, "s": status},
    )


def apply(conn: Connection, person_id: uuid.UUID, change_id: uuid.UUID) -> ChangeSetApplied | None:
    """Apply a pending change set. None when the itinerary changed since the preview: the change
    set is then marked expired (the caller commits that and answers 409)."""
    row = _row(conn, person_id, change_id, lock=True)
    trips.refuse_if_past(row.trip_status)
    if row.status != "pending":
        raise conflict("change_set_closed", f"this change set is {row.status}")
    version = conn.execute(
        text("SELECT version FROM app.itinerary WHERE id = :i FOR UPDATE"),
        {"i": row.itinerary_id},
    ).scalar_one()
    if version != row.base_version:
        _close(conn, change_id, "expired")
        return None
    proposal: State = row.proposal
    snapshot(conn, row.itinerary_id, change_id)
    write_state(conn, row.itinerary_id, proposal)
    if row.action == "edit_stops":
        _apply_stop_edit(conn, row.itinerary_id, proposal["trip_edit"])
    new_version = version + 1
    conn.execute(
        text(
            "UPDATE app.itinerary SET version = :v, summary = CAST(:s AS jsonb),"
            " engine_version = :ev, config_version = :cv, import_run_id = CAST(:run AS uuid)"
            " WHERE id = :i"
        ),
        {
            "i": row.itinerary_id,
            "v": new_version,
            "s": json.dumps(proposal["summary"], sort_keys=True),
            "ev": proposal["engine_version"],
            "cv": proposal["config_version"],
            "run": proposal["import_run_id"],
        },
    )
    conn.execute(
        text(
            "UPDATE app.change_set SET status = 'applied', proposal = NULL, decided_at = now(),"
            " result_version = :v WHERE id = :c"
        ),
        {"c": change_id, "v": new_version},
    )
    return ChangeSetApplied(
        change_set=require(conn, person_id, change_id),
        itinerary=itineraries.require_itinerary(conn, person_id, row.itinerary_id),
    )


def _apply_stop_edit(conn: Connection, itinerary_id: uuid.UUID, edit: dict[str, Any]) -> None:
    """The trip's side of an applied stop edit (ADR 024): its stops, name and length, and the
    stop version, which this plan now carries and the other plans no longer match."""
    from detour_api.repo.trips import ResolvedStop, write_stops

    trip_id = conn.execute(
        text("SELECT trip_id FROM app.itinerary WHERE id = :i"), {"i": itinerary_id}
    ).scalar_one()
    stops = [
        ResolvedStop(s["city_id"], s["name"], s["country_iso2"], s["lat"], s["lon"], s["days"])
        for s in edit["stops"]
    ]
    write_stops(conn, trip_id, stops)
    first = stops[0]
    version = conn.execute(
        text(
            "UPDATE app.trip SET title = :name, destination_name = :name, destination_ref = :ref,"
            " destination_point = ST_SetSRID(ST_MakePoint(:lon, :lat), 4326),"
            " duration_days = :days, stops_version = stops_version + 1, updated_at = now()"
            " WHERE id = :t RETURNING stops_version"
        ),
        {
            "name": edit["name"],
            "ref": str(first.city_id),
            "lat": first.lat,
            "lon": first.lon,
            "days": edit["duration_days"],
            "t": trip_id,
        },
    ).scalar_one()
    conn.execute(
        text("UPDATE app.itinerary SET stops_version = :v WHERE id = :i"),
        {"v": version, "i": itinerary_id},
    )


def discard(conn: Connection, person_id: uuid.UUID, change_id: uuid.UUID) -> ChangeSet:
    row = _row(conn, person_id, change_id, lock=True)
    if row.status != "pending":
        raise conflict("change_set_closed", f"this change set is {row.status}")
    _close(conn, change_id, "discarded")
    return require(conn, person_id, change_id)


def list_versions(
    conn: Connection, person_id: uuid.UUID, itinerary_id: uuid.UUID
) -> list[ItineraryVersion]:
    itineraries.require_itinerary(conn, person_id, itinerary_id)
    rows = conn.execute(
        text(
            "SELECT v.version, v.replaced_at, v.change_set_id, c.action, c.target_name,"
            " c.restores_version"
            " FROM app.itinerary_version v LEFT JOIN app.change_set c ON c.id = v.change_set_id"
            " WHERE v.itinerary_id = :i ORDER BY v.version DESC"
        ),
        {"i": itinerary_id},
    ).all()
    return [
        ItineraryVersion(
            version=r.version,
            replaced_at=r.replaced_at,
            change_set_id=r.change_set_id,
            action=r.action,
            target_name=r.target_name,
            restores_version=r.restores_version,
        )
        for r in rows
    ]


def itinerary_row(conn: Connection, person_id: uuid.UUID, itinerary_id: uuid.UUID) -> Any:
    """The itinerary's row with its trip's status and destination; not found or a past trip is
    refused. For the actions that read a plan of any profile (Optimize, ADR 029)."""
    return _itinerary_row(conn, person_id, itinerary_id)


def latest_optimize(
    conn: Connection, itinerary_id: uuid.UUID, version: int
) -> tuple[int, State] | None:
    """The version an applied Optimize replaced, if it is the latest change: the plan has not
    changed since, and that change set was an Optimize itself, not an undo (ADR 029)."""
    row = conn.execute(
        text(
            "SELECT base_version FROM app.change_set WHERE itinerary_id = :i AND status = 'applied'"
            " AND action = 'optimize' AND restores_version IS NULL AND result_version = :v"
        ),
        {"i": itinerary_id, "v": version},
    ).first()
    if row is None:
        return None
    state = stored_version(conn, itinerary_id, row.base_version)
    return None if state is None else (row.base_version, state)
