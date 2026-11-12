"""The routing adapter and the travel-time service against a real database and a stub server.

Never the live server: the transport is ``ValhallaStub``, and in the ``test`` environment the
adapter stays off unless a transport is injected.
"""

from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from sqlalchemy import Engine, text

from detour_api.adapters.valhalla import MATRIX_SHAPE, PROVIDER, ROUTE_SHAPE, ValhallaClient
from detour_api.db import make_engine
from detour_api.settings import Settings
from detour_api.travel.service import TravelTimeService
from tests.conftest import TEST_SECRET, _scratch_database
from tests.import_helpers import migrate
from tests.valhalla_stub import FakeClock, ValhallaStub, coord, street

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def database_url() -> Iterator[str]:
    with _scratch_database() as url, pytest.MonkeyPatch.context() as mp:
        migrate(url, mp)
        yield url


@pytest.fixture
def engine(database_url: str) -> Iterator[Engine]:
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute("TRUNCATE geo.travel_time")
        conn.execute("TRUNCATE app.provider_usage")
    eng = make_engine(database_url)
    yield eng
    eng.dispose()


class Env:
    def __init__(self, engine: Engine, **overrides: Any) -> None:
        self.engine = engine
        self.stub = ValhallaStub()
        self.clock = FakeClock()
        self.settings = Settings(environment="test", token_secret=TEST_SECRET, **overrides)
        self.client = ValhallaClient(
            self.settings,
            engine,
            self.stub.transport,
            now=self.clock.now,
            sleep=self.clock.sleep,
        )
        self.service = TravelTimeService(self.settings, engine, self.client, now=self.clock.now)

    def rows(self) -> list[tuple[Any, ...]]:
        with self.engine.begin() as conn:
            return [
                tuple(r)
                for r in conn.execute(
                    text(
                        "SELECT from_lat, to_lat, mode, request_shape, provider, confidence,"
                        " seconds, meters, algorithm, response_date, retry_after"
                        " FROM geo.travel_time ORDER BY from_lat, to_lat, mode"
                    )
                )
            ]

    def calls_today(self) -> int:
        with self.engine.begin() as conn:
            row = conn.execute(text("SELECT COALESCE(sum(calls), 0) FROM app.provider_usage"))
            return int(row.scalar_one())


@pytest.fixture
def env(engine: Engine) -> Env:
    return Env(engine)


# -- the adapter's request ---------------------------------------------------------------------


def test_request_is_one_fixed_shape_with_identifying_headers(env: Env) -> None:
    pts = street(4)
    env.service.cells([(pts[0], t) for t in pts[1:]], "walk")
    (request,) = env.stub.requests
    assert request.method == "POST" and request.url.path == "/sources_to_targets"
    assert request.headers["user-agent"].startswith("Detour-backend/")
    assert request.headers["x-client-id"] == "detour-travel-planner"
    body = env.stub.bodies[0]
    assert list(body) == ["sources", "targets", "costing"]  # exactly these, nothing else
    assert body["costing"] == "pedestrian"
    assert body["sources"] == [{"lat": pts[0].lat, "lon": pts[0].lon}]
    assert [t["lat"] for t in body["targets"]] == [p.lat for p in pts[1:]]


def test_driving_uses_the_auto_costing(env: Env) -> None:
    pts = street(2)
    env.service.cells([(pts[0], pts[1])], "drive")
    assert env.stub.bodies[0]["costing"] == "auto"


def test_the_adapter_is_off_in_tests_unless_a_transport_is_injected(engine: Engine) -> None:
    settings = Settings(environment="test", token_secret=TEST_SECRET)
    assert ValhallaClient(settings, engine).enabled is False
    assert ValhallaClient(settings, engine, ValhallaStub().transport).enabled is True
    assert ValhallaClient(settings, None, ValhallaStub().transport).enabled is False
    off = Settings(environment="test", token_secret=TEST_SECRET, routing_enabled=False)
    assert ValhallaClient(off, engine, ValhallaStub().transport).enabled is False


