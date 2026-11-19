"""Removing a region's imported data (ADR 033).

Removing a region frees database space (the Supabase Free plan has 500 MB) without touching what
trips show. Everything a trip, a past-trip record or a display-name override still names is kept:
the place stays in ``geo.place`` with ``is_active = false`` (so it is no longer found by search or
offered to the planner), with its source rows, its names and its photo link. Everything else of the
region goes: places with their source and signal rows (cascade), administrative areas, the stored
names and lookups of places that are gone, and the photo lookups of those places.

The region row stays, ``disabled`` and without a current data version, so a later import fills it
again; places have deterministic identifiers, so the kept ones become active again by themselves.
The GeoNames cities of the region's countries go too (they were most of the imported data in
production: 28 of 43 MB), except where another region with data still covers the country, and except
every city that a trip, a stop, a day's base, a past-trip record, a display-name override or a kept
place still names. A later import loads the cities again (the workflow's gazetteer step, on by
default) under the same GeoNames identifiers. Countries, currencies and the travel-time cache stay.
"""

import uuid
from typing import Any

import structlog
from sqlalchemy import Connection, Engine, text

from detour_api.errors import conflict, not_found
from detour_api.models.search import RegionRemoval, RemovalTrip
from detour_api.names import store as names_store

log = structlog.get_logger("detour.regions")

# Same threshold as the importer: a clean-up this large is followed by a table rewrite so the
# files, and the size Supabase counts, shrink.
FULL_VACUUM_THRESHOLD = 1000

# A place the app still names (an item, a past-trip record, a display-name override). Soft
# references: there is no foreign key between the schemas.
_PLACE_KEPT = (
    "EXISTS (SELECT 1 FROM app.itinerary_item i WHERE i.place_id = p.id)"
    " OR EXISTS (SELECT 1 FROM app.trip_visit v WHERE v.geo_place_ref = p.id::text)"
    " OR EXISTS (SELECT 1 FROM app.place_name_override o WHERE o.entity_kind = 'place'"
    "   AND o.entity_ref = p.id::text)"
)
_AREA_KEPT = (
    "EXISTS (SELECT 1 FROM app.trip t WHERE t.destination_kind = 'area'"
    " AND t.destination_ref = a.id::text)"
    " OR EXISTS (SELECT 1 FROM app.place_name_override o WHERE o.entity_kind = 'area'"
    "   AND o.entity_ref = a.id::text)"
)

# A city the app still names (ids are GeoNames ids, stored as text or bigint; no foreign key).
_CITY_KEPT = (
    "EXISTS (SELECT 1 FROM app.trip t WHERE t.destination_kind = 'city'"
    " AND t.destination_ref = c.id::text)"
    " OR EXISTS (SELECT 1 FROM app.trip_stop s WHERE s.city_id = c.id)"
    " OR EXISTS (SELECT 1 FROM app.itinerary_day d WHERE d.base_city_id = c.id)"
    " OR EXISTS (SELECT 1 FROM app.trip_visit v WHERE v.kind = 'city'"
    "   AND v.geo_place_ref = c.id::text)"
    " OR EXISTS (SELECT 1 FROM app.place_name_override o WHERE o.entity_kind = 'city'"
    "   AND o.entity_ref = c.id::text)"
    # Only a place that stays protects its city (the others are deleted first).
    f" OR EXISTS (SELECT 1 FROM geo.place p WHERE p.city_id = c.id AND ({_PLACE_KEPT}))"
)

# The region's countries that no other region with data covers: only their cities may go.
_FREE_COUNTRIES = (
    "SELECT cc FROM unnest(CAST(:c AS text[])) AS cc WHERE NOT EXISTS ("
    " SELECT 1 FROM geo.region o WHERE o.id <> :r AND cc = ANY (o.country_codes)"
    " AND EXISTS (SELECT 1 FROM geo.place p WHERE p.region_id = o.id AND p.is_active))"
)


def _region(conn: Connection, region_id: str, lock: bool = False) -> Any:
    row = conn.execute(
        text(
            "SELECT id, name, status, country_codes FROM geo.region WHERE id = :r"
            + (" FOR UPDATE" if lock else "")
        ),
        {"r": region_id},
    ).first()
    if row is None:
        raise not_found("region")
    return row


def _installation_trips(
    conn: Connection, person_id: uuid.UUID, region_id: str, countries: list[str]
) -> list[RemovalTrip]:
    rows = conn.execute(
        text(
            """
            SELECT t.id, t.title, t.status FROM app.trip t
            WHERE EXISTS (SELECT 1 FROM app.trip_member tm WHERE tm.trip_id = t.id AND tm.person_id = :i) AND NOT t.is_seed AND (
                t.destination_country = ANY (:c)
                OR EXISTS (
                    SELECT 1 FROM app.itinerary it
                    JOIN app.itinerary_day d ON d.itinerary_id = it.id
                    JOIN app.itinerary_item x ON x.day_id = d.id
                    JOIN geo.place p ON p.id = x.place_id
                    WHERE it.trip_id = t.id AND p.region_id = :r))
            ORDER BY t.status DESC, t.start_date DESC NULLS LAST, t.id
            """
        ),
        {"i": person_id, "r": region_id, "c": countries},
    ).all()
    return [RemovalTrip(id=r.id, title=r.title, status=r.status) for r in rows]


