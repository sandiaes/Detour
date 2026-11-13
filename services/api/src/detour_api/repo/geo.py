"""Read access to the ``geo`` schema: regions, destination search, place search and lookup.

Every query is parameterised. Search text is normalised with the same function that filled the
``*_norm`` columns at import, so both sides agree.
"""

import math
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, text

from detour_api.models.search import (
    AttributionEntry,
    DataVersion,
    DestinationResult,
    PlaceDetail,
    PlaceSource,
    PlaceSummary,
    RegionInfo,
)
from detour_api.planner.config import DEFAULT_CONFIG
from detour_api.textnorm import normalize_text

METERS_PER_DEGREE = 111_320.0

MATCH_NAMES = {0: "exact", 1: "prefix", 2: "word_prefix", 3: "contains", 4: "similar"}


def list_regions(conn: Connection) -> list[RegionInfo]:
    rows = conn.execute(
        text(
            """
            SELECT r.id, r.name, r.country_codes, r.status, r.current_import_run_id,
                   i.osm_snapshot_date, i.finished_at,
                   COALESCE(i.counts -> 'places', '{}'::jsonb) AS places
            FROM geo.region r LEFT JOIN geo.import_run i ON i.id = r.current_import_run_id
            ORDER BY r.id
            """
        )
    ).all()
    return [
        RegionInfo(
            id=r.id,
            name=r.name,
            country_codes=list(r.country_codes),
            status=r.status,
            data_version=None
            if r.current_import_run_id is None
            else DataVersion(
                import_run_id=r.current_import_run_id,
                osm_snapshot_date=r.osm_snapshot_date,
                finished_at=r.finished_at,
            ),
            counts={k: int(v) for k, v in r.places.items()},
        )
        for r in rows
    ]


def region_for_country(conn: Connection, country_iso2: str) -> tuple[str, str] | None:
    """The region that covers a country: an available one first. Returns (id, status)."""
    row = conn.execute(
        text(
            "SELECT id, status FROM geo.region WHERE :c = ANY (country_codes)"
            " ORDER BY (status = 'available') DESC, id LIMIT 1"
        ),
        {"c": country_iso2},
    ).first()
    return None if row is None else (row.id, row.status)


def licences(conn: Connection) -> list[AttributionEntry]:
    rows = conn.execute(text("SELECT code, name, url, attribution FROM geo.licence")).all()
    by_code = {r.code: r for r in rows}
    entries = []
    if "ODbL-1.0" in by_code:
        r = by_code["ODbL-1.0"]
        entries.append(
            AttributionEntry(
                name="OpenStreetMap",
                text=r.attribution,
                url="https://www.openstreetmap.org/copyright",
                licence=r.code,
                applies_to="Places, restaurants, administrative areas; search results from Photon",
            )
        )
    if "CC-BY-4.0" in by_code:
        r = by_code["CC-BY-4.0"]
        entries.append(
            AttributionEntry(
                name="GeoNames",
                text=r.attribution,
                url="https://www.geonames.org",
                licence=r.code,
                applies_to="Cities, countries and currencies",
            )
        )
    return entries


# -- destinations ------------------------------------------------------------------------------