def test_configuration_cannot_exceed_the_adr_004_rates() -> None:
    with pytest.raises(ValueError):
        Settings(routing_rate_per_second=2.0)
    with pytest.raises(ValueError):
        Settings(routing_burst=11)


# -- cache -------------------------------------------------------------------------------------


def test_a_miss_calls_the_adapter_and_a_repeat_is_a_cache_hit(env: Env) -> None:
    pts = street(5)
    cells = [(pts[0], t) for t in pts[1:]]
    first = env.service.cells(cells, "walk")
    assert len(env.stub.requests) == 1
    assert first.stats.provider_requests == 1 and first.stats.cache_hits == 0
    assert {t.confidence for t in first.times.values()} == {"routed"}
    assert {t.source for t in first.times.values()} == {"provider"}

    second = env.service.cells(cells, "walk")
    assert len(env.stub.requests) == 1  # no new call at all
    assert second.stats.cache_hits == 4 and second.stats.provider_requests == 0
    assert {t.source for t in second.times.values()} == {"cache"}
    for cell in cells:  # same numbers from the cache as from the provider
        assert (second.times[cell].seconds, second.times[cell].meters) == (
            first.times[cell].seconds,
            first.times[cell].meters,
        )


def test_only_the_misses_are_requested(env: Env) -> None:
    pts = street(4)
    env.service.cells([(pts[0], pts[1])], "walk")
    env.stub.requests.clear()
    env.service.cells([(pts[0], pts[1]), (pts[0], pts[2]), (pts[0], pts[3])], "walk")
    assert [len(b["targets"]) for b in env.stub.bodies] == [2]
    assert [t["lat"] for t in env.stub.bodies[0]["targets"]] == [pts[2].lat, pts[3].lat]


def test_every_cell_is_stored_with_provider_date_shape_and_algorithm(env: Env) -> None:
    pts = street(3)
    env.service.cells([(pts[0], pts[1]), (pts[0], pts[2])], "walk")
    rows = env.rows()
    assert len(rows) == 2
    for row in rows:
        _, _, mode, shape, provider, confidence, seconds, meters, algorithm, date, retry = row
        assert (mode, shape, provider, confidence) == ("walk", MATRIX_SHAPE, PROVIDER, "routed")
        assert seconds > 0 and meters > 0 and algorithm == "timedistancematrix"
        assert date.year == 2026 and date.month == 11 and date.day == 11  # the Date header
        assert retry is None


def test_walk_and_drive_are_cached_separately(env: Env) -> None:
    pts = street(2)
    env.service.cells([(pts[0], pts[1])], "walk")
    env.service.cells([(pts[0], pts[1])], "drive")
    assert len(env.stub.requests) == 2
    assert [r[2] for r in env.rows()] == ["drive", "walk"]


def test_a_row_of_another_request_shape_is_not_used(env: Env, engine: Engine) -> None:
    pts = street(2)
    env.service.cells([(pts[0], pts[1])], "walk")
    with engine.begin() as conn:
        conn.execute(text("UPDATE geo.travel_time SET request_shape = 'matrix-v0'"))
    env.service.cells([(pts[0], pts[1])], "walk")
    assert len(env.stub.requests) == 2  # the old-shape row did not count as a hit
    assert sorted(r[3] for r in env.rows()) == sorted([MATRIX_SHAPE, "matrix-v0"])


def test_a_dense_matrix_is_chunked_and_complete(env: Env) -> None:
    pts = street(30)
    result = env.service.matrix(pts, "walk")
    assert len(result.times) == 30 * 29
    assert all(len(b["targets"]) <= 100 for b in env.stub.bodies)
    assert len(env.stub.requests) == 30  # one source per request
    assert all(t.confidence == "routed" for t in result.times.values())
    again = env.service.matrix(pts, "walk")
    assert len(env.stub.requests) == 30 and again.stats.cache_hits == 30 * 29


