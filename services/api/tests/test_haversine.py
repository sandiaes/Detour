"""The great-circle distance the same-sight rule uses."""

import math

import pytest

from detour_api.planner.dedupe import haversine_m


def test_haversine_matches_known_distances() -> None:
    assert haversine_m(48.0, 16.0, 48.0, 16.0) == 0
    # one degree of latitude is about 111.2 km
    assert haversine_m(48.0, 16.0, 49.0, 16.0) == pytest.approx(111_195, rel=1e-3)
    # a degree of longitude at 48 degrees is shorter by cos(48 degrees)
    assert haversine_m(48.0, 16.0, 48.0, 17.0) == pytest.approx(
        111_195 * math.cos(math.radians(48)), rel=2e-3
    )
