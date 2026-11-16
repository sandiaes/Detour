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
from detour_api.names.api import to_api
from detour_api.names.store import PLACE_NAME_COLUMNS, resolve_place_row
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


# A region's coverage polygon is checked with this much slack (degrees, about 5 km): Geofabrik's
# polygons are simplified, so a place on the border must not fall out of its own region.
REGION_SLACK_DEGREES = 0.05


def region_for_country(
    conn: Connection, country_iso2: str, lat: float | None = None, lon: float | None = None
) -> tuple[str, str] | None:
    """The region that covers a country: an available one first. Returns (id, status).

    With a point, a region whose coverage polygon is known must also cover the point (with a little
    slack): a city extract such as Greater London or Paris claims its whole country by code, and
    Manchester or Lyon are not in it (ADR 033). A region with no polygon is matched by country.
    """
    row = conn.execute(
        text(
            "SELECT id, status FROM geo.region r WHERE :c = ANY (r.country_codes)"
            " AND (CAST(:lat AS double precision) IS NULL OR r.geom IS NULL OR ST_DWithin(r.geom,"
            "      ST_SetSRID(ST_MakePoint(CAST(:lon AS double precision),"
            "                              CAST(:lat AS double precision)), 4326), :slack))"
            " ORDER BY (r.status = 'available') DESC, r.id LIMIT 1"
        ),
        {"c": country_iso2, "lat": lat, "lon": lon, "slack": REGION_SLACK_DEGREES},
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
                applies_to="Places, administrative areas; search results from Photon",
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
          AND (r.geom IS NULL OR ST_DWithin(r.geom, ST_SetSRID(ST_MakePoint(h.lon, h.lat), 4326),
               CAST(:slack AS double precision)))
    ORDER BY (r.status = 'available') DESC, r.id LIMIT 1
) reg ON true
ORDER BY h.tier, h.population DESC NULLS LAST, h.sim DESC, h.kind, h.ref
LIMIT :limit
"""


def search_destinations(conn: Connection, query: str, limit: int) -> list[DestinationResult]:
    norm = normalize_text(query)
    if not norm:
        return []
    rows = conn.execute(
        text(_DESTINATION_SQL), {"q": norm, "limit": limit, "slack": REGION_SLACK_DEGREES}
    ).all()
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
        region = region_for_country(conn, row.country_iso2, row.lat, row.lon)
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
    person_id: uuid.UUID | None = None,
) -> tuple[str, dict[str, Any]]:
    """The place-search SQL and its parameters (exposed so tests can EXPLAIN the real query).
    ``person_id`` applies that installation's approved display names (ADR 025)."""
    params: dict[str, Any] = {
        "limit": limit,
        "inst": str(person_id) if person_id is not None else None,
    }
    where = ["p.is_active"]
    tier = "NULL::int"
    sim = "0::real"
    order: list[str] = []
    if query:
        norm = normalize_text(query)
        params["q"] = norm
        # The local name, the English one, any alias the source gives (other languages,
        # romanizations, ASCII spellings) or a name fetched from Wikidata (ADR 025).
        where.append(
            "(p.name_norm LIKE '%' || :q || '%' OR p.name_norm % :q"
            " OR p.name_en_norm LIKE '%' || :q || '%' OR p.name_en_norm % :q"
            " OR p.alias_norm LIKE '%' || :q || '%'"
            " OR p.id IN (SELECT CAST(n.entity_ref AS uuid) FROM geo.place_name n"
            "   WHERE n.entity_kind = 'place'"
            "   AND (n.name_norm LIKE '%' || :q || '%' OR n.name_norm % :q)))"
        )

        def tier_of(col: str) -> str:
            return (
                f"CASE WHEN {col} = :q THEN 0 WHEN {col} LIKE :q || '%' THEN 1"
                f" WHEN {col} LIKE '% ' || :q || '%' THEN 2"
                f" WHEN {col} LIKE '%' || :q || '%' THEN 3 ELSE 4 END"
            )

        alias_tier = (
            "CASE WHEN p.alias_norm IS NULL THEN NULL"
            " WHEN '|' || p.alias_norm || '|' LIKE '%|' || :q || '|%' THEN 0"
            " WHEN '|' || p.alias_norm LIKE '%|' || :q || '%' THEN 1"
            " WHEN p.alias_norm LIKE '% ' || :q || '%' THEN 2"
            " WHEN p.alias_norm LIKE '%' || :q || '%' THEN 3 ELSE 4 END"
        )
        stored_tier = (
            f"(SELECT min({tier_of('n.name_norm')}) FROM geo.place_name n"
            " WHERE n.entity_kind = 'place' AND n.entity_ref = p.id::text)"
        )
        # LEAST ignores a NULL (no English name, no alias), so the best match counts.
        tier = (
            f"LEAST({tier_of('p.name_norm')}, {tier_of('p.name_en_norm')}, {alias_tier},"
            f" {stored_tier})"
        )
        sim = "GREATEST(similarity(p.name_norm, :q), COALESCE(similarity(p.name_en_norm, :q), 0))"
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
               p.region_id, p.city_id, c.name AS city_name,
               p.names_i18n->>'en' AS en_name, p.name_en_norm, p.names_i18n,
               {PLACE_NAME_COLUMNS},
               {tier} AS tier, {sim} AS sim, {dist} AS dist
        FROM geo.place p
        LEFT JOIN geo.city c ON c.id = p.city_id
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
            name_en=r.en_name if r.name_en_norm else None,
            names=to_api(resolve_place_row(r)) if r.name else None,
            kind=r.kind,
            category=r.category,
            lat=r.lat,
            lon=r.lon,
            region_id=r.region_id,
            city_id=r.city_id,
            city_name=r.city_name,
            distance_m=None if r.dist is None else round(r.dist, 1),
            match=None if r.tier is None else MATCH_NAMES[r.tier],
        )
        for r in rows
    ]