def preview(conn: Connection, person_id: uuid.UUID, region_id: str) -> RegionRemoval:
    region = _region(conn, region_id)
    counts = conn.execute(
        text(
            f"""
            SELECT count(*) AS total,
                   count(*) FILTER (WHERE {_PLACE_KEPT}) AS kept,
                   COALESCE(sum(pg_column_size(p.*) + COALESCE(
                       (SELECT sum(pg_column_size(s.*)) FROM geo.place_source s
                        WHERE s.place_id = p.id), 0)
                       + COALESCE((SELECT pg_column_size(g.*) FROM geo.place_signal g
                        WHERE g.place_id = p.id), 0))
                       FILTER (WHERE NOT ({_PLACE_KEPT})), 0) AS freed
            FROM geo.place p WHERE p.region_id = :r
            """
        ),
        {"r": region_id},
    ).one()
    areas = conn.execute(
        text(
            f"SELECT count(*) AS total, count(*) FILTER (WHERE {_AREA_KEPT}) AS kept"
            " FROM geo.admin_area a WHERE a.region_id = :r"
        ),
        {"r": region_id},
    ).one()
    cities = conn.execute(
        text(
            f"""
            SELECT count(*) AS total,
                   count(*) FILTER (WHERE {_CITY_KEPT}) AS kept,
                   COALESCE(sum(pg_column_size(c.*)) FILTER (WHERE NOT ({_CITY_KEPT})), 0) AS freed
            FROM geo.city c WHERE c.country_iso2 IN ({_FREE_COUNTRIES})
            """
        ),
        {"r": region_id, "c": list(region.country_codes)},
    ).one()
    return RegionRemoval(
        region_id=region.id,
        name=region.name,
        places_total=int(counts.total),
        places_removed=int(counts.total) - int(counts.kept),
        places_kept=int(counts.kept),
        admin_areas_removed=int(areas.total) - int(areas.kept),
        admin_areas_kept=int(areas.kept),
        cities_removed=int(cities.total) - int(cities.kept),
        cities_kept=int(cities.kept),
        trips=_installation_trips(conn, person_id, region_id, list(region.country_codes)),
        bytes_freed_estimate=int(counts.freed) + int(cities.freed),
    )


def remove(conn: Connection, person_id: uuid.UUID, region_id: str) -> RegionRemoval:
    """Remove the region's data as ``preview`` describes it. 409 ``import_running`` while any region
    is being imported (one change to ``geo`` at a time)."""
    region = _region(conn, region_id, lock=True)
    running = conn.execute(
        text("SELECT id FROM geo.region WHERE status = 'importing' LIMIT 1")
    ).scalar_one_or_none()
    if running is not None:
        raise conflict("import_running", f"the region {running} is being imported: try again later")
    result = preview(conn, person_id, region_id)
    conn.execute(
        text(f"DELETE FROM geo.place p WHERE p.region_id = :r AND NOT ({_PLACE_KEPT})"),
        {"r": region_id},
    )
    conn.execute(
        text("UPDATE geo.place SET is_active = false WHERE region_id = :r AND is_active"),
        {"r": region_id},
    )
    conn.execute(
        text(f"DELETE FROM geo.admin_area a WHERE a.region_id = :r AND NOT ({_AREA_KEPT})"),
        {"r": region_id},
    )
    conn.execute(
        text("UPDATE geo.admin_area SET is_active = false WHERE region_id = :r AND is_active"),
        {"r": region_id},
    )
    # The cities of countries no other region with data covers, except those the app still names
    # (after the places, so a kept place's city stays).
    conn.execute(
        text(
            f"DELETE FROM geo.city c WHERE c.country_iso2 IN ({_FREE_COUNTRIES})"
            f" AND NOT ({_CITY_KEPT})"
        ),
        {"r": region_id, "c": list(region.country_codes)},
    )
    # Names and photo links of places and cities that are gone. Kept ones keep theirs.
    names_store.prune(conn)
    conn.execute(
        text(
            "DELETE FROM geo.image_lookup l WHERE l.kind = 'city'"
            " AND NOT EXISTS (SELECT 1 FROM geo.city c WHERE c.id::text = l.ref_id)"
        )
    )
    conn.execute(
        text(
            "DELETE FROM geo.image_lookup l WHERE l.kind = 'place'"
            " AND NOT EXISTS (SELECT 1 FROM geo.place p WHERE p.id::text = l.ref_id)"
        )
    )
    conn.execute(
        text(
            "UPDATE geo.region SET status = 'disabled', current_import_run_id = NULL WHERE id = :r"
        ),
        {"r": region_id},
    )
    log.info(
        "region_removed",
        region=region.id,
        places_removed=result.places_removed,
        places_kept=result.places_kept,
    )
    return result


def vacuum_full(engine: Engine | None) -> None:
    """Rewrite the region tables after a large removal. Best effort: the data is already gone."""
    if engine is None:
        return
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(
                text(
                    "VACUUM (FULL, ANALYZE) geo.place, geo.place_source, geo.place_signal,"
                    " geo.admin_area"
                )
            )
    except Exception as exc:
        log.warning("vacuum_failed", error=type(exc).__name__)
