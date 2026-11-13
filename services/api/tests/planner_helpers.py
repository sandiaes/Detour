"""Shared helpers for the planner tests: the synthetic fixtures (sights, places to eat, the
towns of an invented area) and a request."""

import json
from dataclasses import dataclass
from datetime import date
from functools import cache
from pathlib import Path

from detour_api.planner.types import BaseCity, Candidate, PlanRequest, Restaurant

PLANNER_FIXTURES = Path(__file__).parent / "fixtures" / "planner"
GOLDEN = PLANNER_FIXTURES / "golden"
# The gazetteer id given to the synthetic city in requests (the fixture has no real city).
SYNTHETIC_CITY_ID = 900101


@dataclass(frozen=True)
class _Fixture:
    centre: tuple[float, float]
    candidates: tuple[Candidate, ...]
    restaurants: tuple[Restaurant, ...]
    towns: tuple[BaseCity, ...]


@cache
def _load(name: str) -> _Fixture:
    data = json.loads((PLANNER_FIXTURES / f"{name}.json").read_text())
    assert data["synthetic"] is True  # invented test data, never real places
    return _Fixture(
        centre=(data["centre"]["lat"], data["centre"]["lon"]),
        candidates=tuple(Candidate(**c) for c in data["candidates"]),
        restaurants=tuple(
            Restaurant(
                place_id=r["place_id"],
                name=r["name"],
                venue_type=r["venue_type"],
                lat=r["lat"],
                lon=r["lon"],
                meal_types=tuple(r["meal_types"]),
                cuisines=None if r["cuisines"] is None else tuple(r["cuisines"]),
            )
            for r in data.get("restaurants", [])
        ),
        towns=tuple(BaseCity(**t) for t in data.get("towns", [])),
    )


def candidates(name: str) -> list[Candidate]:
    return list(_load(name).candidates)


def restaurants(name: str) -> list[Restaurant]:
    return list(_load(name).restaurants)


def towns(name: str) -> list[BaseCity]:
    return list(_load(name).towns)


def request(
    name: str, days: int, start: date | None = None, data_version: str | None = "run-fixture"
) -> PlanRequest:
    fixture = _load(name)
    lat, lon = fixture.centre
    if fixture.towns:
        return PlanRequest(
            destination_name="Synthetic Area",
            lat=lat,
            lon=lon,
            days=days,
            start_date=start,
            data_version=data_version,
            kind="area",
            base_cities=fixture.towns,
        )
    return PlanRequest(
        destination_name="Synthetic City",
        lat=lat,
        lon=lon,
        days=days,
        start_date=start,
        data_version=data_version,
        kind="city",
        base_cities=(BaseCity(SYNTHETIC_CITY_ID, "Synthetic City", lat, lon),),
    )


def insert_synthetic_sights(database_url: str, region_id: str = "test-region") -> int:
    """Load the synthetic city fixture (invented sights and places to eat centred on Testburg)
    into a database whose fixture region is imported, so the region is big enough for two plans
    with meals. Returns the number of sights."""
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
        for r in restaurants("city-large"):
            conn.execute(
                "INSERT INTO geo.place (id, region_id, kind, category, name, name_norm, geom,"
                " first_import_run_id, last_changed_import_run_id)"
                " VALUES (%s, %s, 'restaurant', %s, %s, lower(%s),"
                " ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, %s)",
                (r.place_id, region_id, r.venue_type, r.name, r.name, r.lon, r.lat, run, run),
            )
            conn.execute(
                "INSERT INTO geo.restaurant_profile (place_id, cuisines, venue_type, meal_types)"
                " VALUES (%s, %s, %s, %s)",
                (
                    r.place_id,
                    None if r.cuisines is None else list(r.cuisines),
                    r.venue_type,
                    list(r.meal_types),
                ),
            )
    return len(rows)