def test_the_cache_never_grows_beyond_its_row_cap(engine: Engine) -> None:
    capped = Env(engine, routing_cache_max_rows=1000)
    pts = street(40)  # 1,560 cells
    capped.service.matrix(pts, "walk")
    assert len(capped.rows()) == 1000


# -- fallback ----------------------------------------------------------------------------------


def test_when_the_adapter_is_disabled_everything_is_a_labelled_estimate(engine: Engine) -> None:
    off = Env(engine, routing_enabled=False)
    pts = street(4)
    result = off.service.matrix(pts, "walk")
    assert off.stub.requests == []
    assert len(result.times) == 12
    for t in result.times.values():
        assert (t.confidence, t.source, t.reason) == ("estimated", "estimate", "adapter_disabled")
        assert t.seconds > 0 and t.meters > 0
    assert off.rows() == []  # an estimate says nothing about the provider: not stored


def test_without_a_database_it_estimates_and_calls_nothing() -> None:
    settings = Settings(environment="test", token_secret=TEST_SECRET)
    stub = ValhallaStub()
    client = ValhallaClient(settings, None, stub.transport)
    service = TravelTimeService(settings, None, client)
    pts = street(3)
    result = service.cells([(pts[0], pts[1])], "drive")
    assert stub.requests == []
    assert result.get(pts[0], pts[1]).reason == "adapter_disabled"


def test_use_provider_false_reads_the_cache_and_never_calls_out(env: Env) -> None:
    pts = street(3)
    env.service.cells([(pts[0], pts[1])], "walk")
    env.stub.requests.clear()
    result = env.service.cells([(pts[0], pts[1]), (pts[0], pts[2])], "walk", use_provider=False)
    assert env.stub.requests == []
    assert result.get(pts[0], pts[1]).source == "cache"
    assert result.get(pts[0], pts[2]).reason == "provider_not_asked"


@pytest.mark.parametrize("mode", ["429", "500", "timeout", "garbage", "wrong_shape", "error154"])
def test_a_failure_gives_estimates_and_opens_the_breaker(env: Env, mode: str) -> None:
    env.stub.mode = mode
    pts = street(5)
    cells = [(a, b) for a in pts[:3] for b in pts if a != b]
    result = env.service.cells(cells, "walk")
    assert len(env.stub.requests) == 1  # the first failure stops all further calls
    assert {t.reason for t in result.times.values()} == {"adapter_unavailable"}
    assert {t.confidence for t in result.times.values()} == {"estimated"}
    assert env.client.breaker.state == "open"
    assert env.rows() == []

    env.service.cells([(pts[3], pts[4])], "walk")
    assert len(env.stub.requests) == 1  # breaker open: no call, no matter how many plans


def test_after_a_429_the_breaker_stays_open_for_the_retry_after_then_probes_once(
    env: Env,
) -> None:
    env.stub.mode = "429"
    pts = street(3)
    env.service.cells([(pts[0], pts[1])], "walk")
    env.stub.mode = "ok"
    env.clock.advance(299)  # 429 pauses 300 s; Retry-After said 120
    env.service.cells([(pts[0], pts[1])], "walk")
    assert len(env.stub.requests) == 1
    env.clock.advance(2)
    result = env.service.cells([(pts[0], pts[1])], "walk")
    assert len(env.stub.requests) == 2 and result.get(pts[0], pts[1]).source == "provider"
    assert env.client.breaker.state == "closed"


def test_the_daily_budget_stops_calls_and_falls_back(engine: Engine) -> None:
    limited = Env(engine, routing_daily_budget=2)
    pts = street(6)
    result = limited.service.matrix(pts, "walk")
    assert len(limited.stub.requests) == 2 and limited.calls_today() == 2
    reasons = {t.reason for t in result.times.values() if t.confidence == "estimated"}
    assert reasons == {"budget_exhausted"}
    routed_sources = {a for (a, _), t in result.times.items() if t.confidence == "routed"}
    assert routed_sources == set(pts[:2])  # sorted order: deterministic which are reached
    limited.service.matrix(pts, "walk")  # the rest is still not called today
    assert len(limited.stub.requests) == 2


