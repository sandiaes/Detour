"""Parsers, request planner and estimator: contract tests against the documented-format
fixtures. No network, no database."""

import json

import pytest

from detour_api.adapters.valhalla import (
    MATRIX_MAX_CELLS,
    MATRIX_MAX_METERS,
    MatrixCell,
    decode_polyline6,
    parse_matrix,
    parse_route,
)
from detour_api.travel import chunking
from detour_api.travel.estimate import RULES, estimate, estimated
from detour_api.travel.types import Coord, distance_m
from tests.valhalla_stub import FIXTURES, ROUTE_FIXTURE, coord, street

MATRIX_FIXTURE = json.loads((FIXTURES / "matrix-1x4-documented.json").read_text())


# -- response parsing -----------------------------------------------------------------------


def test_matrix_fixture_is_read_with_its_null_cell() -> None:
    cells, algorithm = parse_matrix(MATRIX_FIXTURE, 4)
    assert algorithm == "timedistancematrix"
    assert cells == [
        MatrixCell(0, 0),
        MatrixCell(523, 662),  # the pair the owner measured: 0.662 km, 523 s
        MatrixCell(None, None),  # a null cell is "no routed time", never a number
        MatrixCell(840, 1063),
    ]


@pytest.mark.parametrize(
    "item",
    [
        None,
        {"distance": None, "time": None},
        {"time": 5},
        {"distance": 1.0},
        {"distance": -1, "time": 3},
    ],
)
def test_every_null_variant_is_a_null_cell(item: object) -> None:
    payload = {"sources_to_targets": [[item]], "units": "kilometers"}
    assert parse_matrix(payload, 1)[0] == [MatrixCell(None, None)]


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"sources_to_targets": []},
        {"sources_to_targets": [[{"time": 1, "distance": 1.0}], [{"time": 1, "distance": 1.0}]]},
        {"sources_to_targets": [[{"time": 1, "distance": 1.0}]], "units": "miles"},
        {"sources_to_targets": [["x"]]},
        {"sources_to_targets": [[{"time": 1, "distance": 1.0, "to_index": 3}]]},
        {"sources_to_targets": [[{"time": 1, "distance": 1.0, "from_index": 2}]]},
    ],
)
def test_a_structure_that_is_not_what_was_asked_for_is_refused(payload: object) -> None:
    with pytest.raises(ValueError):
        parse_matrix(payload, 1)


def test_wrong_number_of_targets_is_refused() -> None:
    with pytest.raises(ValueError, match="wrong number"):
        parse_matrix(MATRIX_FIXTURE, 3)


def test_route_fixture_gives_time_length_and_geometry() -> None:
    seconds, meters, points = parse_route(ROUTE_FIXTURE, with_geometry=True)
    assert (seconds, meters) == (11505, 282885)  # Florence to Rome, as the owner measured
    assert list(points[0]) == pytest.approx([43.7696, 11.2558])
    assert list(points[-1]) == pytest.approx([41.9028, 12.4964])
    assert parse_route(ROUTE_FIXTURE, with_geometry=False)[2] == []


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"trip": {}},
        {"trip": {"summary": {"time": 1}}},
        {"trip": {"units": "miles", "summary": {"time": 1, "length": 1}}},
    ],
)
def test_unreadable_route_is_refused(payload: object) -> None:
    with pytest.raises(ValueError):
        parse_route(payload, with_geometry=False)


def test_geometry_without_a_shape_is_refused() -> None:
    payload = {"trip": {"summary": {"time": 1, "length": 1}, "legs": [{}]}}
    with pytest.raises(ValueError, match="no shape"):
        parse_route(payload, with_geometry=True)


def test_polyline_decoder_against_the_published_example() -> None:
    # The example string from Google's polyline documentation encodes (38.5, -120.2),
    # (40.7, -120.95), (43.252, -126.453) at five decimals. Read at six decimals every value is
    # a tenth of that, which is an independent check of the decoder's arithmetic.
    points = decode_polyline6("_p~iF~ps|U_ulLnnqC_mqNvxq`@")
    flat = [v for point in points for v in point]
    assert flat == pytest.approx([3.85, -12.02, 4.07, -12.095, 4.3252, -12.6453])


def test_truncated_polyline_is_refused() -> None:
    with pytest.raises(ValueError, match="truncated"):
        decode_polyline6("_p~iF~ps|U_")


