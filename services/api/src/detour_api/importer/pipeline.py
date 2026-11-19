"""External-tool half of the region import: download, filter, osm2pgsql, reading the staging DB.

The staging database is a throwaway PostGIS (a service container in GitHub Actions, any local
PostGIS elsewhere). Nothing here touches the target database; ``loader.py`` does.
"""

import hashlib
import os
import re
import subprocess
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import httpx
import psycopg
import structlog
from sqlalchemy.engine import make_url

from detour_api.importer import IMPORTER_VERSION

log = structlog.get_logger("detour.import")

LUA_STYLE = Path(__file__).with_name("osm.lua")
DEFAULT_USER_AGENT = f"Detour-import/{IMPORTER_VERSION} (+https://github.com/sandiaes/Detour)"
# Must match the candidate test in osm.lua.
TAGS_FILTER = (
    "nwr/tourism=attraction,museum,gallery,viewpoint,zoo,theme_park,aquarium",
    "nwr/historic",
    "r/admin_level=4,6",
)
# Simplification of boundary polygons, in degrees (about 100 m): areas are used to scope a
# destination, not to draw borders.
BOUNDARY_TOLERANCE_DEG = 0.001


class ToolMissingError(RuntimeError):
    pass


def libpq_url(url: str) -> str:
    """Accept SQLAlchemy-style URLs (``postgresql+psycopg://``) as well as plain ones."""
    return re.sub(r"^postgres(ql)?(\+\w+)?://", "postgresql://", url)


def pg_env(url: str) -> dict[str, str]:
    """libpq environment variables for a URL, so passwords never appear in a command line."""
    parsed = make_url(libpq_url(url))
    env = dict(os.environ)
    mapping = {
        "PGHOST": parsed.host,
        "PGPORT": str(parsed.port) if parsed.port else None,
        "PGUSER": parsed.username,
        "PGPASSWORD": parsed.password,
        "PGDATABASE": parsed.database,
    }
    for key, value in mapping.items():
        if value:
            env[key] = value
    sslmode = parsed.query.get("sslmode")
    if isinstance(sslmode, str):
        env["PGSSLMODE"] = sslmode
    return env


def run_tool(args: list[str], env: dict[str, str] | None = None) -> str:
    try:
        result = subprocess.run(  # noqa: S603
            args, check=True, capture_output=True, text=True, env=env
        )
    except FileNotFoundError as exc:
        raise ToolMissingError(f"{args[0]} is not installed") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"{args[0]} failed: {exc.stderr.strip()[-2000:]}") from exc
    return result.stdout


@dataclass(frozen=True)
class DownloadResult:
    path: Path
    sha256: str
    size: int
    url: str | None
    last_modified: date | None = None


def sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _http_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).date()
    except (TypeError, ValueError):
        return None


class DownloadError(RuntimeError):
    """Every attempt to download a file failed (a network problem, not a problem with the data)."""


