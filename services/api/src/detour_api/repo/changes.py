"""Change sets and itinerary versions (Phase 7, ADR 018): the database side of recalculation.

``load_context`` reads what a preview needs (the itinerary's current state, the place to add or
the item to remove, the sights and places to eat around the plan's bases and the addition, the
towns near the addition). ``save`` stores a previewed change set; ``apply`` keeps the current
version in ``app.itinerary_version`` and writes the proposal exactly as previewed; ``discard``
closes it. The recalculation itself runs between ``load_context`` and ``save``, outside any
transaction, because it may wait on the routing provider.
"""

import json
import math
import uuid
from collections.abc import Iterable
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
)
from detour_api.models.restaurants import (
    MovedItem,
    SlotReason,
    SlotRestaurant,
    SlotSuggestion,
    SlotSuggestions,
)
from detour_api.planner import restaurant_slots
from detour_api.planner.config import PlannerConfig
from detour_api.planner.diff import PlanDiff
from detour_api.planner.durations import visit_minutes
from detour_api.planner.reasons import issue_text, slot_text
from detour_api.planner.recalc import Addition, RecalcConfig, RecalcInput, entry_key
from detour_api.planner.restaurant_slots import Dining, SlotResult
from detour_api.planner.types import BaseCity, Candidate, Issue, Note, Restaurant
from detour_api.repo import geo, itineraries, planning, user_places
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
        "RESTAURANT_ADDED",
        "MEAL_REPLACED",
        "STOP_REMOVED_ITEMS",
        "STOPS_CHANGED",
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
    # add_restaurant (Phase 8): the restaurant and the slot it was previewed for
    dining: Dining | None = None
    slot_day: int | None = None
    slot_meal: str | None = None
    after_item_id: uuid.UUID | None = None


def impossible(issues: list[Issue]) -> ApiError:
    from detour_api.planner.reasons import issue_text

    params = [{"code": i.code, "text": issue_text(i.code, i.params)} for i in issues]
    return ApiError(
        422,
        "recalculation_impossible",
        " ".join(p["text"] for p in params),
        extra={"issues": params},
    )


def _itinerary_row(conn: Connection, installation_id: uuid.UUID, itinerary_id: uuid.UUID) -> Any:
    row = conn.execute(
        text(
            "SELECT it.id, it.profile, it.version, t.status AS trip_status, t.destination_kind,"
            " t.destination_ref FROM app.itinerary it JOIN app.trip t ON t.id = it.trip_id"
            " WHERE it.id = :i AND t.installation_id = :n"
        ),
        {"i": itinerary_id, "n": installation_id},
    ).first()
    if row is None:
        raise not_found("itinerary")
    if row.trip_status == "past":
        raise conflict("trip_archived", "a past trip cannot be changed")
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


def _restaurant_info(
    conn: Connection, ids: list[str]
) -> dict[str, tuple[str | None, tuple[str, ...] | None]]:
    if not ids:
        return {}
    rows = conn.execute(
        text(
            "SELECT place_id, venue_type, cuisines FROM geo.restaurant_profile"
            " WHERE place_id = ANY(CAST(:ids AS uuid[]))"
        ),
        {"ids": ids},
    ).all()
    return {
        str(r.place_id): (r.venue_type, None if r.cuisines is None else tuple(r.cuisines))
        for r in rows
    }


def _head(
    conn: Connection, installation_id: uuid.UUID, itinerary_id: uuid.UUID
) -> tuple[Any, geo.ResolvedDestination, State, dict[str, Any]]:
    row = _itinerary_row(conn, installation_id, itinerary_id)
    if row.profile not in ("essentials", "wider"):
        raise conflict(
            "not_recalculable", "only planned itineraries are recalculated; edit this one by hand"
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
    installation_id: uuid.UUID,
    itinerary_id: uuid.UUID,
    body: ChangeSetCreate,
    config: PlannerConfig,
    rconfig: RecalcConfig,
) -> Context:
    row, dest, state, common = _head(conn, installation_id, itinerary_id)

    addition: Addition | None = None
    dining: Dining | None = None
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
    elif body.action == "add_restaurant":
        dining = load_dining(conn, installation_id, body.place_id, body.user_place_id)
        assert body.day is not None  # noqa: S101 - guaranteed by ChangeSetCreate
        if not 1 <= body.day <= len(state["days"]):
            raise invalid("day_not_found", f"the plan has {len(state['days'])} days")
        point = (dining.lat, dining.lon)
        target_name = dining.name
    else:
        addition = _addition(conn, installation_id, body)
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
        dining=dining,
        slot_day=body.day,
        slot_meal=body.meal_type,
        after_item_id=body.after_item_id,
    )


