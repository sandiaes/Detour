"""Where the stored renditions live: Supabase Storage in production (ADR 022, decision 7).

The backend writes with the service key and serves the bytes itself (``GET /v1/images/{id}``), so
the app never talks to Supabase. The request shapes follow Supabase's Storage API (upload:
``POST /storage/v1/object/{bucket}/{key}`` with ``x-upsert``; read from a public bucket:
``GET /storage/v1/object/public/{bucket}/{key}``); they are checked against the real service on the
first run of the resolver, not before.
"""

from typing import Protocol

import httpx

from detour_api.settings import Settings


class StoreError(Exception):
    pass


class ImageStore(Protocol):
    def put(self, key: str, data: bytes, content_type: str = "image/jpeg") -> None: ...

    def get(self, key: str) -> bytes | None: ...

    def exists(self, key: str) -> bool: ...


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


class SupabaseImageStore:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        assert settings.supabase_url and settings.supabase_service_key  # noqa: S101
        self._base = f"{settings.supabase_url}/storage/v1/object"
        self._bucket = settings.photos_bucket
        self._key = settings.supabase_service_key.get_secret_value()
        self._transport = transport

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=20.0, transport=self._transport)

    def put(self, key: str, data: bytes, content_type: str = "image/jpeg") -> None:
        headers = {
            "Authorization": f"Bearer {self._key}",
            "apikey": self._key,
            "Content-Type": content_type,
            "x-upsert": "true",
            "Cache-Control": "max-age=31536000",
        }
        try:
            with self._client() as client:
                response = client.post(
                    f"{self._base}/{self._bucket}/{key}", content=data, headers=headers
                )
        except httpx.HTTPError as exc:
            raise StoreError(type(exc).__name__) from exc
        if response.status_code >= 400:
            raise StoreError(f"upload refused: HTTP {response.status_code}")

    def get(self, key: str) -> bytes | None:
        try:
            with self._client() as client:
                response = client.get(f"{self._base}/public/{self._bucket}/{key}")
        except httpx.HTTPError as exc:
            raise StoreError(type(exc).__name__) from exc
        if response.status_code == 404 or response.status_code == 400:
            return None
        if response.status_code >= 400:
            raise StoreError(f"read refused: HTTP {response.status_code}")
        return response.content

    def exists(self, key: str) -> bool:
        """Whether the object is there, without downloading it (a HEAD request)."""
        try:
            with self._client() as client:
                response = client.head(f"{self._base}/public/{self._bucket}/{key}")
        except httpx.HTTPError as exc:
            raise StoreError(type(exc).__name__) from exc
        if response.status_code in (400, 404):
            return False
        if response.status_code >= 400:
            raise StoreError(f"read refused: HTTP {response.status_code}")
        return True


def make_store(
    settings: Settings, transport: httpx.BaseTransport | None = None
) -> ImageStore | None:
    """Supabase Storage when it is configured, else nothing (photos are then not stored)."""
    if settings.supabase_url and settings.supabase_service_key:
        return SupabaseImageStore(settings, transport)
    return None
