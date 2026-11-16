"""Region catalog and import jobs started from the app (ADR 033, step 3)."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Connection, text

from detour_api.errors import conflict, not_found
from detour_api.importer.regions import REGIONS
from detour_api.importer.report import GEO_SIZE_LIMIT_BYTES
from detour_api.models.search import CatalogRegion, ImportJob, RegionCatalog
from detour_api.settings import Settings

ACTIVE = ("requested", "running")


def _job(row: Any, stall: timedelta, now: datetime) -> ImportJob:
    status = row.status
    if status in ACTIVE and now - row.updated_at > stall:
        status = "stalled"
    return ImportJob(
        id=row.id,
        status=status,
        message=row.message,
        run_url=row.run_url,
        requested_at=row.requested_at,
        updated_at=row.updated_at,
    )


def latest_jobs(conn: Connection, settings: Settings) -> dict[str, ImportJob]:
    rows = conn.execute(
        text(
            "SELECT DISTINCT ON (region_id) id, region_id, status, message, run_url,"
            " requested_at, updated_at FROM geo.import_job ORDER BY region_id, requested_at DESC"
        )
    ).all()
    stall = timedelta(minutes=settings.import_job_stall_minutes)
    now = datetime.now(UTC)
    return {r.region_id: _job(r, stall, now) for r in rows}


def catalog(
    conn: Connection, settings: Settings, can_manage: bool, import_enabled: bool
) -> RegionCatalog:
    stored = {
        r.id: r
        for r in conn.execute(
            text(
                "SELECT r.id, r.status, r.current_import_run_id,"
                " (SELECT count(*) FROM geo.place p WHERE p.region_id = r.id AND p.is_active) AS n,"
                " (SELECT count(*) FROM geo.place p WHERE p.region_id = r.id"
                "  AND NOT p.is_active) AS kept FROM geo.region r"
            )
        ).all()
    }
    jobs = latest_jobs(conn, settings)
    size = conn.execute(
        text(
            "SELECT COALESCE(SUM(pg_total_relation_size(c.oid)), 0)::bigint FROM pg_class c"
            " JOIN pg_namespace n ON n.oid = c.relnamespace"
            " WHERE n.nspname = 'geo' AND c.relkind = 'r'"
        )
    ).scalar_one()
    regions = []
    for definition in REGIONS.values():
        row = stored.get(definition.id)
        regions.append(
            CatalogRegion(
                id=definition.id,
                name=definition.name,
                country_codes=list(definition.countries),
                download_mb=definition.download_mb,
                state="not_imported" if row is None else row.status,
                places=0 if row is None else int(row.n),
                places_kept=0 if row is None else int(row.kept),
                job=jobs.get(definition.id),
            )
        )
    return RegionCatalog(
        can_manage=can_manage,
        import_enabled=import_enabled,
        geo_bytes=int(size),
        geo_limit_bytes=GEO_SIZE_LIMIT_BYTES,
        regions=regions,
    )


def start_job(
    conn: Connection, settings: Settings, region_id: str, installation_id: uuid.UUID
) -> uuid.UUID:
    """Record a request. 404 for a region that is not in the catalog; 409 while an import of any
    region is running or was requested and is not stalled (one change to ``geo`` at a time)."""
    if region_id not in REGIONS:
        raise not_found("region")
    conn.execute(text("LOCK TABLE geo.import_job IN SHARE ROW EXCLUSIVE MODE"))
    running = conn.execute(
        text("SELECT id FROM geo.region WHERE status = 'importing' LIMIT 1")
    ).scalar_one_or_none()
    if running is not None:
        raise conflict("import_running", f"the region {running} is being imported")
    stall = timedelta(minutes=settings.import_job_stall_minutes)
    for row in conn.execute(
        text(
            "SELECT id, region_id, status, message, run_url, requested_at, updated_at"
            " FROM geo.import_job WHERE status IN ('requested', 'running')"
        )
    ).all():
        if _job(row, stall, datetime.now(UTC)).status != "stalled":
            raise conflict("import_running", f"an import of {row.region_id} is under way")
    job_id = uuid.uuid4()
    conn.execute(
        text("INSERT INTO geo.import_job (id, region_id, requested_by) VALUES (:j, :r, :i)"),
        {"j": job_id, "r": region_id, "i": installation_id},
    )
    return job_id


def finish_request(
    conn: Connection, job_id: uuid.UUID, *, ok: bool, message: str | None, run_url: str | None
) -> None:
    """After the dispatch: a refused or failed request is a failed job at once."""
    conn.execute(
        text(
            "UPDATE geo.import_job SET status = :s, message = :m, run_url = :u, updated_at = now()"
            " WHERE id = :j"
        ),
        {"j": job_id, "s": "requested" if ok else "failed", "m": message, "u": run_url},
    )
