"""Database side of plan generation: what the engine reads, and writing its itineraries.

``load_context`` reads the trip, checks it can be planned, and loads the candidate attractions of
the destination's region around the trip's destination point. ``save_generation`` writes the
engine's itineraries with their days, items and transfers in one transaction. The engine itself
runs between the two, outside any transaction, because it may wait on the routing provider.
"""

import itertools
import json
import math
import uuid
from dataclasses import dataclass, field
from datetime import time

from sqlalchemy import Connection, text

from detour_api.errors import ApiError, conflict, invalid
from detour_api.models.trips import GenerationResult
from detour_api.planner.config import PlannerConfig
from detour_api.planner.reasons import ITEM_TEMPLATES
from detour_api.planner.types import Candidate, Generation, Plan, PlanRequest
from detour_api.repo import geo, itineraries, trips
from detour_api.repo.geo import METERS_PER_DEGREE
from detour_api.travel.estimate import ESTIMATE_VERSION


@dataclass(frozen=True)
class PlanningContext:
    trip_id: uuid.UUID
    city_id: int
    region_id: str
    request: PlanRequest
    candidates: list[Candidate] = field(default_factory=list)


def load_context(
    conn: Connection, installation_id: uuid.UUID, trip_id: uuid.UUID, config: PlannerConfig
) -> PlanningContext:
    trip = trips.require_trip(conn, installation_id, trip_id)
    if trip.status == "past":
        raise conflict("trip_archived", "a past trip cannot get new itineraries")
    if trip.destination.kind != "city":
        raise invalid(
            "area_not_supported",
            "itineraries for an area destination are not available yet; choose a city",
        )
    dest = geo.resolve_destination(conn, "city", trip.destination.ref)
    if dest is None:
        raise invalid("destination_not_found", "the trip's city is no longer in the imported data")
    if dest.region_id is None or dest.region_status != "available":
        raise ApiError(
            409,
            "region_not_available",
            "this destination is outside the regions that are available for planning",
        )
    import_run = conn.execute(
        text("SELECT current_import_run_id FROM geo.region WHERE id = :r"), {"r": dest.region_id}
    ).scalar_one_or_none()
    request = PlanRequest(
        destination_name=trip.destination.name,
        lat=trip.destination.lat,
        lon=trip.destination.lon,
        days=trip.duration_days,
        start_date=trip.start_date,
        currency_code=trip.currency_code,
        data_version=None if import_run is None else str(import_run),
    )
    radius = max(p.radius_m for p in config.profiles)
    return PlanningContext(
        trip_id=trip.id,
        city_id=int(trip.destination.ref),
        region_id=dest.region_id,
        request=request,
        candidates=load_candidates(conn, dest.region_id, request.lat, request.lon, radius),
    )


def load_candidates(
    conn: Connection, region_id: str, lat: float, lon: float, radius_m: int
) -> list[Candidate]:
    """Active, named attractions of the region in a box around the point (the engine applies the
    exact radius). Uses the GiST index on ``geo.place.geom``."""
    dlat = radius_m / METERS_PER_DEGREE
    dlon = radius_m / (METERS_PER_DEGREE * max(math.cos(math.radians(lat)), 0.01))
    rows = conn.execute(
        text(
            """
            SELECT p.id, p.name, p.category, ST_Y(p.geom) AS lat, ST_X(p.geom) AS lon,
                   s.osm_signals, s.sitelink_count
            FROM geo.place p LEFT JOIN geo.place_signal s ON s.place_id = p.id
            WHERE p.is_active AND p.kind = 'attraction' AND p.name IS NOT NULL
              AND p.region_id = :r
              AND p.geom && ST_MakeEnvelope(:x1, :y1, :x2, :y2, 4326)
            ORDER BY p.id
            """
        ),
        {"r": region_id, "x1": lon - dlon, "y1": lat - dlat, "x2": lon + dlon, "y2": lat + dlat},
    ).all()
    return [
        Candidate(
            place_id=str(r.id),
            name=r.name,
            category=r.category,
            lat=r.lat,
            lon=r.lon,
            signals=dict(r.osm_signals or {}),
            sitelink_count=r.sitelink_count,
        )
        for r in rows
    ]


def _time(minute: int) -> time:
    return time(minute // 60, minute % 60)


def _summary(plan: Plan, generation: Generation, request: PlanRequest, sequencer: str) -> str:
    stats = plan.stats
    return json.dumps(
        {
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
            },
            "notes": [{"code": n.code, "params": n.params} for n in plan.notes + generation.notes],
            "sequencer": sequencer,
            "estimate_version": ESTIMATE_VERSION,
            "currency_code": request.currency_code,
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
                    config_version, import_run_id, seed, diversity_score, summary)
                VALUES (:id, :t, :g, :p, :ev, :cv, CAST(:run AS uuid), :seed, :div,
                    CAST(:summary AS jsonb))
                """
            ),
            {
                "id": itinerary_id,
                "t": context.trip_id,
                "g": generation_id,
                "p": plan.profile,
                "ev": generation.engine_version,
                "cv": generation.config_version,
                "run": generation.data_version,
                "seed": generation.seed,
                "div": diversity,
                "summary": _summary(plan, generation, context.request, sequencer),
            },
        )
        _write_days(conn, itinerary_id, plan, context.city_id)
    return GenerationResult(
        generation_id=generation_id,
        distinct=generation.distinct,
        jaccard_permille=generation.jaccard_permille,
        max_jaccard_permille=max_jaccard_permille,
        notes=[itineraries.render_note(n.code, n.params) for n in generation.notes],
        itineraries=[itineraries.require_itinerary(conn, installation_id, i) for i in ids],
    )


def _write_days(conn: Connection, itinerary_id: uuid.UUID, plan: Plan, city_id: int) -> None:
    for day in plan.days:
        day_id = uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO app.itinerary_day (id, itinerary_id, day_index, date, base_city_id)"
                " VALUES (:d, :i, :n, :date, :city)"
            ),
            {"d": day_id, "i": itinerary_id, "n": day.day_index, "date": day.date, "city": city_id},
        )
        item_ids = [uuid.uuid4() for _ in day.visits]
        for position, (item_id, visit) in enumerate(zip(item_ids, day.visits, strict=True), 1):
            assert all(code in ITEM_TEMPLATES for code in visit.reasons)  # noqa: S101
            conn.execute(
                text(
                    """
                    INSERT INTO app.itinerary_item (id, day_id, position, type, place_id,
                        display_name, display_point, start_time, end_time, duration_minutes,
                        duration_source, origin, locked, reasons)
                    VALUES (:id, :d, :pos, 'visit', :place, :name,
                        ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), :start, :end, :minutes,
                        'category_default', 'engine', false, :reasons)
                    """
                ),
                {
                    "id": item_id,
                    "d": day_id,
                    "pos": position,
                    "place": uuid.UUID(visit.place_id),
                    "name": visit.name,
                    "lat": visit.lat,
                    "lon": visit.lon,
                    "start": _time(visit.start_minute),
                    "end": _time(visit.end_minute),
                    "minutes": visit.duration_minutes,
                    "reasons": list(visit.reasons),
                },
            )
        for (from_id, to_id), visit in zip(itertools.pairwise(item_ids), day.visits, strict=False):
            leg = visit.transfer
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
