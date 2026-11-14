"""Database side of plan generation: what the engine reads, and writing its itineraries.

``load_context`` reads the trip, checks it can be planned, and loads what the engine plans with:
for a city, the attractions and places to eat of the destination's region around the trip's
destination point; for an area, the towns of the area (possible base cities) and the attractions
and places to eat inside it. ``save_generation`` writes the engine's itineraries with their days
(base city, inter-city leg), items (visits and meals) and transfers in one transaction. The engine
itself runs between the two, outside any transaction, because it may wait on the routing provider.
"""

import itertools
import json
import math
import uuid
from dataclasses import dataclass, field
from datetime import time
from typing import Any

from sqlalchemy import Connection, text

from detour_api.errors import ApiError, conflict, invalid
from detour_api.models.trips import GenerationResult, Trip
from detour_api.names.store import PLACE_NAME_COLUMNS, apply_overrides_to_trip, resolve_place_row
from detour_api.planner.config import PlannerConfig
from detour_api.planner.dedupe import collapse_duplicates
from detour_api.planner.reasons import ITEM_TEMPLATES
from detour_api.planner.types import (
    BaseCity,
    Candidate,
    Generation,
    Plan,
    PlanRequest,
    RouteStop,
)
from detour_api.repo import geo, itineraries, trips
from detour_api.repo.geo import METERS_PER_DEGREE
from detour_api.travel.estimate import ESTIMATE_VERSION


@dataclass(frozen=True)
class PlanningContext:
    trip_id: uuid.UUID
    region_id: str
    request: PlanRequest
    candidates: list[Candidate] = field(default_factory=list)
    # A multi-city trip's stop version, stored on its itineraries (ADR 024, decision 20).
    stops_version: int | None = None


# At most this many towns of an area are considered as base cities (the most populous first).
MAX_AREA_TOWNS = 60
# GeoNames feature codes that are not towns to stay in: sections of a populated place, and
# historical, abandoned or destroyed places.
NOT_A_BASE = ("PPLX", "PPLH", "PPLQ", "PPLW")


def load_context(
    conn: Connection, installation_id: uuid.UUID, trip_id: uuid.UUID, config: PlannerConfig
) -> PlanningContext:
    trip = trips.require_trip(conn, installation_id, trip_id)
    if trip.status == "past":
        raise conflict("trip_archived", "a past trip cannot get new itineraries")
    if trip.destination.kind == "route":
        return _route_context(conn, trip, config)
    kind = trip.destination.kind
    dest = geo.resolve_destination(conn, kind, trip.destination.ref)
    if dest is None:
        raise invalid(
            "destination_not_found", f"the trip's {kind} is no longer in the imported data"
        )
    if kind == "area" and not geo.area_planning_allowed(dest):
        raise invalid("area_single_city_only", geo.SINGLE_CITY_MESSAGE)
    if dest.region_id is None or dest.region_status != "available":
        raise ApiError(
            409,
            "region_not_available",
            "this destination is outside the regions that are available for planning",
        )
    import_run = conn.execute(
        text("SELECT current_import_run_id FROM geo.region WHERE id = :r"), {"r": dest.region_id}
    ).scalar_one_or_none()
    data_version = None if import_run is None else str(import_run)
    if kind == "city":
        request = PlanRequest(
            destination_name=trip.destination.name,
            lat=trip.destination.lat,
            lon=trip.destination.lon,
            days=trip.duration_days,
            start_date=trip.start_date,
            data_version=data_version,
            kind="city",
            base_cities=(
                BaseCity(
                    int(trip.destination.ref),
                    trip.destination.name,
                    trip.destination.lat,
                    trip.destination.lon,
                ),
            ),
        )
        radius = max(p.radius_m for p in config.profiles)
        return PlanningContext(
            trip_id=trip.id,
            region_id=dest.region_id,
            request=request,
            candidates=load_candidates(conn, dest.region_id, request.lat, request.lon, radius),
        )
    area_id = uuid.UUID(trip.destination.ref)
    request = PlanRequest(
        destination_name=trip.destination.name,
        lat=trip.destination.lat,
        lon=trip.destination.lon,
        days=trip.duration_days,
        start_date=trip.start_date,
        data_version=data_version,
        kind="area",
        base_cities=tuple(load_area_towns(conn, area_id)),
    )
    return PlanningContext(
        trip_id=trip.id,
        region_id=dest.region_id,
        request=request,
        candidates=load_area_candidates(conn, dest.region_id, area_id),
    )