def load_restaurant_context(
    conn: Connection,
    installation_id: uuid.UUID,
    itinerary_id: uuid.UUID,
    place_id: uuid.UUID | None,
    user_place_id: uuid.UUID | None,
    config: PlannerConfig,
    rconfig: RecalcConfig,
) -> Context:
    """What suggesting slots for a restaurant needs (nothing is stored)."""
    row, dest, state, common = _head(conn, installation_id, itinerary_id)
    dining = load_dining(conn, installation_id, place_id, user_place_id)
    recalc_input = _plan_input(
        conn, row, dest, state, (dining.lat, dining.lon), None, config, rconfig
    )
    return Context(
        **common,
        action="add_restaurant",
        target_name=dining.name,
        recalc=recalc_input,
        place_id=place_id,
        user_place_id=user_place_id,
        dining=dining,
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
    meal_places = [r["place_id"] for r in state["items"] if r["type"] == "meal" and r["place_id"]]
    own_meals = [
        r["user_place_id"] for r in state["items"] if r["type"] == "meal" and r["user_place_id"]
    ]
    rplan = _to_rplan(
        state,
        row.profile,
        _restaurant_info(conn, meal_places),
        user_cuisines=_user_cuisines(conn, own_meals),
    )
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
    rests: dict[str, Restaurant] = {}
    for region in regions:
        for lat, lon in points:
            for c in planning.load_candidates(conn, region, lat, lon, radius):
                cands.setdefault(c.place_id, c)
            for r in planning.load_restaurants(
                conn, region, lat, lon, radius + config.meal_search_m[-1]
            ):
                rests.setdefault(r.place_id, r)
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
        restaurants=tuple(rests[k] for k in sorted(rests)),
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


def _user_cuisines(conn: Connection, ids: list[str]) -> dict[str, tuple[str, ...] | None]:
    if not ids:
        return {}
    rows = conn.execute(
        text("SELECT id, cuisines FROM app.user_place WHERE id = ANY(CAST(:ids AS uuid[]))"),
        {"ids": ids},
    ).all()
    return {str(r.id): None if not r.cuisines else tuple(r.cuisines) for r in rows}


def load_dining(
    conn: Connection,
    installation_id: uuid.UUID,
    place_id: uuid.UUID | None,
    user_place_id: uuid.UUID | None,
) -> Dining:
    """The restaurant to add: an imported place to eat (venue type, cuisines and meal types as the
    import stored them) or one of the user's own (what the user gave; unknown stays unknown)."""
    if place_id is not None:
        row = conn.execute(
            text(
                "SELECT p.kind, p.name, p.is_active, ST_Y(p.geom) AS lat, ST_X(p.geom) AS lon,"
                " rp.venue_type, rp.cuisines, rp.meal_types FROM geo.place p"
                " LEFT JOIN geo.restaurant_profile rp ON rp.place_id = p.id WHERE p.id = :i"
            ),
            {"i": place_id},
        ).first()
        if row is None or not row.is_active:
            raise invalid("place_not_found", "place_id is not an active place")
        if row.kind != "restaurant" or row.venue_type is None:
            raise invalid("wrong_place_kind", "only places to eat can be added as a restaurant")
        if row.name is None:
            raise invalid("unnamed_place", "this place has no name in the data; add it by hand")
        return Dining(
            name=row.name,
            lat=row.lat,
            lon=row.lon,
            venue_type=row.venue_type,
            cuisines=None if not row.cuisines else tuple(row.cuisines),
            meal_types=None if not row.meal_types else tuple(row.meal_types),
            place_id=str(place_id),
        )
    assert user_place_id is not None  # noqa: S101 - one of the two is always given
    place = user_places.get(conn, installation_id, user_place_id)
    if place is None:
        raise invalid("user_place_not_found", "user_place_id is not one of your places")
    if place.kind != "restaurant":
        raise invalid("wrong_place_kind", "only a place of kind restaurant can be added as a meal")
    return Dining(
        name=place.name,
        lat=place.lat,
        lon=place.lon,
        cuisines=None if not place.cuisines else tuple(place.cuisines),
        meal_types=None if not place.meal_types else tuple(place.meal_types),
        user_place_id=str(user_place_id),
    )


def _addition(conn: Connection, installation_id: uuid.UUID, body: ChangeSetCreate) -> Addition:
    if body.place_id is not None:
        found = geo.place_exists(conn, body.place_id)
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
    place = user_places.get(conn, installation_id, body.user_place_id)
    if place is None:
        raise invalid("user_place_not_found", "user_place_id is not one of your places")
    if place.kind == "restaurant":
        raise invalid(
            "wrong_place_kind", "a restaurant is added to a meal slot: use add_restaurant"
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
                meal_type=i.meal_type,
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
                meal_type=i.meal_type,
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
                meal_type=r.meal_type,
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


def slot_suggestions(dining: Dining, result: SlotResult) -> SlotSuggestions:
    """The suggestions as the API shows them: reasons rendered through the fixed templates."""

    def reasons(items: Iterable[restaurant_slots.Reason]) -> list[SlotReason]:
        return [SlotReason(code=r.code, text=slot_text(r.code, r.params)) for r in items]

    return SlotSuggestions(
        restaurant=SlotRestaurant(
            name=dining.name,
            venue_type=dining.venue_type,
            cuisines=None if dining.cuisines is None else list(dining.cuisines),
            meal_types=None if dining.meal_types is None else list(dining.meal_types),
            meal_types_basis="venue_type" if dining.basis == "venue" else dining.basis,
        ),
        suggestions=[
            SlotSuggestion(
                rank=n,
                day=s.day_index,
                meal_type=s.meal_type,
                start_time=_t(s.start_minute),
                end_time=_t(s.end_minute),
                after_item_id=None if s.after_item_id is None else uuid.UUID(s.after_item_id),
                after_name=s.after_name,
                before_name=s.before_name,
                travel_minutes_added=s.travel_minutes_added,
                travel_label="estimated" if s.estimated else "routed",
                detour_metres=s.detour_m,
                replaces=s.replaces,
                items_moved=[
                    MovedItem(
                        kind=m.kind,
                        name=m.name,
                        old_start_time=_t(m.old_start_minute),
                        new_start_time=_t(m.new_start_minute),
                    )
                    for m in s.shifts
                ],
                reasons=reasons(s.reasons),
                score=s.cost,
            )
            for n, s in enumerate(result.suggestions, start=1)
        ],
        slots_considered=result.slots_considered,
        issues=[SlotReason(code=i.code, text=issue_text(i.code, i.params)) for i in result.issues],
    )


# -- change sets ---------------------------------------------------------------------------------

_CHANGE_COLUMNS = (
    "id, itinerary_id, action, target_name, status, base_version, restores_version,"
    " result_version, diff, notes, created_at, decided_at"
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
        notes=[itineraries.render_note(n["code"], n.get("params", {})) for n in row.notes],
        created_at=row.created_at,
        decided_at=row.decided_at,
    )


def save(
    conn: Connection,
    installation_id: uuid.UUID,
    ctx: Context,
    proposal: State,
    diff: ChangeDiff,
    notes: list[Note],
) -> ChangeSet:
    _itinerary_row(conn, installation_id, ctx.itinerary_id)
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
                slot_day, slot_meal, after_item_id, proposal, diff, notes)
            VALUES (:id, :i, :v, :a, :p, :u, :item, :minutes, :name, :restores,
                :slot_day, :slot_meal, :after,
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
            "slot_day": ctx.slot_day,
            "slot_meal": ctx.slot_meal,
            "after": ctx.after_item_id,
            "proposal": json.dumps(proposal, sort_keys=True),
            "diff": diff.model_dump_json(),
            "notes": json.dumps([{"code": n.code, "params": n.params} for n in notes]),
        },
    )
    return require(conn, installation_id, change_id)


