"""Load a staged OpenStreetMap extract into the ``geo`` schema of the target database.

Flow (docs/data-model.md, ADR 005):

1. transaction 1 records the region and a new ``geo.import_run`` (status ``running``);
2. transaction 2 streams the staging rows into temporary tables with COPY, merges them into the
   ``geo`` tables, deactivates what disappeared, checks its own counts against the database,
   evaluates the readiness gates and commits; it is all-or-nothing;
3. on failure the run is marked ``failed`` (transaction 3) and the data stays as it was.

The merge is an upsert keyed by a deterministic identifier, so running the same import twice
leaves the same rows. Places that vanish from a later extract are kept with ``is_active = false``
instead of being deleted, because accepted itineraries may still show them.

The target connection must be a session-mode connection (Supabase session pooler, port 5432):
temporary tables and the advisory lock need a session.
"""

import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import psycopg
import structlog
from psycopg.types.json import Jsonb

from detour_api.db import SEARCH_PATH
from detour_api.importer import IMPORTER_VERSION
from detour_api.importer.derive import OSM_LICENCE, PlaceRow, build_place, source_ref
from detour_api.importer.pipeline import Candidate, iter_boundaries, iter_candidates, libpq_url
from detour_api.importer.regions import RegionDef
from detour_api.importer.report import (
    Counters,
    evaluate_gates,
    pct,
    render_markdown,
)
from detour_api.importer.selection import (
    REASON_NO_GEOMETRY,
    RULES_VERSION,
    decide,
)
from detour_api.textnorm import normalize_text, stable_uuid

# An area's Wikidata item (its photo, ADR 022 amendment); a malformed tag is dropped, not kept.
WIKIDATA_ID = re.compile(r"^Q[0-9]+$")

log = structlog.get_logger("detour.import")

IMPORT_LOCK_KEY = 7_240_001  # advisory lock: one import at a time per database
NEEDED_TABLES = ("geo.place", "geo.region", "geo.import_run", "geo.city")


class ImportError_(RuntimeError):
    pass


@dataclass(frozen=True)
class SourceInfo:
    url: str | None
    sha256: str | None
    size: int | None
    osm_snapshot_date: date | None


def check_target(conn: psycopg.Connection[Any]) -> None:
    """Fail early, with a useful message, if the target is not migrated."""
    conn.execute(f"SET search_path TO {SEARCH_PATH}")
    conn.commit()  # session-level: a rollback of an open transaction would undo it
    for table in NEEDED_TABLES:
        row = conn.execute("SELECT to_regclass(%s)", (table,)).fetchone()
        if row is None or row[0] is None:
            raise ImportError_(f"{table} does not exist: run 'alembic upgrade head' first")
    conn.rollback()