# -- request planning -----------------------------------------------------------------------


def test_cells_are_one_source_with_at_most_100_targets() -> None:
    pts = street(251)  # 250 targets for the first source
    source = pts[0]
    matrices, routes = chunking.plan([(source, t) for t in pts[1:]])
    assert routes == []
    assert [len(m.targets) for m in matrices] == [100, 100, 50]
    assert all(m.source == source for m in matrices)
    assert all(len(m.targets) <= MATRIX_MAX_CELLS for m in matrices)


def test_dense_matrix_request_count() -> None:
    pts = street(12)
    matrices, routes = chunking.plan([(a, b) for a in pts for b in pts if a != b])
    assert routes == [] and len(matrices) == 12  # one request per source: 11 targets each
    assert {len(m.targets) for m in matrices} == {11}


def test_far_cells_are_single_route_requests_never_in_a_matrix() -> None:
    florence, rome, milan = coord(43.7696, 11.2558), coord(41.9028, 12.4964), coord(45.4642, 9.19)
    near = street(2)
    cells = [(florence, rome), (rome, milan), (near[0], near[1])]
    matrices, routes = chunking.plan(cells)
    assert [(r.origin, r.destination) for r in routes] == sorted([(florence, rome), (rome, milan)])
    assert len(matrices) == 1 and matrices[0].targets == (near[1],)
    for m in matrices:
        assert all(distance_m(m.source, t) <= MATRIX_MAX_METERS for t in m.targets)


def test_the_matrix_distance_limit_is_150_km_with_a_margin() -> None:
    a = coord(47.0, 11.0)
    just_inside = coord(47.0 + 148.0 / 111.19, 11.0)
    just_outside = coord(47.0 + 150.5 / 111.19, 11.0)
    assert chunking.is_matrix_cell(a, just_inside)
    assert not chunking.is_matrix_cell(a, just_outside)


def test_the_plan_is_independent_of_input_order_and_duplicates() -> None:
    pts = [*street(6), coord(41.9028, 12.4964)]
    cells = [(a, b) for a in pts for b in pts if a != b]
    forward = chunking.plan(cells)
    backward = chunking.plan(list(reversed(cells)) + cells)
    assert forward == backward


def test_identical_points_make_no_request() -> None:
    p = street(1)[0]
    assert chunking.plan([(p, p)]) == ([], [])


# -- coordinates and estimates --------------------------------------------------------------


def test_coordinates_are_rounded_to_a_fifth_decimal() -> None:
    c = Coord.from_degrees(43.762449, 11.229851)
    assert (c.lat_e5, c.lon_e5) == (4376245, 1122985)
    assert (c.lat, c.lon) == (43.76245, 11.22985)
    assert Coord.from_degrees(43.762449, 11.2298512) == Coord.from_degrees(43.762451, 11.2298488)


@pytest.mark.parametrize("lat,lon", [(91, 0), (0, 181), (float("nan"), 0), (0, float("inf"))])
def test_bad_coordinates_are_refused(lat: float, lon: float) -> None:
    with pytest.raises(ValueError):
        Coord.from_degrees(lat, lon)


def test_estimate_is_straight_line_times_a_factor_and_labelled() -> None:
    a, b = coord(43.7624, 11.2298), coord(43.7714, 11.2298)  # about 1 km
    straight = distance_m(a, b)
    result = estimated(a, b, "walk", "adapter_disabled")
    assert result.confidence == "estimated" and result.source == "estimate"
    assert result.reason == "adapter_disabled"
    assert result.meters == round(straight * RULES["walk"].detour_factor)
    assert result.seconds == round(result.meters / RULES["walk"].near_speed)


def test_estimate_of_two_identical_points_is_zero_and_still_labelled() -> None:
    a = coord(43.7624, 11.2298)
    assert estimate(a, a, "walk") == (0, 0)
    assert estimated(a, a, "drive", "same_point").confidence == "estimated"


def test_driving_estimate_uses_a_faster_speed_beyond_the_city_tier() -> None:
    florence, rome = coord(43.7696, 11.2558), coord(41.9028, 12.4964)
    seconds, meters = estimate(florence, rome, "drive")
    flat_urban = meters / RULES["drive"].near_speed
    assert seconds < flat_urban  # not the whole way at city speed
    assert estimate(rome, florence, "drive") == (seconds, meters)  # symmetric
