"""Shared helpers for the planner tests: the synthetic candidate fixtures and a request."""

import json
from datetime import date
from functools import cache
from pathlib import Path

from detour_api.planner.types import Candidate, PlanRequest

PLANNER_FIXTURES = Path(__file__).parent / "fixtures" / "planner"
GOLDEN = PLANNER_FIXTURES / "golden"


@cache
def _load(name: str) -> tuple[tuple[float, float], tuple[Candidate, ...]]:
    data = json.loads((PLANNER_FIXTURES / f"{name}.json").read_text())
    assert data["synthetic"] is True  # invented test data, never real places
    centre = (data["centre"]["lat"], data["centre"]["lon"])
    return centre, tuple(Candidate(**c) for c in data["candidates"])


def candidates(name: str) -> list[Candidate]:
    return list(_load(name)[1])


def request(
    name: str, days: int, start: date | None = None, data_version: str | None = "run-fixture"
) -> PlanRequest:
    (lat, lon), _ = _load(name)
    return PlanRequest(
        destination_name="Synthetic City",
        lat=lat,
        lon=lon,
        days=days,
        start_date=start,
        currency_code="EUR",
        data_version=data_version,
    )


def insert_synthetic_sights(database_url: str, region_id: str = "test-region") -> int:
    """Load the synthetic city fixture (invented places centred on Testburg) into a database whose
    fixture region is imported, so the region is big enough for two plans. Returns the count."""
    import psycopg

    rows = candidates("city-large")
    with psycopg.connect(database_url, autocommit=True) as conn:
        [(run,)] = conn.execute(
            "SELECT current_import_run_id FROM geo.region WHERE id = %s", (region_id,)
        ).fetchall()
        for c in rows:
            conn.execute(
                "INSERT INTO geo.place (id, region_id, kind, category, name, name_norm, geom,"
                " first_import_run_id, last_changed_import_run_id)"
                " VALUES (%s, %s, 'attraction', %s, %s, lower(%s),"
                " ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, %s)",
                (c.place_id, region_id, c.category, c.name, c.name, c.lon, c.lat, run, run),
            )
            conn.execute(
                "INSERT INTO geo.place_signal (place_id, osm_signals, score) VALUES (%s, %s, 0)",
                (c.place_id, json.dumps(c.signals)),
            )
    return len(rows)