def start_run(
    conn: psycopg.Connection[Any], region: RegionDef, source: SourceInfo, poly_wkt: str | None
) -> uuid.UUID:
    run_id = uuid.uuid4()
    with conn.transaction():
        conn.execute(
            """
            INSERT INTO geo.region (id, name, country_codes, geom)
            VALUES (%s, %s, %s, CASE WHEN %s::text IS NULL THEN NULL
                                     ELSE ST_Multi(ST_SetSRID(ST_GeomFromText(%s), 4326)) END)
            ON CONFLICT (id) DO UPDATE
                SET name = EXCLUDED.name,
                    country_codes = EXCLUDED.country_codes,
                    geom = COALESCE(EXCLUDED.geom, geo.region.geom)
            """,
            (region.id, region.name, list(region.countries), poly_wkt, poly_wkt),
        )
        conn.execute(
            """
            INSERT INTO geo.import_run
                (id, region_id, importer_version, rules_version, source_url, source_sha256,
                 source_bytes, osm_snapshot_date, started_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                run_id,
                region.id,
                IMPORTER_VERSION,
                RULES_VERSION,
                source.url,
                source.sha256,
                source.size,
                source.osm_snapshot_date,
                datetime.now(UTC),
            ),
        )
        # A region that has never been usable shows as importing; an available one stays so.
        conn.execute(
            "UPDATE geo.region SET status = 'importing' WHERE id = %s AND status = 'disabled'"
            " AND current_import_run_id IS NULL",
            (region.id,),
        )
    return run_id


def fail_run(conn: psycopg.Connection[Any], run_id: uuid.UUID, region_id: str, error: str) -> None:
    conn.rollback()
    with conn.transaction():
        conn.execute(
            "UPDATE geo.import_run SET status = 'failed', finished_at = %s, error = %s"
            " WHERE id = %s",
            (datetime.now(UTC), error[:2000], run_id),
        )
        conn.execute(
            "UPDATE geo.region SET status = 'disabled' WHERE id = %s AND status = 'importing'",
            (region_id,),
        )


_STAGE_PLACE = """
CREATE TEMP TABLE stage_place (
    id uuid, kind text, category text, name text, name_norm text, names_i18n jsonb,
    name_en_norm text, alias_norm text, lon float8, lat float8, address jsonb, source_ref text, tags jsonb,
    wikidata_id text, osm_signals jsonb, score numeric
) ON COMMIT DROP
"""
_STAGE_AREA = """
CREATE TEMP TABLE stage_area (
    id uuid, name text, name_norm text, level smallint, country_iso2 text,
    geom geometry, source_ref text, wikidata_id text
) ON COMMIT DROP
"""


def _place_values(place: PlaceRow) -> tuple[object, ...]:
    return (
        place.id,
        place.kind,
        place.category,
        place.name,
        place.name_norm,
        Jsonb(place.names_i18n) if place.names_i18n else None,
        place.name_en_norm,
        place.alias_norm,
        place.lon,
        place.lat,
        Jsonb(place.address) if place.address else None,
        place.source_ref,
        Jsonb(place.source_tags),
        place.signal.wikidata_id,
        Jsonb(place.signal.osm_signals),
        place.signal.score,
    )


def classify_candidates(
    region: RegionDef,
    candidates: Iterable[Candidate],
    counters: Counters,
) -> Iterable[PlaceRow]:
    """Apply the selection rule, count everything, and yield the places to keep."""
    for cand in candidates:
        decision = decide(cand.tags)
        if decision is None:
            counters.not_candidates += 1
            continue
        ref = source_ref(cand.osm_type, cand.osm_id)
        if not decision.kept:
            counters.exclude(decision, ref, cand.tags)
            continue
        if cand.lon is None or cand.lat is None:
            counters.exclude(decision, ref, cand.tags, REASON_NO_GEOMETRY)
            continue
        place = build_place(
            region.id, cand.osm_type, cand.osm_id, decision, cand.tags, cand.lon, cand.lat
        )
        counters.kept(place)
        yield place


def _copy_places(conn: psycopg.Connection[Any], places: Iterable[PlaceRow]) -> int:
    n = 0
    with (
        conn.cursor() as cur,
        cur.copy(
            "COPY stage_place (id, kind, category, name, name_norm, names_i18n, name_en_norm, alias_norm, lon, lat,"
            " address,"
            " source_ref, tags, wikidata_id,"
            " osm_signals, score) FROM STDIN"
        ) as copy,
    ):
        for place in places:
            copy.write_row(_place_values(place))
            n += 1
    return n


def _copy_areas(
    conn: psycopg.Connection[Any], region: RegionDef, staging: psycopg.Connection[Any]
) -> int:
    n = 0
    with (
        conn.cursor() as cur,
        cur.copy(
            "COPY stage_area (id, name, name_norm, level, country_iso2, geom, source_ref, wikidata_id)"
            " FROM STDIN"
        ) as copy,
    ):
        for b in iter_boundaries(staging):
            name = (b.tags.get("name") or "").strip()
            level_text = b.tags.get("admin_level", "")
            if not name or not level_text.isdigit():
                continue
            iso = (b.tags.get("ISO3166-2") or "")[:2]
            if len(iso) != 2 or iso not in region.countries:
                iso = region.countries[0] if len(region.countries) == 1 else ""
            ref = f"relation/{b.osm_id}"
            qid = (b.tags.get("wikidata") or "").strip()
            copy.write_row(
                (
                    str(stable_uuid("admin_area", f"{region.id}/osm/{ref}")),
                    name,
                    normalize_text(name),
                    int(level_text),
                    iso or None,
                    b.ewkb_hex,
                    ref,
                    qid if WIKIDATA_ID.match(qid) else None,
                )
            )
            n += 1
    return n


def assign_cities(conn: psycopg.Connection[Any], region_id: str) -> int:
    """Set ``city_id`` to the nearest gazetteer city of the region's countries.

    Distance is the planar distance in degrees, taken from the GiST index; of the five nearest
    candidates the one with the smallest great-circle distance wins, ties broken by identifier.
    """
    cur = conn.execute(
        """
        WITH r AS (SELECT country_codes FROM geo.region WHERE id = %(r)s),
        nearest AS (
            SELECT p.id AS place_id,
                   (SELECT x.id FROM (
                        SELECT c.id,
                               ST_DistanceSphere(c.geom, p.geom) AS d
                        FROM geo.city c, r
                        WHERE c.country_iso2 = ANY (r.country_codes)
                        ORDER BY c.geom <-> p.geom
                        LIMIT 5) x
                    ORDER BY x.d, x.id LIMIT 1) AS city_id
            FROM geo.place p
            WHERE p.region_id = %(r)s AND p.is_active
        )
        UPDATE geo.place p SET city_id = n.city_id
        FROM nearest n
        WHERE p.id = n.place_id AND p.city_id IS DISTINCT FROM n.city_id
        """,
        {"r": region_id},
    )
    return cur.rowcount


# An import that removes at least this many rows rewrites the tables afterwards (VACUUM FULL), so
# the database file shrinks. Smaller clean-ups only make the space reusable.
FULL_VACUUM_THRESHOLD = 1000

# Itinerary items in app that name a geo place keep it from being deleted (soft reference, no
# foreign key: the trip keeps its own snapshot either way).
_REFERENCED_BY_APP = "EXISTS (SELECT 1 FROM app.itinerary_item i WHERE i.place_id = p.id)"


def _merge(conn: psycopg.Connection[Any], region: RegionDef, run_id: uuid.UUID) -> dict[str, int]:
    """Bring the region's geo rows in line with the staged ones.

    Rows that did not change are not written at all (``WHERE ... IS DISTINCT FROM``): rewriting
    them would leave a dead copy of every row behind on each import. Places that are gone from the
    extract are deleted, unless an itinerary item still names them, in which case
    they stay with ``is_active = false``.
    """
    params = {"region": region.id, "run": run_id, "lic": OSM_LICENCE}
    conn.execute(
        """
        INSERT INTO geo.place
            (id, region_id, kind, category, name, name_norm, names_i18n, name_en_norm, alias_norm,
             geom, address, is_active, first_import_run_id, last_changed_import_run_id)
        SELECT id, %(region)s, kind, category, name, name_norm, names_i18n, name_en_norm, alias_norm,
               ST_SetSRID(ST_MakePoint(lon, lat), 4326), address, true, %(run)s, %(run)s
        FROM stage_place
        ON CONFLICT (id) DO UPDATE SET
            kind = EXCLUDED.kind, category = EXCLUDED.category, name = EXCLUDED.name,
            name_norm = EXCLUDED.name_norm, names_i18n = EXCLUDED.names_i18n,
            name_en_norm = EXCLUDED.name_en_norm, alias_norm = EXCLUDED.alias_norm, geom = EXCLUDED.geom, address = EXCLUDED.address, is_active = true,
            last_changed_import_run_id = EXCLUDED.last_changed_import_run_id
        WHERE (geo.place.kind, geo.place.category, geo.place.name, geo.place.name_norm,
               geo.place.names_i18n, geo.place.name_en_norm, geo.place.alias_norm, geo.place.geom,
               geo.place.address, geo.place.is_active)
              IS DISTINCT FROM
              (EXCLUDED.kind, EXCLUDED.category, EXCLUDED.name, EXCLUDED.name_norm,
               EXCLUDED.names_i18n, EXCLUDED.name_en_norm, EXCLUDED.alias_norm, EXCLUDED.geom,
               EXCLUDED.address, true)
        """,
        params,
    )
    conn.execute(
        """
        INSERT INTO geo.place_source (place_id, source, source_ref, licence_code, tags, import_run_id)
        SELECT id, 'osm', source_ref, %(lic)s, tags, %(run)s FROM stage_place
        ON CONFLICT (place_id, source, source_ref) DO UPDATE SET
            licence_code = EXCLUDED.licence_code, tags = EXCLUDED.tags,
            import_run_id = EXCLUDED.import_run_id
        WHERE (geo.place_source.licence_code, geo.place_source.tags)
              IS DISTINCT FROM (EXCLUDED.licence_code, EXCLUDED.tags)
        """,
        params,
    )
    conn.execute(
        """
        INSERT INTO geo.place_signal (place_id, wikidata_id, osm_signals, score)
        SELECT id, wikidata_id, osm_signals, score FROM stage_place
        ON CONFLICT (place_id) DO UPDATE SET
            wikidata_id = EXCLUDED.wikidata_id, osm_signals = EXCLUDED.osm_signals,
            score = EXCLUDED.score
        WHERE (geo.place_signal.wikidata_id, geo.place_signal.osm_signals, geo.place_signal.score)
              IS DISTINCT FROM (EXCLUDED.wikidata_id, EXCLUDED.osm_signals, EXCLUDED.score)
        """
    )
    # Places of this region that are not in the new extract (this also clears places that an
    # earlier version of the import only deactivated).
    purged = conn.execute(
        f"""
        DELETE FROM geo.place p
        WHERE p.region_id = %(region)s
          AND NOT EXISTS (SELECT 1 FROM stage_place s WHERE s.id = p.id)
          AND NOT ({_REFERENCED_BY_APP})
        """,
        params,
    ).rowcount
    deactivated = conn.execute(
        """
        UPDATE geo.place p SET is_active = false
        WHERE p.region_id = %(region)s AND p.is_active
          AND NOT EXISTS (SELECT 1 FROM stage_place s WHERE s.id = p.id)
        """,
        params,
    ).rowcount
    conn.execute(
        """
        INSERT INTO geo.admin_area
            (id, region_id, name, name_norm, level, country_iso2, geom, source, source_ref,
             licence_code, is_active, last_changed_import_run_id, wikidata_id)
        SELECT s.id, %(region)s, s.name, s.name_norm, s.level, c.iso2,
               ST_SetSRID(s.geom, 4326), 'osm', s.source_ref, %(lic)s, true, %(run)s,
               s.wikidata_id
        FROM stage_area s LEFT JOIN geo.country c ON c.iso2 = s.country_iso2
        ON CONFLICT (source, source_ref) DO UPDATE SET
            name = EXCLUDED.name, name_norm = EXCLUDED.name_norm, level = EXCLUDED.level,
            country_iso2 = EXCLUDED.country_iso2, geom = EXCLUDED.geom, is_active = true,
            last_changed_import_run_id = EXCLUDED.last_changed_import_run_id,
            wikidata_id = EXCLUDED.wikidata_id
        WHERE (geo.admin_area.name, geo.admin_area.name_norm, geo.admin_area.level,
               geo.admin_area.country_iso2, geo.admin_area.geom, geo.admin_area.is_active,
               geo.admin_area.wikidata_id)
              IS DISTINCT FROM
              (EXCLUDED.name, EXCLUDED.name_norm, EXCLUDED.level, EXCLUDED.country_iso2,
               EXCLUDED.geom, true, EXCLUDED.wikidata_id)
        """,
        params,
    )
    # Trips keep their own snapshot of a destination, so an area that is gone can simply go.
    areas_purged = conn.execute(
        "DELETE FROM geo.admin_area a WHERE a.region_id = %(region)s"
        " AND NOT EXISTS (SELECT 1 FROM stage_area s WHERE s.source_ref = a.source_ref)",
        params,
    ).rowcount
    return {
        "places_purged": purged,
        "places_deactivated": deactivated,
        "admin_areas_purged": areas_purged,
    }


def _db_counts(conn: psycopg.Connection[Any], region_id: str) -> dict[str, dict[str, int]]:
    rows = conn.execute(
        """
        SELECT p.kind,
               count(*),
               count(p.name),
               count(*) FILTER (WHERE s.wikidata_id IS NOT NULL)
        FROM geo.place p
        LEFT JOIN geo.place_signal s ON s.place_id = p.id
        WHERE p.region_id = %s AND p.is_active
        GROUP BY p.kind
        """,
        (region_id,),
    ).fetchall()
    return {kind: {"total": t, "named": n, "with_wikidata": w} for kind, t, n, w in rows}


def _geo_bytes(conn: psycopg.Connection[Any]) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(pg_total_relation_size(c.oid)), 0)::bigint FROM pg_class c"
        " JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'geo' AND c.relkind = 'r'"
    ).fetchone()
    assert row is not None  # noqa: S101
    return int(row[0])


def _verify_counts(counters: Counters, db: dict[str, dict[str, int]]) -> None:
    """The report is built from counters; refuse to commit if the database disagrees."""
    for kind in set(db) | set(counters.kinds):
        seen = counters.kinds.get(kind)
        row = db.get(kind, {"total": 0, "named": 0, "with_wikidata": 0})
        expected = {
            "total": seen.total if seen else 0,
            "named": seen.named if seen else 0,
            "with_wikidata": seen.with_wikidata if seen else 0,
        }
        if expected != row:
            raise ImportError_(f"report and database disagree for {kind}: {expected} vs {row}")


def load_region(
    conn: psycopg.Connection[Any],
    staging: psycopg.Connection[Any],
    region: RegionDef,
    run_id: uuid.UUID,
    source: SourceInfo,
    warnings: list[str],
) -> tuple[dict[str, Any], Counters]:
    counters = Counters()
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (IMPORT_LOCK_KEY,))
        conn.execute(_STAGE_PLACE)
        conn.execute(_STAGE_AREA)
        places = classify_candidates(region, iter_candidates(staging), counters)
        _copy_places(conn, places)
        counters.areas = _copy_areas(conn, region, staging)
        merge_counts = _merge(conn, region, run_id)
        assigned = assign_cities(conn, region.id)
        has_cities = conn.execute(
            "SELECT EXISTS (SELECT 1 FROM geo.city WHERE country_iso2 = ANY (%s))",
            (list(region.countries),),
        ).fetchone()
        if not (has_cities and has_cities[0]):
            warnings.append(
                "No gazetteer cities for this region's countries yet: places have no city_id."
                " Run the gazetteer import, which assigns it."
            )

        _verify_counts(counters, _db_counts(conn, region.id))
        area_count = conn.execute(
            "SELECT count(*) FROM geo.admin_area WHERE region_id = %s AND is_active", (region.id,)
        ).fetchone()
        assert area_count is not None  # noqa: S101
        if area_count[0] != counters.areas:
            raise ImportError_(f"admin areas: loaded {counters.areas}, database {area_count[0]}")
        if source.osm_snapshot_date is None:
            warnings.append("The extract has no replication timestamp: snapshot date unknown.")

        geo_bytes = _geo_bytes(conn)
        gates = evaluate_gates(counters, geo_bytes)
        all_passed = all(g.passed for g in gates)
        status = "available" if all_passed else "disabled"

        report = {
            "region": {"id": region.id, "name": region.name, "countries": list(region.countries)},
            "run": {
                "id": str(run_id),
                "importer_version": IMPORTER_VERSION,
                "rules_version": RULES_VERSION,
            },
            "source": {
                "url": source.url,
                "sha256": source.sha256,
                "bytes": source.size,
                "osm_snapshot_date": source.osm_snapshot_date.isoformat()
                if source.osm_snapshot_date
                else None,
            },
            "kinds": {k: v.as_dict() for k, v in sorted(counters.kinds.items())},
            "admin_areas": counters.areas,
            "excluded": {
                "total": sum(counters.excluded.values()),
                "by_class": counters.excluded_rows(),
            },
            "categories": counters.category_rows(),
            "geo_size_bytes": geo_bytes,
            "gates": [g.as_dict() for g in gates],
            "all_gates_passed": all_passed,
            "region_status": status,
            "retention": merge_counts,
            "warnings": warnings,
        }
        run_counts = {
            "places": {k: v.total for k, v in sorted(counters.kinds.items())},
            "places_total": sum(v.total for v in counters.kinds.values()),
            "excluded_total": report["excluded"]["total"],  # type: ignore[index]
            "admin_areas": counters.areas,
            "places_purged": merge_counts["places_purged"],
            "places_deactivated": merge_counts["places_deactivated"],
            "admin_areas_purged": merge_counts["admin_areas_purged"],
            "cities_assigned_now": assigned,
        }
        conn.execute(
            "UPDATE geo.import_run SET status = 'succeeded', finished_at = %s, counts = %s,"
            " report = %s WHERE id = %s",
            (datetime.now(UTC), Jsonb(run_counts), Jsonb(report), run_id),
        )
        conn.execute(
            "UPDATE geo.region SET current_import_run_id = %s, status = %s WHERE id = %s",
            (run_id, status, region.id),
        )
    return report, counters


def vacuum_and_analyze(conn: psycopg.Connection[Any], full: bool = False) -> int | None:
    """After the commit: reclaim dead row versions and refresh statistics. Returns the new size.

    A plain VACUUM makes dead space reusable but does not shrink the files; ``full`` rewrites the
    tables, which is what lowers the size Supabase counts after a large clean-up. Best effort: the
    data is already committed.
    """
    try:
        conn.autocommit = True
        options = "FULL, ANALYZE" if full else "ANALYZE"
        conn.execute(
            f"VACUUM ({options}) geo.place, geo.place_source, geo.place_signal, geo.admin_area"
        )
        return _geo_bytes(conn)
    except psycopg.Error as exc:
        log.warning("vacuum_failed", error=type(exc).__name__)
        return None
    finally:
        conn.autocommit = False


def finalize_size_gate(
    conn: psycopg.Connection[Any],
    run_id: uuid.UUID,
    region_id: str,
    report: dict[str, Any],
    counters: Counters,
    size_after: int,
) -> None:
    """Gate 6 judged on the size after the vacuum, not on the size inside the import transaction.

    Inside the transaction the files still hold every dead row version the import is about to
    free, so the size read there can fail a region for space that is freed a moment later. The
    other five gates do not depend on size and are unchanged. Updates the stored report and the
    region status when the outcome moves.
    """
    gates = evaluate_gates(counters, size_after)
    all_passed = all(g.passed for g in gates)
    status = "available" if all_passed else "disabled"
    report["geo_size_at_commit_bytes"] = report["geo_size_bytes"]
    report["geo_size_bytes"] = size_after
    report["gates"] = [g.as_dict() for g in gates]
    report["all_gates_passed"] = all_passed
    report["region_status"] = status
    with conn.transaction():
        conn.execute("UPDATE geo.import_run SET report = %s WHERE id = %s", (Jsonb(report), run_id))
        conn.execute("UPDATE geo.region SET status = %s WHERE id = %s", (status, region_id))


def import_region(
    *,
    region: RegionDef,
    staging_url: str,
    target_url: str,
    source: SourceInfo,
    poly_wkt: str | None,
    warnings: list[str] | None = None,
) -> tuple[dict[str, Any], Counters]:
    """Run steps 1 to 3 of the module docstring. Returns the report and the counters."""
    warns = list(warnings or [])
    with (
        psycopg.connect(libpq_url(target_url)) as conn,
        psycopg.connect(libpq_url(staging_url)) as staging,
    ):
        check_target(conn)
        run_id = start_run(conn, region, source, poly_wkt)
        try:
            report, counters = load_region(conn, staging, region, run_id, source, warns)
        except Exception as exc:
            fail_run(conn, run_id, region.id, f"{type(exc).__name__}: {exc}")
            raise
        removed = report["retention"]["places_purged"] + report["retention"]["admin_areas_purged"]
        full = removed >= FULL_VACUUM_THRESHOLD
        size_after = vacuum_and_analyze(conn, full=full)
        report["geo_size_after_vacuum_bytes"] = size_after
        report["vacuum"] = "full" if full else "plain"
        if size_after is not None:
            finalize_size_gate(conn, run_id, region.id, report, counters, size_after)
    log.info("import_done", region=region.id, status=report["region_status"])
    return report, counters


__all__ = ["ImportError_", "SourceInfo", "assign_cities", "import_region", "pct", "render_markdown"]
