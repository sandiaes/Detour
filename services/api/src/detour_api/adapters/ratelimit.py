"""Client-side politeness for a public server: a token bucket and a circuit breaker (ADR 004).

Both are pure state machines driven by an injected monotonic clock, so tests never sleep. Both
are thread-safe (FastAPI runs synchronous endpoints in a thread pool) and per process: the API
runs as one process on Render's free plan, so the limits hold for the whole service. A second
process would double the rate; revisit then.
"""

import threading
import time
from collections.abc import Callable

Clock = Callable[[], float]
Sleeper = Callable[[float], None]


class TokenBucket:
    """At most ``burst`` calls at once and ``rate_per_second`` calls per second sustained.

    The bucket starts full. Over any window of T seconds it admits at most ``burst + rate * T``
    calls.
    """

    def __init__(
        self,
        rate_per_second: float,
        burst: int,
        *,
        now: Clock = time.monotonic,
        sleep: Sleeper = time.sleep,
    ) -> None:
        if rate_per_second <= 0 or burst < 1:
            raise ValueError("rate must be positive and burst at least 1")
        self._rate = rate_per_second
        self._burst = float(burst)
        self._now = now
        self._sleep = sleep
        self._tokens = float(burst)
        self._stamp = now()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        current = self._now()
        elapsed = max(0.0, current - self._stamp)
        self._stamp = current
        self._tokens = min(self._burst, self._tokens + elapsed * self._rate)

    def try_acquire(self) -> float:
        """Take a token and return 0.0, or return the seconds to wait until one is available."""
        with self._lock:
            self._refill()
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return 0.0
            return (1.0 - self._tokens) / self._rate

    def acquire(self, max_wait: float) -> bool:
        """Wait up to ``max_wait`` seconds for a token. False (nothing taken) if that is not
        enough: the caller then degrades instead of queuing behind the limit."""
        deadline = self._now() + max(0.0, max_wait)
        while True:
            wait = self.try_acquire()
            if wait == 0.0:
                return True
            if self._now() + wait > deadline:
                return False
            self._sleep(wait)


class CircuitBreaker:
    """Stops calling after a failure.

    ``closed`` lets calls through. A failure opens it for a pause (``failure_pause``; an HTTP 429
    uses ``rate_limit_pause``, or the server's Retry-After if longer). When the pause is over it
    is ``half-open``: exactly one probe call is allowed. Success closes it; failure reopens it
    with the pause doubled, up to ``max_pause``.
    """

    def __init__(
        self,
        failure_pause: float = 60.0,
        rate_limit_pause: float = 300.0,
        max_pause: float = 900.0,
        *,
        now: Clock = time.monotonic,
    ) -> None:
        self._failure_pause = failure_pause
        self._rate_limit_pause = rate_limit_pause
        self._max_pause = max_pause
        self._now = now
        self._lock = threading.Lock()
        self._open_until = 0.0
        self._failures = 0
        self._probe_out = False

    @property
    def state(self) -> str:
        with self._lock:
            if self._failures == 0:
                return "closed"
            return "open" if self._now() < self._open_until else "half-open"

    def allow(self) -> bool:
        with self._lock:
            if self._failures == 0:
                return True
            if self._now() < self._open_until or self._probe_out:
                return False
            self._probe_out = True
            return True

    def cancel_probe(self) -> None:
        """A call that was allowed was not made after all (no token, no budget)."""
        with self._lock:
            self._probe_out = False

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._probe_out = False
            self._open_until = 0.0

    def record_failure(
        self, *, rate_limited: bool = False, retry_after: float | None = None
    ) -> None:
        with self._lock:
            self._failures += 1
            self._probe_out = False
            base = self._rate_limit_pause if rate_limited else self._failure_pause
            pause = min(self._max_pause, base * 2 ** (self._failures - 1))
            if retry_after is not None and retry_after > 0:
                pause = max(pause, min(self._max_pause, retry_after))
            self._open_until = self._now() + pause