_DESTINATION_SQL = """
WITH cities AS (
    SELECT 'city' AS kind, c.id::text AS ref, c.name, c.country_iso2, c.population,
           NULL::smallint AS level, ST_Y(c.geom) AS lat, ST_X(c.geom) AS lon,
           c.admin1_code,
           CASE
               WHEN c.name_norm = CAST(:q AS text) THEN 0
               WHEN c.name_norm LIKE CAST(:q AS text) || '%' THEN 1
               WHEN c.alt_names_norm IS NOT NULL AND (
                    c.alt_names_norm = CAST(:q AS text) OR c.alt_names_norm LIKE CAST(:q AS text) || '|%'
                    OR c.alt_names_norm LIKE '%|' || CAST(:q AS text) OR c.alt_names_norm LIKE '%|' || CAST(:q AS text) || '|%'
               ) THEN 1
               WHEN c.name_norm LIKE '% ' || CAST(:q AS text) || '%' THEN 2
               WHEN c.name_norm LIKE '%' || CAST(:q AS text) || '%'
                    OR c.alt_names_norm LIKE '%' || CAST(:q AS text) || '%' THEN 3
               ELSE 4
           END AS tier,
           GREATEST(similarity(c.name_norm, CAST(:q AS text)), similarity(c.ascii_name, CAST(:q AS text))) AS sim
    FROM geo.city c
    WHERE c.name_norm LIKE '%' || CAST(:q AS text) || '%' OR c.alt_names_norm LIKE '%' || CAST(:q AS text) || '%'
          OR c.name_norm % CAST(:q AS text)
),
areas AS (
    SELECT 'area' AS kind, a.id::text AS ref, a.name, a.country_iso2,
           NULL::integer AS population, a.level, ST_Y(ST_PointOnSurface(a.geom)) AS lat,
           ST_X(ST_PointOnSurface(a.geom)) AS lon, NULL::text AS admin1_code,
           CASE
               WHEN a.name_norm = CAST(:q AS text) THEN 0
               WHEN a.name_norm LIKE CAST(:q AS text) || '%' THEN 1
               WHEN a.name_norm LIKE '% ' || CAST(:q AS text) || '%' THEN 2
               WHEN a.name_norm LIKE '%' || CAST(:q AS text) || '%' THEN 3
               ELSE 4
           END AS tier,
           similarity(a.name_norm, CAST(:q AS text)) AS sim
    FROM geo.admin_area a
    WHERE a.is_active
          AND (a.name_norm LIKE '%' || CAST(:q AS text) || '%' OR a.name_norm % CAST(:q AS text))
),
hits AS (
    SELECT * FROM cities UNION ALL SELECT * FROM areas
)
SELECT h.kind, h.ref, h.name, h.country_iso2, co.name AS country_name, a1.name AS admin1_name,
       h.population, h.level, h.lat, h.lon, h.tier,
       reg.id AS region_id, COALESCE(reg.status = 'available', false) AS available
FROM hits h
LEFT JOIN geo.country co ON co.iso2 = h.country_iso2
LEFT JOIN geo.admin_code a1 ON a1.code = h.country_iso2 || '.' || h.admin1_code
LEFT JOIN LATERAL (
    SELECT r.id, r.status FROM geo.region r
    WHERE h.country_iso2 = ANY (r.country_codes)
    ORDER BY (r.status = 'available') DESC, r.id LIMIT 1
) reg ON true
ORDER BY h.tier, h.population DESC NULLS LAST, h.sim DESC, h.kind, h.ref
LIMIT :limit
"""


def search_destinations(conn: Connection, query: str, limit: int) -> list[DestinationResult]:
    norm = normalize_text(query)
    if not norm:
        return []
    rows = conn.execute(text(_DESTINATION_SQL), {"q": norm, "limit": limit}).all()
    return [
        DestinationResult(
            kind=r.kind,
            ref=r.ref,
            name=r.name,
            country_iso2=r.country_iso2,
            country_name=r.country_name,
            admin1_name=r.admin1_name,
            population=r.population,
            admin_level=r.level,
            lat=r.lat,
            lon=r.lon,
            region_id=r.region_id,
            planning_available=bool(r.available),
            unavailable_reason=(
                "region_not_available"
                if not r.available
                else "area_single_city_only"
                if r.kind == "area" and r.country_iso2 in DEFAULT_CONFIG.single_city_countries
                else None
            ),
            match=MATCH_NAMES[r.tier],
        )
        for r in rows
    ]


@dataclass(frozen=True)
class ResolvedDestination:
    name: str
    lat: float
    lon: float
    country_iso2: str | None
    region_id: str | None
    region_status: str | None
    # The countries of the covering region (for an area without its own country code).
    region_countries: tuple[str, ...] = ()


SINGLE_CITY_MESSAGE = (
    "areas in Japan cannot be planned yet (travel between Japanese cities is mostly by rail, "
    "which the planner does not model); choose a city"
)


