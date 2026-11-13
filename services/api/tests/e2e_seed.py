"""Builds the database that the Android end-to-end test runs against.

It is the same fixture the API tests use: the real migrations, the real gazetteer and region
import commands run on the small invented extract (`tests/fixtures/region-sample.osm`), plus the
planner's invented city fixture so that Testburg can be planned. Nothing here is real map data,
and nothing calls a network service. The fixture region is too small to pass the ADR 009 gates, so
it is marked available by hand, exactly as the API tests do.

    DETOUR_DATABASE_URL=postgresql://... DETOUR_STAGING_DATABASE_URL=postgresql://... \\
        python -m tests.e2e_seed

Both databases must exist, have PostGIS available, and be empty. `osm2pgsql` and `osmium` must be
installed. Run it from `services/api`.
"""

import os
import sys
import tempfile
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config

from tests.import_helpers import (
    TEST_REGION,
    import_fixture_gazetteer,
    import_fixture_region,
    require_tools,
)
from tests.planner_helpers import insert_synthetic_sights

API_ROOT = Path(__file__).resolve().parents[1]


def seed(target_url: str, staging_url: str) -> int:
    """Returns the number of synthetic sights added."""
    require_tools()
    os.environ["DETOUR_DATABASE_URL"] = target_url
    command.upgrade(Config(str(API_ROOT / "alembic.ini")), "head")
    import_fixture_gazetteer(target_url, ["AT", "JP"])
    with tempfile.TemporaryDirectory() as work:
        import_fixture_region(target_url, staging_url, Path(work))
    added = insert_synthetic_sights(target_url, TEST_REGION.id)
    with psycopg.connect(target_url, autocommit=True) as conn:
        conn.execute("UPDATE geo.region SET status = 'available' WHERE id = %s", (TEST_REGION.id,))
    return added


def main() -> int:
    target = os.environ.get("DETOUR_DATABASE_URL")
    staging = os.environ.get("DETOUR_STAGING_DATABASE_URL")
    if not target or not staging:
        print("DETOUR_DATABASE_URL and DETOUR_STAGING_DATABASE_URL are required.", file=sys.stderr)
        return 2
    added = seed(target, staging)
    print(f"Seeded the fixture region (Testburg, city ref 900101) with {added} synthetic sights.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