def download(
    url: str,
    dest: Path,
    user_agent: str = DEFAULT_USER_AGENT,
    transport: httpx.BaseTransport | None = None,
    retries: int = 5,
    sleep: Callable[[float], None] = time.sleep,
) -> DownloadResult:
    """Download with an identifying User-Agent, retrying network errors. Streams to disk.

    Waits 5, 10, 20, 40 seconds between attempts (about a minute and a quarter). A runner whose
    network cannot reach the server (the 2026-11-18/19 ``Network is unreachable`` errors lasted
    minutes) is not helped by waiting longer: the workflow tests the connection first and starts
    the whole import again on a fresh runner. Raises ``DownloadError`` when every attempt fails.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with (
                httpx.Client(
                    headers={"User-Agent": user_agent},
                    timeout=httpx.Timeout(60.0, read=300.0),
                    follow_redirects=True,
                    transport=transport,
                ) as client,
                client.stream("GET", url) as response,
            ):
                response.raise_for_status()
                modified = _http_date(response.headers.get("Last-Modified"))
                with dest.open("wb") as fh:
                    for chunk in response.iter_bytes(1 << 20):
                        fh.write(chunk)
            digest, size = sha256_file(dest)
            log.info("downloaded", url=url, bytes=size, sha256=digest)
            return DownloadResult(dest, digest, size, url, modified)
        except (httpx.HTTPError, OSError) as exc:
            last_error = exc
            log.warning(
                "download_failed",
                url=url,
                attempt=attempt,
                error=type(exc).__name__,
                reason=str(exc)[:200],  # the cause (refused, reset, timed out, TLS), no secrets
            )
            if attempt < retries:
                sleep(5.0 * 2 ** (attempt - 1))
    raise DownloadError(f"could not download {url}: {type(last_error).__name__}")


def filter_extract(source: Path, dest: Path) -> None:
    """Keep only the objects the import needs (and what they reference)."""
    run_tool(["osmium", "tags-filter", str(source), *TAGS_FILTER, "-o", str(dest), "--overwrite"])


def snapshot_date(path: Path) -> date | None:
    """The replication timestamp in the file header, or ``None`` if the file has none."""
    out = run_tool(
        ["osmium", "fileinfo", "-g", "header.option.osmosis_replication_timestamp", str(path)]
    ).strip()
    if not out:
        return None
    try:
        return datetime.fromisoformat(out.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def build_staging(staging_url: str, filtered: Path, cache_mb: int = 1000) -> None:
    """Recreate schema ``staging`` in the temporary PostGIS and load the filtered extract."""
    with psycopg.connect(libpq_url(staging_url), autocommit=True) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS postgis")
        conn.execute("DROP SCHEMA IF EXISTS staging CASCADE")
        conn.execute("CREATE SCHEMA staging")
    run_tool(
        [
            "osm2pgsql",
            "--output=flex",
            f"--style={LUA_STYLE}",
            "--slim",
            "--drop",
            f"--cache={cache_mb}",
            str(filtered),
        ],
        env=pg_env(staging_url),
    )


@dataclass(frozen=True)
class Candidate:
    osm_type: str  # N, W or R
    osm_id: int
    tags: dict[str, str]
    lon: float | None
    lat: float | None


def iter_candidates(conn: psycopg.Connection[Any]) -> Iterator[Candidate]:
    """Every candidate object with a representative point, in a fixed order."""
    query = """
        SELECT osm_type, osm_id, tags, ST_X(p), ST_Y(p)
        FROM (
            SELECT osm_type, osm_id, tags,
                   CASE
                     WHEN geom IS NULL OR ST_IsEmpty(geom) THEN NULL
                     WHEN GeometryType(geom) = 'POINT' THEN geom
                     ELSE ST_PointOnSurface(ST_MakeValid(geom))
                   END AS p
            FROM staging.osm_object
        ) s
        ORDER BY osm_type, osm_id
    """
    with conn.cursor(name="candidates") as cur:
        cur.itersize = 5000
        cur.execute(query)
        for osm_type, osm_id, tags, lon, lat in cur:
            yield Candidate(osm_type, osm_id, tags, lon, lat)


@dataclass(frozen=True)
class Boundary:
    osm_id: int
    tags: dict[str, str]
    ewkb_hex: str


def iter_boundaries(conn: psycopg.Connection[Any]) -> Iterator[Boundary]:
    query = f"""
        SELECT osm_id, tags, encode(ST_AsEWKB(g), 'hex')
        FROM (
            SELECT osm_id, tags,
                   ST_Multi(ST_CollectionExtract(
                       ST_MakeValid(ST_SimplifyPreserveTopology(geom, {BOUNDARY_TOLERANCE_DEG})),
                       3)) AS g
            FROM staging.osm_boundary
        ) s
        WHERE g IS NOT NULL AND NOT ST_IsEmpty(g)
        ORDER BY osm_id
    """
    with conn.cursor() as cur:
        cur.execute(query)
        for osm_id, tags, ewkb in cur.fetchall():
            yield Boundary(osm_id, tags, ewkb)