def area_planning_allowed(dest: ResolvedDestination) -> bool:
    """Japan is planned as single-city trips only for now (app plan D4, ADR 016)."""
    countries = (dest.country_iso2,) if dest.country_iso2 else dest.region_countries
    return not any(c in DEFAULT_CONFIG.single_city_countries for c in countries)


def resolve_destination(conn: Connection, kind: str, ref: str) -> ResolvedDestination | None:
    """Look a destination up in the imported data, with the region that covers it."""
    if kind == "city":
        if not ref.isdigit():
            return None
        row = conn.execute(
            text(
                "SELECT name, ST_Y(geom) lat, ST_X(geom) lon, country_iso2 FROM geo.city"
                " WHERE id = :i"
            ),
            {"i": int(ref)},
        ).first()
        if row is None:
            return None
        region = region_for_country(conn, row.country_iso2)
        return ResolvedDestination(
            row.name,
            row.lat,
            row.lon,
            row.country_iso2,
            None if region is None else region[0],
            None if region is None else region[1],
        )
    try:
        area_id = uuid.UUID(ref)
    except ValueError:
        return None
    area = conn.execute(
        text(
            "SELECT a.name, ST_Y(ST_PointOnSurface(a.geom)) lat, ST_X(ST_PointOnSurface(a.geom)) lon,"
            " a.country_iso2, r.id AS region_id, r.status, r.country_codes FROM geo.admin_area a"
            " JOIN geo.region r ON r.id = a.region_id WHERE a.id = :i AND a.is_active"
        ),
        {"i": area_id},
    ).first()
    if area is None:
        return None
    return ResolvedDestination(
        area.name,
        area.lat,
        area.lon,
        area.country_iso2,
        area.region_id,
        area.status,
        tuple(area.country_codes or ()),
    )


# -- places ------------------------------------------------------------------------------------


def build_place_search(
    *,
    query: str | None,
    region: str | None,
    kind: str | None,
    category: str | None,
    lat: float | None,
    lon: float | None,
    radius_m: float | None,
    limit: int,
) -> tuple[str, dict[str, Any]]:
    """The place-search SQL and its parameters (exposed so tests can EXPLAIN the real query)."""
    params: dict[str, Any] = {"limit": limit}
    where = ["p.is_active"]
    tier = "NULL::int"
    sim = "0::real"
    order: list[str] = []
    if query:
        norm = normalize_text(query)
        params["q"] = norm
        where.append("(p.name_norm LIKE '%' || :q || '%' OR p.name_norm % :q)")
        tier = (
            "CASE WHEN p.name_norm = :q THEN 0 WHEN p.name_norm LIKE :q || '%' THEN 1"
            " WHEN p.name_norm LIKE '% ' || :q || '%' THEN 2"
            " WHEN p.name_norm LIKE '%' || :q || '%' THEN 3 ELSE 4 END"
        )
        sim = "similarity(p.name_norm, :q)"
        order += ["tier", "sim DESC"]
    dist = "NULL::double precision"
    if lat is not None and lon is not None:
        radius = float(radius_m or 1000)
        dlat = radius / METERS_PER_DEGREE
        dlon = radius / (METERS_PER_DEGREE * max(math.cos(math.radians(lat)), 0.01))
        params.update(
            lat=lat,
            lon=lon,
            radius=radius,
            x1=lon - dlon,
            y1=lat - dlat,
            x2=lon + dlon,
            y2=lat + dlat,
        )
        # && uses the GiST index on geom; ST_DWithin then makes the radius exact.
        where.append("p.geom && ST_MakeEnvelope(:x1, :y1, :x2, :y2, 4326)")
        where.append(
            "ST_DWithin(p.geom::geography, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,"
            " :radius)"
        )
        dist = (
            "ST_Distance(p.geom::geography, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography)"
        )
        order.append("dist")
    if not order:
        order = ["p.name_norm NULLS LAST"]
    if region:
        params["region"] = region
        where.append("p.region_id = :region")
    if kind:
        params["kind"] = kind
        where.append("p.kind = :kind")
    if category:
        params["category"] = category
        where.append("p.category = :category")
    sql = f"""
        SELECT p.id, p.name, p.kind, p.category, ST_Y(p.geom) AS lat, ST_X(p.geom) AS lon,
               p.region_id, p.city_id, c.name AS city_name, rp.cuisines, rp.venue_type,
               {tier} AS tier, {sim} AS sim, {dist} AS dist
        FROM geo.place p
        LEFT JOIN geo.city c ON c.id = p.city_id
        LEFT JOIN geo.restaurant_profile rp ON rp.place_id = p.id
        WHERE {" AND ".join(where)}
        ORDER BY {", ".join(order)}, p.id
        LIMIT :limit
    """
    return sql, params