def place_exists(
    conn: Connection, place_id: uuid.UUID, person_id: uuid.UUID | None = None
) -> tuple[str, str, float, float, bool, int | None, str] | None:
    """(kind, display name, lat, lon, is_active, default_visit_minutes, category) of a
    geo.place."""
    row = conn.execute(
        text(
            "SELECT p.id, p.kind, p.name, p.names_i18n, ST_Y(p.geom) lat, ST_X(p.geom) lon,"
            " p.is_active, p.default_visit_minutes, p.category, "
            + PLACE_NAME_COLUMNS
            + " FROM geo.place p WHERE p.id = :i"
        ),
        {"i": place_id, "inst": str(person_id) if person_id is not None else None},
    ).first()
    # The resolved English-facing name (ADR 025), or the category for an unnamed place.
    return (
        None
        if row is None
        else (
            row.kind,
            resolve_place_row(row).display or row.category,
            row.lat,
            row.lon,
            row.is_active,
            row.default_visit_minutes,
            row.category,
        )
    )


def get_place(
    conn: Connection, place_id: uuid.UUID, person_id: uuid.UUID | None = None
) -> PlaceDetail | None:
    row = conn.execute(
        text(
            f"""
            SELECT p.id, p.name, p.kind, p.category, ST_Y(p.geom) AS lat, ST_X(p.geom) AS lon,
                   p.region_id, p.city_id, c.name AS city_name, p.names_i18n, p.names_i18n->>'en' AS en_name,
                   p.name_en_norm, p.address, p.default_visit_minutes,
                   p.is_active, s.wikidata_id, {PLACE_NAME_COLUMNS}
            FROM geo.place p
            LEFT JOIN geo.city c ON c.id = p.city_id
            LEFT JOIN geo.place_signal s ON s.place_id = p.id
            WHERE p.id = :i
            """
        ),
        {"i": place_id, "inst": str(person_id) if person_id is not None else None},
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
        name_en=row.en_name if row.name_en_norm else None,
        names=to_api(resolve_place_row(row)) if row.name else None,
        kind=row.kind,
        category=row.category,
        lat=row.lat,
        lon=row.lon,
        region_id=row.region_id,
        city_id=row.city_id,
        city_name=row.city_name,
        names_i18n=row.names_i18n,
        address=row.address,
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