def _route_context(conn: Connection, trip: Trip, config: PlannerConfig) -> PlanningContext:
    """A multi-city trip (ADR 024): every stop must still be a city in an available region; the
    candidates are those around each stop (each place once)."""
    if not trip.stops:
        raise invalid("route_needs_two_stops", "this multi-city trip has no stops")
    radius = max(p.radius_m for p in config.profiles)
    candidates: dict[str, Candidate] = {}
    runs: list[str] = []
    regions: list[str] = []
    stops: list[RouteStop] = []
    for stop in trip.stops:
        dest = geo.resolve_destination(conn, "city", str(stop.city_id))
        if dest is None:
            raise invalid(
                "destination_not_found", f"city {stop.position} is no longer in the imported data"
            )
        if dest.region_id is None or dest.region_status != "available":
            raise ApiError(
                409,
                "region_not_available",
                f"city {stop.position} ({stop.name}) is outside the regions that are available "
                "for planning",
            )
        if dest.region_id not in regions:
            regions.append(dest.region_id)
            run = conn.execute(
                text("SELECT current_import_run_id FROM geo.region WHERE id = :r"),
                {"r": dest.region_id},
            ).scalar_one_or_none()
            if run is not None:
                runs.append(str(run))
        for c in load_candidates(conn, dest.region_id, stop.lat, stop.lon, radius):
            candidates.setdefault(c.place_id, c)
        stops.append(
            RouteStop(
                BaseCity(stop.city_id, stop.name, stop.lat, stop.lon),
                stop.days,
                stop.country_iso2,
            )
        )
    first = trip.stops[0]
    request = PlanRequest(
        destination_name=trip.destination.name,
        lat=first.lat,
        lon=first.lon,
        days=trip.duration_days,
        start_date=trip.start_date,
        # One import run per region; a route across regions records them all.
        data_version=",".join(runs) if runs else None,
        kind="route",
        stops=tuple(stops),
    )
    return PlanningContext(
        trip_id=trip.id,
        region_id=regions[0],
        request=request,
        candidates=collapse_duplicates(candidates[k] for k in sorted(candidates)),
        stops_version=trip.stops_version,
    )


def _box(lat: float, lon: float, radius_m: int) -> dict[str, float]:
    dlat = radius_m / METERS_PER_DEGREE
    dlon = radius_m / (METERS_PER_DEGREE * max(math.cos(math.radians(lat)), 0.01))
    return {"x1": lon - dlon, "y1": lat - dlat, "x2": lon + dlon, "y2": lat + dlat}


_CANDIDATE_SQL = """
    SELECT p.id, p.kind, p.name, p.names_i18n,
           -- The inputs of the name resolver (ADR 025): the English-facing name is chosen in
           -- Python from the place's own names and any stored Wikidata names; never translated.
           {names},
           p.category, ST_Y(p.geom) AS lat, ST_X(p.geom) AS lon,
           s.osm_signals, s.sitelink_count
    FROM geo.place p LEFT JOIN geo.place_signal s ON s.place_id = p.id
    WHERE p.is_active AND p.kind = 'attraction' AND p.name IS NOT NULL
      AND p.region_id = :r AND {where}
    ORDER BY p.id
"""

# Name inputs without an installation (``:inst`` null): plans take the resolved name; a user's own
# approved names are applied to the plan's snapshots when it is stored (names.store).
_NAMES = PLACE_NAME_COLUMNS.replace("CAST(:inst AS uuid)", "NULL::uuid")
_IN_BOX = "p.geom && ST_MakeEnvelope(:x1, :y1, :x2, :y2, 4326)"
_IN_AREA = "ST_Intersects(p.geom, (SELECT a.geom FROM geo.admin_area a WHERE a.id = :area))"


def _display(row: Any) -> str:
    return resolve_place_row(row).display or str(row.name)


def _candidates(rows: Any) -> list[Candidate]:
    return collapse_duplicates(
        Candidate(
            place_id=str(r.id),
            name=_display(r),
            category=r.category,
            lat=r.lat,
            lon=r.lon,
            signals=dict(r.osm_signals or {}),
            sitelink_count=r.sitelink_count,
        )
        for r in rows
    )


def load_area_candidates(conn: Connection, region_id: str, area_id: uuid.UUID) -> list[Candidate]:
    rows = conn.execute(
        text(_CANDIDATE_SQL.format(names=_NAMES, where=_IN_AREA)), {"r": region_id, "area": area_id}
    ).all()
    return _candidates(rows)