def test_the_rate_limit_makes_calls_wait_when_the_wait_fits(engine: Engine) -> None:
    env = Env(engine, routing_burst=2, routing_max_wait_seconds=1.0)
    result = env.service.matrix(street(5), "walk")
    assert len(env.stub.requests) == 5 and not any(
        t.confidence == "estimated" for t in result.times.values()
    )
    # two calls from the burst, then one second for each of the other three: 1 per second
    assert env.clock.slept == [pytest.approx(1.0)] * 3


def test_the_rate_limit_degrades_instead_of_queuing_when_the_wait_is_too_long(
    engine: Engine,
) -> None:
    env = Env(engine, routing_burst=2, routing_max_wait_seconds=0.5)
    result = env.service.matrix(street(5), "walk")
    assert len(env.stub.requests) == 2  # the burst; the third would have to wait a full second
    assert env.clock.slept == []
    assert {t.reason for t in result.times.values() if t.confidence == "estimated"} == {
        "rate_limited"
    }
    assert env.calls_today() == 2  # a call that was never made is not counted


def test_a_time_limit_estimates_the_cells_not_reached(env: Env) -> None:
    pts = street(5)

    class Ticking(FakeClock):
        def now(self) -> float:
            self.t += 1.0  # every look at the clock costs a second
            return self.t

    ticking = Ticking()
    service = TravelTimeService(env.settings, env.engine, env.client, now=ticking.now)
    result = service.matrix(pts, "walk", max_seconds=2.5)
    reasons = {t.reason for t in result.times.values() if t.confidence == "estimated"}
    assert reasons == {"time_limit"} and 0 < len(env.stub.requests) < 5


# -- null cells ---------------------------------------------------------------------------------


def test_a_null_cell_is_an_estimate_and_remembered_without_a_number(env: Env) -> None:
    pts = street(4)
    env.stub.null_targets = {(pts[2].lat, pts[2].lon)}
    cells = [(pts[0], pts[1]), (pts[0], pts[2]), (pts[0], pts[3])]
    result = env.service.cells(cells, "drive")
    unreachable = result.get(pts[0], pts[2])
    assert (unreachable.confidence, unreachable.reason) == ("estimated", "no_route")
    assert unreachable.seconds > 0  # the labelled estimate, not zero and not missing
    assert result.get(pts[0], pts[1]).confidence == "routed"

    stored = {r[1]: r for r in env.rows()}
    row = stored[pts[2].lat_e5]
    assert row[5] == "estimated" and row[6] is None and row[7] is None and row[10] is not None

    env.stub.requests.clear()
    again = env.service.cells(cells, "drive")
    assert env.stub.requests == []  # the null cell is not asked again at once
    assert again.get(pts[0], pts[2]).reason == "no_route"
    assert again.get(pts[0], pts[2]).seconds == unreachable.seconds


def test_a_no_route_cell_is_asked_again_after_its_retry_period(env: Env, engine: Engine) -> None:
    pts = street(2)
    env.stub.null_targets = {(pts[1].lat, pts[1].lon)}
    env.service.cells([(pts[0], pts[1])], "drive")
    with engine.begin() as conn:
        conn.execute(text("UPDATE geo.travel_time SET retry_after = now() - interval '1 day'"))
    env.stub.null_targets = set()
    env.stub.requests.clear()
    result = env.service.cells([(pts[0], pts[1])], "drive")
    assert len(env.stub.requests) == 1
    assert result.get(pts[0], pts[1]).confidence == "routed"
    assert [r[5] for r in env.rows()] == ["routed"]