def _row(conn: Connection, installation_id: uuid.UUID, change_id: uuid.UUID, lock: bool) -> Any:
    row = conn.execute(
        text(
            f"SELECT c.{_CHANGE_COLUMNS.replace(', ', ', c.')}, c.proposal, t.status AS trip_status"
            " FROM app.change_set c JOIN app.itinerary it ON it.id = c.itinerary_id"
            " JOIN app.trip t ON t.id = it.trip_id WHERE c.id = :c AND t.installation_id = :n"
            + (" FOR UPDATE OF c" if lock else "")
        ),
        {"c": change_id, "n": installation_id},
    ).first()
    if row is None:
        raise not_found("change set")
    return row


def require(conn: Connection, installation_id: uuid.UUID, change_id: uuid.UUID) -> ChangeSet:
    return _change_set(_row(conn, installation_id, change_id, lock=False))


def _close(conn: Connection, change_id: uuid.UUID, status: str) -> None:
    conn.execute(
        text(
            "UPDATE app.change_set SET status = :s, proposal = NULL, decided_at = now()"
            " WHERE id = :c"
        ),
        {"c": change_id, "s": status},
    )


def apply(
    conn: Connection, installation_id: uuid.UUID, change_id: uuid.UUID
) -> ChangeSetApplied | None:
    """Apply a pending change set. None when the itinerary changed since the preview: the change
    set is then marked expired (the caller commits that and answers 409)."""
    row = _row(conn, installation_id, change_id, lock=True)
    if row.trip_status == "past":
        raise conflict("trip_archived", "a past trip cannot be changed")
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
        change_set=require(conn, installation_id, change_id),
        itinerary=itineraries.require_itinerary(conn, installation_id, row.itinerary_id),
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


def discard(conn: Connection, installation_id: uuid.UUID, change_id: uuid.UUID) -> ChangeSet:
    row = _row(conn, installation_id, change_id, lock=True)
    if row.status != "pending":
        raise conflict("change_set_closed", f"this change set is {row.status}")
    _close(conn, change_id, "discarded")
    return require(conn, installation_id, change_id)


def list_versions(
    conn: Connection, installation_id: uuid.UUID, itinerary_id: uuid.UUID
) -> list[ItineraryVersion]:
    itineraries.require_itinerary(conn, installation_id, itinerary_id)
    rows = conn.execute(
        text(
            "SELECT v.version, v.replaced_at, v.change_set_id, c.action, c.target_name"
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
        )
        for r in rows
    ]
