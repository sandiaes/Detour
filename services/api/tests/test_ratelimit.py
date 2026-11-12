"""Token bucket and circuit breaker (ADR 004): driven by a fake clock, no sleeping."""

import pytest

from detour_api.adapters.ratelimit import CircuitBreaker, TokenBucket
from tests.valhalla_stub import FakeClock


def test_burst_of_ten_then_one_per_second() -> None:
    clock = FakeClock()
    bucket = TokenBucket(1.0, 10, now=clock.now, sleep=clock.sleep)
    assert [bucket.try_acquire() for _ in range(10)] == [0.0] * 10
    wait = bucket.try_acquire()  # the eleventh call in the same instant is refused
    assert wait == pytest.approx(1.0)
    clock.advance(1.0)
    assert bucket.try_acquire() == 0.0
    assert bucket.try_acquire() > 0.0


def test_the_bucket_never_holds_more_than_the_burst() -> None:
    clock = FakeClock()
    bucket = TokenBucket(1.0, 10, now=clock.now, sleep=clock.sleep)
    clock.advance(3600)  # an idle hour does not store 3600 calls
    granted = sum(1 for _ in range(50) if bucket.try_acquire() == 0.0)
    assert granted == 10


def test_sustained_rate_is_one_per_second_over_a_long_window() -> None:
    clock = FakeClock()
    bucket = TokenBucket(1.0, 10, now=clock.now, sleep=clock.sleep)
    granted = 0
    for _ in range(600):  # try ten times a second for a minute
        if bucket.try_acquire() == 0.0:
            granted += 1
        clock.advance(0.1)
    assert granted <= 10 + 60  # burst + rate x window
    assert granted >= 60


def test_acquire_waits_when_the_wait_is_short_enough() -> None:
    clock = FakeClock()
    bucket = TokenBucket(1.0, 2, now=clock.now, sleep=clock.sleep)
    assert bucket.acquire(5) and bucket.acquire(5)
    assert bucket.acquire(5)  # has to wait one second
    assert clock.slept == [pytest.approx(1.0)]


def test_acquire_gives_up_instead_of_queuing_beyond_the_limit() -> None:
    clock = FakeClock()
    bucket = TokenBucket(1.0, 1, now=clock.now, sleep=clock.sleep)
    assert bucket.acquire(0)
    assert bucket.acquire(0.5) is False  # needs 1 s, only 0.5 s allowed
    assert clock.slept == []  # and it did not sleep first
    clock.advance(1.0)
    assert bucket.acquire(0)  # the refused call took nothing


def test_bucket_rejects_nonsense_settings() -> None:
    with pytest.raises(ValueError):
        TokenBucket(0, 10)
    with pytest.raises(ValueError):
        TokenBucket(1, 0)


def test_breaker_is_closed_until_a_failure_then_pauses() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker(60, 300, 900, now=clock.now)
    assert breaker.state == "closed" and breaker.allow()
    breaker.record_failure()
    assert breaker.state == "open" and not breaker.allow()
    clock.advance(59)
    assert not breaker.allow()
    clock.advance(2)
    assert breaker.state == "half-open"


def test_half_open_allows_exactly_one_probe() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker(60, 300, 900, now=clock.now)
    breaker.record_failure()
    clock.advance(61)
    assert breaker.allow() is True
    assert breaker.allow() is False  # the probe is out; nobody else goes
    breaker.cancel_probe()  # the probe was not made after all
    assert breaker.allow() is True


def test_a_successful_probe_closes_and_a_failed_one_doubles_the_pause() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker(60, 300, 900, now=clock.now)
    breaker.record_failure()
    clock.advance(61)
    assert breaker.allow()
    breaker.record_failure()  # probe failed: 120 s now
    clock.advance(100)
    assert not breaker.allow()
    clock.advance(21)
    assert breaker.allow()
    breaker.record_success()
    assert breaker.state == "closed" and breaker.allow()
    breaker.record_failure()  # a fresh failure starts at the base pause again
    clock.advance(61)
    assert breaker.allow()


def test_rate_limited_pause_is_longer_and_honours_retry_after() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker(60, 300, 900, now=clock.now)
    breaker.record_failure(rate_limited=True)
    clock.advance(299)
    assert not breaker.allow()
    clock.advance(2)
    assert breaker.allow()
    breaker.record_success()
    breaker.record_failure(rate_limited=True, retry_after=600)
    clock.advance(599)
    assert not breaker.allow()
    clock.advance(2)
    assert breaker.allow()


def test_pause_is_capped() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker(60, 300, 900, now=clock.now)
    for _ in range(10):
        breaker.record_failure()
    clock.advance(901)
    assert breaker.allow()
