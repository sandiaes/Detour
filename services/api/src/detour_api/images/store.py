"""Where the stored renditions live: Supabase Storage in production (ADR 022, decision 7).

The backend writes with the service key and serves the bytes itself (``GET /v1/images/{id}``), so
the app never talks to Supabase. The request shapes follow Supabase's Storage API (upload:
``POST /storage/v1/object/{bucket}/{key}`` with ``x-upsert``; read from a public bucket:
``GET /storage/v1/object/public/{bucket}/{key}``); they are checked against the real service on the
first run of the resolver, not before.
"""

import time
from collections.abc import Callable
from typing import Protocol

import httpx

from detour_api.settings import Settings


class StoreError(Exception):
    pass


# Storage sits behind a CDN that answers 5xx now and then (a first real run met one HTTP 520 and
# stopped). A transient failure is tried again a few times; a refusal (4xx) is not.
ATTEMPTS = 4
BACKOFF_SECONDS = (1.0, 3.0, 8.0)


def with_retries(
    call: Callable[[], httpx.Response], sleep: Callable[[float], None] = time.sleep
) -> httpx.Response:
    """Run an HTTP call, repeating it after a network error or a 5xx answer."""
    for attempt in range(ATTEMPTS):
        last = attempt == ATTEMPTS - 1
        try:
            response = call()
        except httpx.HTTPError as exc:
            if last:
                raise StoreError(type(exc).__name__) from exc
        else:
            if response.status_code < 500 or last:
                return response
        sleep(BACKOFF_SECONDS[attempt])
    raise AssertionError("unreachable")  # pragma: no cover


class ImageStore(Protocol):
    def put(self, key: str, data: bytes, content_type: str = "image/jpeg") -> None: ...

    def get(self, key: str) -> bytes | None: ...

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> None: ...


class MemoryImageStore:
    """For tests and local runs without Supabase."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, data: bytes, content_type: str = "image/jpeg") -> None:
        self.objects[key] = data

    def get(self, key: str) -> bytes | None:
        return self.objects.get(key)

    def exists(self, key: str) -> bool:
        return key in self.objects

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)


class SupabaseImageStore:
    def __init__(
        self,
        settings: Settings,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._sleep = sleep
        assert settings.supabase_url and settings.supabase_service_key  # noqa: S101
        self._base = f"{settings.supabase_url}/storage/v1/object"
        self._bucket = settings.photos_bucket
        self._key = settings.supabase_service_key.get_secret_value()
        self._transport = transport

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=20.0, transport=self._transport)

    def _auth_headers(self) -> dict[str, str]:
        """A new-style secret key (``sb_secret_...``) is not a JWT and goes only in ``apikey``;
        Supabase says to send it nowhere else. A legacy ``service_role`` key is a JWT (``eyJ...``)
        and is also sent as the bearer token."""
        headers = {"apikey": self._key}
        if self._key.startswith("eyJ"):
            headers["Authorization"] = f"Bearer {self._key}"
        return headers

    def _send(self, method: str, url: str, **kwargs: object) -> httpx.Response:
        def call() -> httpx.Response:
            with self._client() as client:
                return client.request(method, url, **kwargs)  # type: ignore[arg-type]

        return with_retries(call, self._sleep)

    def put(self, key: str, data: bytes, content_type: str = "image/jpeg") -> None:
        headers = {
            **self._auth_headers(),
            "Content-Type": content_type,
            "x-upsert": "true",
            "Cache-Control": "max-age=31536000",
        }
        response = self._send(
            "POST", f"{self._base}/{self._bucket}/{key}", content=data, headers=headers
        )
        if response.status_code >= 400:
            raise StoreError(f"upload refused: HTTP {response.status_code}")

    def get(self, key: str) -> bytes | None:
        response = self._send("GET", f"{self._base}/public/{self._bucket}/{key}")
        if response.status_code in (400, 404):
            return None
        if response.status_code >= 400:
            raise StoreError(f"read refused: HTTP {response.status_code}")
        return response.content

    def exists(self, key: str) -> bool:
        """Whether the object is there, without downloading it (a HEAD request)."""
        response = self._send("HEAD", f"{self._base}/public/{self._bucket}/{key}")
        if response.status_code in (400, 404):
            return False
        if response.status_code >= 400:
            raise StoreError(f"read refused: HTTP {response.status_code}")
        return True

    def delete(self, key: str) -> None:
        """Remove one object (a cover preview after a week); a missing one is not an error."""
        response = self._send(
            "DELETE", f"{self._base}/{self._bucket}/{key}", headers=self._auth_headers()
        )
        if response.status_code >= 400 and response.status_code not in (400, 404):
            raise StoreError(f"delete refused: HTTP {response.status_code}")


def make_store(
    settings: Settings, transport: httpx.BaseTransport | None = None
) -> ImageStore | None:
    """Supabase Storage when it is configured, else nothing (photos are then not stored)."""
    if settings.supabase_url and settings.supabase_service_key:
        return SupabaseImageStore(settings, transport)
    return None