def load_area_towns(conn: Connection, area_id: uuid.UUID) -> list[BaseCity]:
    """Gazetteer towns inside the area: the possible base cities, most populous first."""
    rows = conn.execute(
        text(
            """
            SELECT c.id, c.name, ST_Y(c.geom) AS lat, ST_X(c.geom) AS lon, c.population
            FROM geo.city c
            WHERE ST_Intersects(c.geom, (SELECT a.geom FROM geo.admin_area a WHERE a.id = :area))
              AND NOT (COALESCE(c.feature_code, '') = ANY (:sections))
            ORDER BY c.population DESC NULLS LAST, c.id
            LIMIT :n
            """
        ),
        {"area": area_id, "n": MAX_AREA_TOWNS, "sections": list(NOT_A_BASE)},
    ).all()
    return [BaseCity(int(r.id), r.name, r.lat, r.lon, r.population) for r in rows]


def load_candidates(
    conn: Connection, region_id: str, lat: float, lon: float, radius_m: int
) -> list[Candidate]:
    """Active, named attractions of the region in a box around the point (the engine applies the
    exact radius). Uses the GiST index on ``geo.place.geom``."""
    rows = conn.execute(
        text(_CANDIDATE_SQL.format(names=_NAMES, where=_IN_BOX)),
        {"r": region_id, **_box(lat, lon, radius_m)},
    ).all()
    return _candidates(rows)