def test_zero_seconds_for_distinct_far_points_is_not_a_route(env: Env) -> None:
    pts = street(3)
    env.stub.zero_targets = {(pts[2].lat, pts[2].lon)}
    result = env.service.cells([(pts[0], pts[1]), (pts[0], pts[2])], "walk")
    assert result.get(pts[0], pts[2]).reason == "no_route"
    assert result.get(pts[0], pts[1]).confidence == "routed"


def test_identical_points_are_estimated_as_zero_without_a_request(env: Env) -> None:
    p = street(1)[0]
    result = env.service.cells([(p, p)], "walk")
    t = result.get(p, p)
    assert (t.seconds, t.meters, t.confidence, t.reason) == (0, 0, "estimated", "same_point")
    assert env.stub.requests == []


# -- long legs and geometry ---------------------------------------------------------------------


def test_legs_between_distant_cities_are_one_route_request_each(env: Env) -> None:
    florence, rome, milan = coord(43.7696, 11.2558), coord(41.9028, 12.4964), coord(45.4642, 9.19)
    result = env.service.cells([(florence, rome), (rome, milan)], "drive")
    assert env.stub.paths() == ["/route", "/route"]
    # requests go out in sorted order (Rome sorts before Florence), so the plan is deterministic
    assert [b["locations"][0] for b in env.stub.bodies] == [
        {"lat": rome.lat, "lon": rome.lon},
        {"lat": florence.lat, "lon": florence.lon},
    ]
    assert {t.confidence for t in result.times.values()} == {"routed"}
    assert result.get(florence, rome).seconds == 11505  # the stub serves the owner's figures
    assert {r[3] for r in env.rows()} == {ROUTE_SHAPE} and len(env.rows()) == 2

    env.service.cells([(florence, rome), (rome, milan)], "drive")
    assert len(env.stub.requests) == 2  # cached


def test_the_route_request_is_plain_unless_slim_requests_are_switched_on(
    env: Env, engine: Engine
) -> None:
    a, b = coord(43.7696, 11.2558), coord(41.9028, 12.4964)
    env.service.cells([(a, b)], "drive")
    assert set(env.stub.bodies[0]) == {"locations", "costing"}

    slim = Env(engine, routing_slim_route_requests=True)
    slim.service.cells([(b, a)], "drive")  # the other direction: not in the cache yet
    assert slim.stub.bodies[0]["directions_type"] == "none"
    assert slim.stub.bodies[0]["shape_format"] == "no_shape"
    slim.service.route_geometry(a, b, "drive")  # geometry is wanted: the shape is kept
    assert slim.stub.bodies[1]["directions_type"] == "none"
    assert "shape_format" not in slim.stub.bodies[1]


def test_route_geometry_is_returned_but_never_stored(env: Env) -> None:
    a, b = coord(43.7696, 11.2558), coord(41.9028, 12.4964)
    line = env.service.route_geometry(a, b, "drive")
    assert line is not None and len(line.points) == 3
    assert (line.seconds, line.meters) == (11505, 282885)
    assert env.rows() == []  # nothing archived or cached (ADR 006)
    with env.engine.begin() as conn:
        assert conn.execute(text("SELECT count(*) FROM app.transfer")).scalar_one() == 0


def test_route_geometry_is_none_when_the_provider_cannot_give_it(env: Env) -> None:
    env.stub.mode = "500"
    a, b = coord(43.7696, 11.2558), coord(41.9028, 12.4964)
    assert env.service.route_geometry(a, b, "drive") is None  # no line is invented
    assert env.service.route_geometry(a, a, "drive") is None


def test_no_cache_available_means_estimates_and_no_calls(env: Env, engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE geo.travel_time RENAME TO travel_time_gone"))
    try:
        pts = street(2)
        result = env.service.cells([(pts[0], pts[1])], "walk")
        assert result.get(pts[0], pts[1]).reason == "cache_unavailable"
        assert env.stub.requests == []
    finally:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE geo.travel_time_gone RENAME TO travel_time"))
