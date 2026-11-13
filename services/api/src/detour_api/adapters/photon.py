"""Photon geocoder adapter (ADR 002, ADR 012).

Photon is used only when the local data has no answer, only from the backend, and only through
this class, which provides what architecture section 6 requires of every provider:

* an identifying User-Agent (configuration),
* a timeout,
* a cache in ``app.provider_cache`` (queries are stored without any installation identifier),
* a daily call budget in ``app.provider_usage``, reserved atomically before the call,
* a fallback: any failure becomes a status in the result, never an exception, so local search
  and manual entry keep working.

Terms read on 2026-11-12 (https://photon.komoot.io): "You can use the API for your project, but
please be fair - extensive usage will be throttled. We do not guarantee for the availability and
usage might be subject of change in the future." Hence: small budget, week-long cache, a pause
after any failure, and a longer pause after HTTP 429.
"""

import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx
import structlog
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from detour_api.settings import Settings

log = structlog.get_logger("detour.photon")

PROVIDER = "photon"
FAILURE_PAUSE_SECONDS = 60.0
RATE_LIMIT_PAUSE_SECONDS = 300.0
MAX_RESULTS = 10

State = Literal["ok", "cached", "unavailable", "budget_exhausted", "disabled"]


@dataclass(frozen=True)
class ExternalPlaceData:
    name: str
    lat: float
    lon: float
    osm_type: str | None
    osm_id: int | None
    osm_key: str | None
    osm_value: str | None
    country_code: str | None
    country: str | None
    state: str | None
    city: str | None
    street: str | None
    housenumber: str | None
    postcode: str | None

    @property
    def ref(self) -> str | None:
        """Provider reference stored on a user place: ``N123`` (node), ``W5`` (way), ``R9``."""
        if self.osm_type and self.osm_id is not None:
            return f"{self.osm_type}{self.osm_id}"
        return None


@dataclass
class PhotonOutcome:
    state: State
    results: list[ExternalPlaceData] = field(default_factory=list)


def _text(value: Any, limit: int = 200) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()[:limit]
    return None


def parse_features(payload: Any) -> list[ExternalPlaceData]:
    """Read a Photon GeoJSON FeatureCollection; skip anything malformed instead of guessing."""
    features = payload.get("features") if isinstance(payload, dict) else None
    if not isinstance(features, list):
        raise ValueError("not a FeatureCollection")
    results: list[ExternalPlaceData] = []
    for feature in features[:MAX_RESULTS]:
        if not isinstance(feature, dict):
            continue
        props = feature.get("properties")
        geometry = feature.get("geometry")
        if not isinstance(props, dict) or not isinstance(geometry, dict):
            continue
        coords = geometry.get("coordinates")
        name = _text(props.get("name"))
        if (
            name is None
            or geometry.get("type") != "Point"
            or not isinstance(coords, list)
            or len(coords) < 2
            or not all(isinstance(c, int | float) for c in coords[:2])
        ):
            continue
        lon, lat = float(coords[0]), float(coords[1])
        if not (
            math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180
        ):
            continue
        osm_id = props.get("osm_id")
        osm_type = props.get("osm_type")
        results.append(
            ExternalPlaceData(
                name=name,
                lat=lat,
                lon=lon,
                osm_type=osm_type if osm_type in ("N", "W", "R") else None,
                osm_id=osm_id if isinstance(osm_id, int) else None,
                osm_key=_text(props.get("osm_key"), 60),
                osm_value=_text(props.get("osm_value"), 60),
                country_code=_text(props.get("countrycode"), 2),
                country=_text(props.get("country")),
                state=_text(props.get("state")),
                city=_text(props.get("city")),
                street=_text(props.get("street")),
                housenumber=_text(props.get("housenumber"), 30),
                postcode=_text(props.get("postcode"), 30),
            )
        )
    return results