def _time(minute: int) -> time:
    return time(minute // 60, minute % 60)


def _summary(plan: Plan, generation: Generation, request: PlanRequest, sequencer: str) -> str:
    stats = plan.stats
    return json.dumps(
        {
            # Every import run the plan read (a multi-city trip may span regions).
            "data_version": generation.data_version,
            "stats": {
                "visits": stats.visits,
                "days_with_visits": stats.days_with_visits,
                "visit_minutes": stats.visit_minutes,
                "travel_minutes": stats.travel_minutes,
                "travel_seconds": stats.travel_seconds,
                "routed_transfers": stats.routed_transfers,
                "estimated_transfers": stats.estimated_transfers,
                "day_utilisation_permille": stats.day_utilisation_permille,
                "travel_share_permille": stats.travel_share_permille,
                "meals": stats.meals,
                "meal_minutes": stats.meal_minutes,
                "intercity_legs": stats.intercity_legs,
            },
            "notes": [{"code": n.code, "params": n.params} for n in plan.notes + generation.notes],
            "sequencer": sequencer,
            "estimate_version": ESTIMATE_VERSION,
            "jaccard_permille": generation.jaccard_permille,
        },
        sort_keys=True,
    )


def save_generation(
    conn: Connection,
    installation_id: uuid.UUID,
    context: PlanningContext,
    generation: Generation,
    sequencer: str,
    max_jaccard_permille: int,
) -> GenerationResult:
    trip_row = conn.execute(
        text(
            "SELECT status, selected_itinerary_id FROM app.trip"
            " WHERE id = :t AND installation_id = :i FOR UPDATE"
        ),
        {"t": context.trip_id, "i": installation_id},
    ).first()
    if trip_row is None:
        raise ApiError(404, "not_found", "trip not found")
    if trip_row.status == "past":
        raise conflict("trip_archived", "a past trip cannot get new itineraries")
    # A new generation replaces the earlier engine proposals the user did not select.
    conn.execute(
        text(
            "DELETE FROM app.itinerary WHERE trip_id = :t AND status = 'proposed'"
            " AND profile IN ('essentials', 'wider')"
            " AND id IS DISTINCT FROM CAST(:sel AS uuid)"
        ),
        {"t": context.trip_id, "sel": trip_row.selected_itinerary_id},
    )
    remaining = conn.execute(
        text("SELECT count(*) FROM app.itinerary WHERE trip_id = :t"), {"t": context.trip_id}
    ).scalar_one()
    if remaining + len(generation.plans) > itineraries.MAX_ITINERARIES_PER_TRIP:
        raise conflict(
            "limit_reached",
            f"at most {itineraries.MAX_ITINERARIES_PER_TRIP} itineraries per trip; "
            "delete one to generate new proposals",
        )

    generation_id = uuid.uuid4()
    diversity = None if generation.jaccard_permille is None else generation.jaccard_permille / 1000
    ids: list[uuid.UUID] = []
    for plan in generation.plans:
        itinerary_id = uuid.uuid4()
        ids.append(itinerary_id)
        conn.execute(
            text(
                """
                INSERT INTO app.itinerary (id, trip_id, generation_id, profile, engine_version,
                    config_version, import_run_id, seed, diversity_score, summary, stops_version)
                VALUES (:id, :t, :g, :p, :ev, :cv, CAST(:run AS uuid), :seed, :div,
                    CAST(:summary AS jsonb), :sv)
                """
            ),
            {
                "id": itinerary_id,
                "t": context.trip_id,
                "g": generation_id,
                "p": plan.profile,
                "ev": generation.engine_version,
                "cv": generation.config_version,
                # import_run_id is one run; a route over several regions keeps the first (all of
                # them are in the summary's data_version).
                "run": (generation.data_version or "").split(",")[0] or None,
                "sv": context.stops_version,
                "seed": generation.seed,
                "div": diversity,
                "summary": _summary(plan, generation, context.request, sequencer),
            },
        )
        _write_days(conn, itinerary_id, plan)
    # The user's approved display names (ADR 025) replace the resolved ones in the snapshots.
    apply_overrides_to_trip(conn, installation_id, context.trip_id)
    return GenerationResult(
        generation_id=generation_id,
        distinct=generation.distinct,
        jaccard_permille=generation.jaccard_permille,
        max_jaccard_permille=max_jaccard_permille,
        notes=[itineraries.render_note(n.code, n.params) for n in generation.notes],
        itineraries=[itineraries.require_itinerary(conn, installation_id, i) for i in ids],
    )


def _write_days(conn: Connection, itinerary_id: uuid.UUID, plan: Plan) -> None:
    for day in plan.days:
        day_id = uuid.uuid4()
        arrival = day.arrival
        conn.execute(
            text(
                "INSERT INTO app.itinerary_day (id, itinerary_id, day_index, date, base_city_id,"
                " base_city_name, arrival_mode, arrival_seconds, arrival_meters,"
                " arrival_confidence) VALUES (:d, :i, :n, :date, :city, :cname, :am, :asec, :amet,"
                " :aconf)"
            ),
            {
                "d": day_id,
                "i": itinerary_id,
                "n": day.day_index,
                "date": day.date,
                "city": day.base_city_id,
                "cname": day.base_city_name,
                # A leg whose time is not known (ADR 024) is stored as such, with no figures.
                "am": "unknown"
                if day.arrival_unknown
                else None
                if arrival is None
                else arrival.mode,
                "asec": None if arrival is None else arrival.seconds,
                "amet": None if arrival is None else arrival.meters,
                "aconf": "unknown"
                if day.arrival_unknown
                else None
                if arrival is None
                else arrival.confidence,
            },
        )
        item_ids = [uuid.uuid4() for _ in day.items]
        for position, (item_id, item) in enumerate(zip(item_ids, day.items, strict=True), 1):
            assert all(code in ITEM_TEMPLATES for code in item.reasons)  # noqa: S101
            conn.execute(
                text(
                    """
                    INSERT INTO app.itinerary_item (id, day_id, position, type, meal_type,
                        place_id, display_name, display_point, start_time, end_time,
                        duration_minutes, duration_source, origin, locked, reasons)
                    VALUES (:id, :d, :pos, :type, :meal, :place, :name,
                        ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), :start, :end, :minutes,
                        'category_default', 'engine', false, :reasons)
                    """
                ),
                {
                    "id": item_id,
                    "d": day_id,
                    "pos": position,
                    "type": item.kind,
                    "meal": item.meal_type,
                    "place": uuid.UUID(item.place_id),
                    "name": item.name,
                    "lat": item.lat,
                    "lon": item.lon,
                    "start": _time(item.start_minute),
                    "end": _time(item.end_minute),
                    "minutes": item.duration_minutes,
                    "reasons": list(item.reasons),
                },
            )
        for (from_id, to_id), item in zip(itertools.pairwise(item_ids), day.items, strict=False):
            leg = item.transfer
            assert leg is not None  # noqa: S101 - the validator guarantees it
            conn.execute(
                text(
                    "INSERT INTO app.transfer (id, from_item_id, to_item_id, mode, seconds,"
                    " meters, confidence) VALUES (:id, :f, :t, :m, :s, :me, :c)"
                ),
                {
                    "id": uuid.uuid4(),
                    "f": from_id,
                    "t": to_id,
                    "m": leg.mode,
                    "s": leg.seconds,
                    "me": leg.meters,
                    "c": leg.confidence,
                },
            )