def search_places(conn: Connection, **kwargs: Any) -> list[PlaceSummary]:
    sql, params = build_place_search(**kwargs)
    rows = conn.execute(text(sql), params).all()
    return [
        PlaceSummary(
            id=r.id,
            name=r.name,
            kind=r.kind,
            category=r.category,
            lat=r.lat,
            lon=r.lon,
            region_id=r.region_id,
            city_id=r.city_id,
            city_name=r.city_name,
            cuisines=list(r.cuisines) if r.cuisines is not None else None,
            venue_type=r.venue_type,
            distance_m=None if r.dist is None else round(r.dist, 1),
            match=None if r.tier is None else MATCH_NAMES[r.tier],
        )
        for r in rows
    ]


def place_exists(
    conn: Connection, place_id: uuid.UUID
) -> tuple[str, str, float, float, bool, int | None, str] | None:
    """(kind, display name, lat, lon, is_active, default_visit_minutes, category) of a
    geo.place."""
    row = conn.execute(
        text(
            "SELECT kind, COALESCE(name, category) AS name, ST_Y(geom) lat, ST_X(geom) lon,"
            " is_active, default_visit_minutes, category FROM geo.place WHERE id = :i"
        ),
        {"i": place_id},
    ).first()
    return (
        None
        if row is None
        else (
            row.kind,
            row.name,
            row.lat,
            row.lon,
            row.is_active,
            row.default_visit_minutes,
            row.category,
        )
    )


def get_place(conn: Connection, place_id: uuid.UUID) -> PlaceDetail | None:
    row = conn.execute(
        text(
            """
            SELECT p.id, p.name, p.kind, p.category, ST_Y(p.geom) AS lat, ST_X(p.geom) AS lon,
                   p.region_id, p.city_id, c.name AS city_name, rp.cuisines, rp.venue_type,
                   rp.meal_types, rp.diet_flags, p.names_i18n, p.address, p.default_visit_minutes,
                   p.is_active, s.wikidata_id
            FROM geo.place p
            LEFT JOIN geo.city c ON c.id = p.city_id
            LEFT JOIN geo.restaurant_profile rp ON rp.place_id = p.id
            LEFT JOIN geo.place_signal s ON s.place_id = p.id
            WHERE p.id = :i
            """
        ),
        {"i": place_id},
    ).first()
    if row is None:
        return None
    sources = conn.execute(
        text(
            "SELECT ps.source, ps.source_ref, ps.licence_code, l.attribution FROM geo.place_source ps"
            " JOIN geo.licence l ON l.code = ps.licence_code WHERE ps.place_id = :i"
            " ORDER BY ps.source, ps.source_ref"
        ),
        {"i": place_id},
    ).all()
    return PlaceDetail(
        id=row.id,
        name=row.name,
        kind=row.kind,
        category=row.category,
        lat=row.lat,
        lon=row.lon,
        region_id=row.region_id,
        city_id=row.city_id,
        city_name=row.city_name,
        cuisines=list(row.cuisines) if row.cuisines is not None else None,
        venue_type=row.venue_type,
        names_i18n=row.names_i18n,
        address=row.address,
        meal_types=list(row.meal_types) if row.meal_types is not None else None,
        diet_flags=list(row.diet_flags) if row.diet_flags is not None else None,
        default_visit_minutes=row.default_visit_minutes,
        is_active=row.is_active,
        wikidata_id=row.wikidata_id,
        sources=[
            PlaceSource(
                source=s.source,
                source_ref=s.source_ref,
                licence=s.licence_code,
                attribution=s.attribution,
            )
            for s in sources
        ],
    )
