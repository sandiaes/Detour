"""The grid index used to keep restaurants near attractions or towns."""

import math
import random

import pytest

from detour_api.importer.proximity import ProximityIndex, haversine_m


def test_haversine_matches_known_distances() -> None:
    assert haversine_m(48.0, 16.0, 48.0, 16.0) == 0
    # one degree of latitude is about 111.2 km
    assert haversine_m(48.0, 16.0, 49.0, 16.0) == pytest.approx(111_195, rel=1e-3)
    # a degree of longitude at 48 degrees is shorter by cos(48 degrees)
    assert haversine_m(48.0, 16.0, 48.0, 17.0) == pytest.approx(
        111_195 * math.cos(math.radians(48)), rel=2e-3
    )


def test_near_is_inclusive_at_the_radius_and_false_beyond() -> None:
    index = ProximityIndex([(48.0, 16.0)], 500)
    assert index.near(48.0, 16.0)
    # about 400 m north, 600 m north
    assert index.near(48.0 + 400 / 111_195, 16.0)
    assert not index.near(48.0 + 600 / 111_195, 16.0)
    exact = 48.0 + 500 / 111_195
    d = haversine_m(48.0, 16.0, exact, 16.0)
    assert index.near(exact - (d - 500) / 111_195 - 1e-9, 16.0)


def test_cells_do_not_hide_points_across_boundaries() -> None:
    # the same answer as a brute-force check, for random points around cell borders
    rng = random.Random(7)  # noqa: S311 - a test, not security
    anchors = [(46 + rng.random(), 10 + rng.random()) for _ in range(300)]
    index = ProximityIndex(anchors, 500)
    for _ in range(2000):
        lat, lon = 46 + rng.random(), 10 + rng.random()
        brute = any(haversine_m(lat, lon, a, b) <= 500 for a, b in anchors)
        assert index.near(lat, lon) == brute


def test_it_works_at_high_latitudes_and_with_no_anchors() -> None:
    far_north = ProximityIndex([(64.0, 20.0)], 500)
    assert far_north.near(64.0, 20.0 + 0.009)  # about 440 m east at 64 degrees
    assert not far_north.near(64.0, 20.0 + 0.02)
    assert not ProximityIndex([], 500).near(0.0, 0.0)


def test_the_answer_does_not_depend_on_input_order() -> None:
    pts = [(48.1, 16.1), (48.2, 16.2), (48.3, 16.3)]
    a, b = ProximityIndex(pts, 500), ProximityIndex(list(reversed(pts)), 500)
    assert a.count == b.count == 3
    assert a.near(48.2, 16.2) and b.near(48.2, 16.2)
