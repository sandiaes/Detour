"""Request limits for the public API (Phase 9; docs/security.md, "Unauthorised use").

The API has no accounts (app plan D5): an installation token only says "the same phone as
before", and anyone who learns the API's address can register as many installations as they
like. The limits here keep one caller from using up what the owner depends on: the database's
connections, the Photon and routing budgets shared by every installation, and Render's CPU.

* **Per installation:** a token bucket keyed by the installation identifier in the bearer token
  (only a genuine, signed token gets its own bucket; anything else shares the anonymous one).
* **Registrations:** one bucket for the whole service, because a new registration is the way
  around the per-installation limit.
* **Photos:** ``GET /v1/images/...`` and ``/v1/cover-previews/...`` are loaded by the phone's
  image view, which sends no token, so photos have one generous bucket of their own (a photo that
  is refused falls back to the illustration in the app).

Over a limit the API answers ``429`` with ``Retry-After`` and the code ``rate_limited``. The
buckets live in memory, per process, like the provider limits (``adapters/ratelimit.py``); a
restart (Render restarts free services at any time) refills them, which is acceptable for a
service with one user.
"""

import math
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable

from detour_api.adapters.ratelimit import TokenBucket
from detour_api.settings import Settings
from detour_api.tokens import verify_token

# Buckets kept at most; the least recently used go first. A full bucket that is dropped and
# recreated loses nothing, so the cap only bounds memory.
MAX_BUCKETS = 5_000
ANONYMOUS = "anonymous"


class RequestLimiter:
    def __init__(self, settings: Settings, *, now: Callable[[], float] = time.monotonic) -> None:
        self._settings = settings
        self._now = now
        self._lock = threading.Lock()
        self._buckets: OrderedDict[str, TokenBucket] = OrderedDict()
        self._registrations = TokenBucket(
            settings.registrations_per_hour / 3600.0, settings.registrations_burst, now=now
        )
        self._images = TokenBucket(
            settings.image_requests_per_minute / 60.0, settings.image_requests_burst, now=now
        )

    def _bucket(self, key: str) -> TokenBucket:
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = TokenBucket(
                    self._settings.rate_limit_per_minute / 60.0,
                    self._settings.rate_limit_burst,
                    now=self._now,
                )
                self._buckets[key] = bucket
                while len(self._buckets) > MAX_BUCKETS:
                    self._buckets.popitem(last=False)
            else:
                self._buckets.move_to_end(key)
            return bucket

    def caller_key(self, authorization: str | None) -> str:
        """The installation of a genuine token, or the shared anonymous key."""
        if authorization and authorization[:7].lower() == "bearer ":
            installation: uuid.UUID | None = verify_token(
                self._settings.token_secret_bytes, authorization[7:].strip()
            )
            if installation is not None:
                return installation.hex
        return ANONYMOUS

    def check(self, method: str, path: str, authorization: str | None) -> float:
        """0.0 when the request may go ahead, otherwise the seconds to wait."""
        if not self._settings.rate_limit_enabled:
            return 0.0
        # Health and configuration are what the app calls while the free host wakes up; they
        # touch neither the database nor a provider.
        if path.startswith("/v1/health") or path == "/v1/config":
            return 0.0
        if method == "POST" and path == "/v1/installations":
            return self._registrations.try_acquire()
        if method == "GET" and path.startswith(("/v1/images/", "/v1/cover-previews/")):
            return self._images.try_acquire()
        return self._bucket(self.caller_key(authorization)).try_acquire()


def retry_after_header(wait: float) -> str:
    return str(max(1, math.ceil(wait)))
