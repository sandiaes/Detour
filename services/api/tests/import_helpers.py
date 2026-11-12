"""Shared helpers for tests that run the real import pipeline on the synthetic fixtures."""

import os
import shutil
from pathlib import Path
from typing import Any

import psycopg
import pytest
from alembic import command
from alembic.config import Config

from detour_api.importer.cli import run_region_import
from detour_api.importer.gazetteer import read_cities_zip, run_gazetteer_import  # noqa: F401
from detour_api.importer.regions import RegionDef
from tests.conftest import API_ROOT

FIXTURES = Path(__file__).parent / "fixtures"
TEST_REGION = RegionDef("test-region", "Test region", "europe/test", ("AT",))


def require_tools() -> None:
    missing = [t for t in ("osm2pgsql", "osmium") if shutil.which(t) is None]
    if missing:
        if os.environ.get("DETOUR_REQUIRE_DB_TESTS") == "1":
            pytest.fail(f"CI must install: {missing}")
        pytest.skip(f"needs {missing}")


def migrate(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DETOUR_DATABASE_URL", url)
    command.upgrade(Config(str(API_ROOT / "alembic.ini")), "head")


def import_fixture_region(
    target_url: str,
    staging_url: str,
    work_dir: Path,
    pbf: Path | None = None,
    region: RegionDef = TEST_REGION,
) -> dict[str, Any]:
    return run_region_import(
        region,
        target_url=target_url,
        staging_url=staging_url,
        work_dir=work_dir,
        pbf=pbf or FIXTURES / "region-sample.osm",
    )


def import_fixture_gazetteer(target_url: str, countries: list[str]) -> dict[str, int]:

    return run_gazetteer_import(
        target_url=target_url,
        countries_text=(FIXTURES / "countryInfo.txt").read_text(encoding="utf-8"),
        admin1_text=(FIXTURES / "admin1CodesASCII.txt").read_text(encoding="utf-8"),
        admin2_text=(FIXTURES / "admin2Codes.txt").read_text(encoding="utf-8"),
        city_lines=(FIXTURES / "cities-sample.txt").read_text(encoding="utf-8").splitlines(),
        country_codes=countries,
        geonames_date=None,
    )


def canonical_geo_dump(url: str, region_id: str) -> dict[str, list[tuple[Any, ...]]]:
    """Everything the import wrote for a region, without run identities and timestamps."""
    queries = {
        "place": (
            "SELECT id, kind, category, name, name_norm, names_i18n, ST_AsText(geom), address,"
            " city_id, default_visit_minutes, is_active FROM geo.place WHERE region_id = %s"
            " ORDER BY id"
        ),
        "place_source": (
            "SELECT ps.place_id, ps.source, ps.source_ref, ps.licence_code, ps.tags"
            " FROM geo.place_source ps JOIN geo.place p ON p.id = ps.place_id"
            " WHERE p.region_id = %s ORDER BY 1, 2, 3"
        ),
        "restaurant_profile": (
            "SELECT rp.* FROM geo.restaurant_profile rp JOIN geo.place p ON p.id = rp.place_id"
            " WHERE p.region_id = %s ORDER BY rp.place_id"
        ),
        "place_signal": (
            "SELECT s.* FROM geo.place_signal s JOIN geo.place p ON p.id = s.place_id"
            " WHERE p.region_id = %s ORDER BY s.place_id"
        ),
        "admin_area": (
            "SELECT id, name, name_norm, level, country_iso2, ST_AsText(geom), source_ref,"
            " licence_code, is_active FROM geo.admin_area WHERE region_id = %s ORDER BY id"
        ),
        "region": (
            "SELECT id, name, country_codes, ST_AsText(geom), status FROM geo.region WHERE id = %s"
        ),
    }
    with psycopg.connect(url) as conn:
        return {
            name: [tuple(row) for row in conn.execute(sql, (region_id,)).fetchall()]
            for name, sql in queries.items()
        }


def strip_run_details(report: dict[str, Any]) -> dict[str, Any]:
    """The report without what legitimately differs between two runs."""
    volatile = (
        "run",
        "geo_size_bytes",
        "geo_size_at_commit_bytes",
        "geo_size_after_vacuum_bytes",
        "gates",
    )
    clean = {k: v for k, v in report.items() if k not in volatile}
    clean["gates"] = [
        {
            **g,
            "checks": [c for c in g["checks"] if not c["label"].startswith("geo schema size")],
        }
        for g in report["gates"]
    ]
    return clean
