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