def cache_key(
    query: str,
    limit: int,
    lang: str | None,
    layers: tuple[str, ...],
    country_codes: tuple[str, ...],
    lat: float | None,
    lon: float | None,
    osm_tags: tuple[str, ...] = (),
) -> str:
    """Same question, same key. The bias point is rounded to 0.1 degree (about 11 km), which
    both improves cache hits and tells Photon less about where the user is."""
    payload = {
        "q": " ".join(query.casefold().split()),
        "limit": limit,
        "lang": lang,
        "layers": sorted(layers),
        "cc": sorted(country_codes),
        "lat": None if lat is None else round(lat, 1),
        "lon": None if lon is None else round(lon, 1),
        "osm_tags": sorted(osm_tags),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


class PhotonClient:
    def __init__(
        self,
        settings: Settings,
        engine: Engine | None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._engine = engine
        self._transport = transport
        self._paused_until = 0.0
        # Tests must never reach the network: only an injected transport enables Photon there.
        self.enabled = (
            settings.photon_enabled
            and engine is not None
            and (settings.environment != "test" or transport is not None)
        )

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        lang: str | None = None,
        layers: tuple[str, ...] = (),
        country_codes: tuple[str, ...] = (),
        lat: float | None = None,
        lon: float | None = None,
        osm_tags: tuple[str, ...] = (),
    ) -> PhotonOutcome:
        if not self.enabled or self._engine is None:
            return PhotonOutcome("disabled")
        limit = max(1, min(limit, MAX_RESULTS))
        key = cache_key(query, limit, lang, layers, country_codes, lat, lon, osm_tags)
        try:
            cached = self._cache_get(key)
            if cached is not None:
                return PhotonOutcome("cached", parse_features(cached))
            if time.monotonic() < self._paused_until:
                return PhotonOutcome("unavailable")
            if not self._reserve_call():
                log.warning("photon_budget_exhausted", budget=self._settings.photon_daily_budget)
                return PhotonOutcome("budget_exhausted")
            payload = self._fetch(query, limit, lang, layers, country_codes, lat, lon, osm_tags)
            results = parse_features(payload)
            self._cache_put(key, payload)
            return PhotonOutcome("ok", results)
        except (httpx.HTTPError, ValueError, SQLAlchemyError) as exc:
            # Only the class is logged: messages can contain the query text.
            log.warning("photon_unavailable", error=type(exc).__name__)
            return PhotonOutcome("unavailable")

    # -- HTTP ---------------------------------------------------------------------------------

    def _fetch(
        self,
        query: str,
        limit: int,
        lang: str | None,
        layers: tuple[str, ...],
        country_codes: tuple[str, ...],
        lat: float | None,
        lon: float | None,
        osm_tags: tuple[str, ...] = (),
    ) -> Any:
        params: list[tuple[str, str | int | float | bool | None]] = [
            ("q", query),
            ("limit", str(limit)),
        ]
        if lang:
            params.append(("lang", lang))
        params += [("layer", layer) for layer in layers]
        params += [("countrycode", cc) for cc in country_codes]
        # Photon's (deprecated, still documented) tag filter, e.g. amenity:restaurant. Callers
        # that need only some tags filter the results again: the filter may be ignored.
        params += [("osm_tag", tag) for tag in osm_tags]
        if lat is not None and lon is not None:
            params += [("lat", f"{round(lat, 1)}"), ("lon", f"{round(lon, 1)}")]
        try:
            with httpx.Client(
                base_url=self._settings.photon_base_url,
                headers={"User-Agent": self._settings.photon_user_agent},
                timeout=self._settings.photon_timeout_seconds,
                transport=self._transport,
            ) as client:
                response = client.get("/api", params=params)
        except httpx.HTTPError:
            self._paused_until = time.monotonic() + FAILURE_PAUSE_SECONDS
            raise
        if response.status_code == 429:
            self._paused_until = time.monotonic() + RATE_LIMIT_PAUSE_SECONDS
            raise httpx.HTTPStatusError("rate limited", request=response.request, response=response)
        if response.status_code >= 400:
            self._paused_until = time.monotonic() + FAILURE_PAUSE_SECONDS
            raise httpx.HTTPStatusError("error", request=response.request, response=response)
        return response.json()

    # -- cache and budget ---------------------------------------------------------------------

    def _cache_get(self, key: str) -> Any | None:
        assert self._engine is not None  # noqa: S101
        with self._engine.begin() as conn:
            row = conn.execute(
                text(
                    "SELECT response FROM app.provider_cache"
                    " WHERE cache_key = :k AND expires_at > now()"
                ),
                {"k": key},
            ).first()
        return None if row is None else row[0]

    def _cache_put(self, key: str, payload: Any) -> None:
        assert self._engine is not None  # noqa: S101
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO app.provider_cache (cache_key, provider, response, expires_at)"
                    " VALUES (:k, :p, CAST(:r AS jsonb), now() + make_interval(hours => :h))"
                    " ON CONFLICT (cache_key) DO UPDATE SET response = EXCLUDED.response,"
                    " fetched_at = now(), expires_at = EXCLUDED.expires_at"
                ),
                {
                    "k": key,
                    "p": PROVIDER,
                    "r": json.dumps(payload),
                    "h": self._settings.photon_cache_ttl_hours,
                },
            )
            conn.execute(
                text(
                    "DELETE FROM app.provider_cache WHERE cache_key IN"
                    " (SELECT cache_key FROM app.provider_cache WHERE expires_at < now()"
                    "  ORDER BY expires_at LIMIT 100)"
                )
            )

    def _reserve_call(self) -> bool:
        """Count one call for today unless the daily budget is used up (atomic)."""
        assert self._engine is not None  # noqa: S101
        with self._engine.begin() as conn:
            row = conn.execute(
                text(
                    "INSERT INTO app.provider_usage (provider, usage_date, calls)"
                    " VALUES (:p, (now() AT TIME ZONE 'UTC')::date, 1)"
                    " ON CONFLICT (provider, usage_date) DO UPDATE SET calls = provider_usage.calls + 1"
                    " WHERE provider_usage.calls < :budget RETURNING calls"
                ),
                {"p": PROVIDER, "budget": self._settings.photon_daily_budget},
            ).first()
        return row is not None
