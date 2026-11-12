"""Environment-based configuration.

Every value comes from an environment variable with the prefix ``DETOUR_``. Secrets (the
database URL and the token secret) are set only in the hosting provider's settings, never in the
repository (see ``.env.example`` and ``docs/deployment.md``).
"""

from functools import lru_cache
from typing import Literal, Self

from pydantic import AliasChoices, BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Used for local development and tests only. Production must supply its own secret.
DEV_TOKEN_SECRET = "dev-only-secret-never-use-in-production-0000"  # noqa: S105
MIN_TOKEN_SECRET_LENGTH = 32


class AttributionItem(BaseModel):
    """One credit line the app must show next to the map."""

    text: str
    url: str

    @field_validator("url")
    @classmethod
    def _https_only(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError("attribution urls must use https")
        return value


# OpenFreeMap requires exactly this credit (docs/spikes/s1-map-findings.md, section 5).
DEFAULT_ATTRIBUTION = [
    AttributionItem(text="OpenFreeMap", url="https://openfreemap.org"),
    AttributionItem(text="© OpenMapTiles", url="https://www.openmaptiles.org/"),
    AttributionItem(text="Data from OpenStreetMap", url="https://www.openstreetmap.org/copyright"),
]


def normalize_database_url(url: str) -> str:
    """Turn a provider's ``postgresql://`` URL into the SQLAlchemy psycopg 3 form."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DETOUR_",
        env_ignore_empty=True,  # a blank line in .env.example means "not set"
        extra="ignore",
    )

    environment: Literal["local", "test", "production"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    # Commit identifier shown by the health endpoint. Render sets RENDER_GIT_COMMIT itself.
    release: str | None = Field(
        default=None, validation_alias=AliasChoices("DETOUR_RELEASE", "RENDER_GIT_COMMIT")
    )

    database_url: SecretStr | None = None
    token_secret: SecretStr | None = None

    # Photon (komoot's public geocoder) is the only external search provider, backend-side only.
    # Its terms (read 2026-11-12, ADR 012): "please be fair - extensive usage will be throttled",
    # no availability guarantee. The daily budget below is our own limit, not a Photon figure.
    photon_enabled: bool = True
    photon_base_url: str = "https://photon.komoot.io"
    photon_user_agent: str = "Detour-backend/0.2 (+https://github.com/sandiaes/Detour)"
    photon_timeout_seconds: float = 4.0
    photon_cache_ttl_hours: int = 168
    photon_daily_budget: int = 300

    # Travel times: the FOSSGIS Valhalla demo server, backend-side only (ADR 004, ADR 013). Its
    # rate rules come from the server's maintainers (ADR 004): 1 call per second, bursts of 10;
    # the validators below stop configuration from exceeding them. The daily budget, the cache
    # cap and the timeouts are our own limits, not figures from FOSSGIS.
    routing_enabled: bool = True
    routing_base_url: str = "https://valhalla1.openstreetmap.de"
    routing_user_agent: str = "Detour-backend/0.3 (+https://github.com/sandiaes/Detour)"
    routing_client_id: str = "detour-travel-planner"
    routing_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    routing_rate_per_second: float = Field(default=1.0, gt=0, le=1.0)
    routing_burst: int = Field(default=10, ge=1, le=10)
    # How long one operation may wait for a rate-limit token before it estimates instead.
    routing_max_wait_seconds: float = Field(default=5.0, ge=0, le=60)
    routing_daily_budget: int = Field(default=1500, ge=0)
    # Rows kept in geo.travel_time; the oldest go first. They count toward ADR 009 gate 6.
    routing_cache_max_rows: int = Field(default=100_000, ge=1000)
    # A cell the provider could not route is asked again only after this many days.
    routing_no_route_retry_days: int = Field(default=30, ge=1)
    # Ask /route for no turn-by-turn maneuvers (directions_type none; checked by hand, ADR 013).
    routing_slim_route_requests: bool = True

    # Plan generation (Phase 4, ADR 014). Whether it may ask the routing provider for the
    # transfers a plan uses (cached times are always read), and the total time it may spend
    # waiting on the provider; transfers not reached are estimated and labelled. Our own limits.
    planner_use_provider: bool = True
    planner_provider_max_seconds: float = Field(default=3.0, ge=0, le=30)

    # Client configuration served by GET /v1/config. The app holds none of these as constants.
    config_version: str = "1"
    map_style_url: str = "https://tiles.openfreemap.org/styles/liberty"
    map_attribution: list[AttributionItem] = Field(
        default_factory=lambda: list(DEFAULT_ATTRIBUTION)
    )

    @field_validator("map_style_url")
    @classmethod
    def _style_is_https(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError("map style url must use https")
        return value

    @field_validator("photon_base_url")
    @classmethod
    def _photon_is_https(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError("photon base url must use https")
        return value.rstrip("/")

    @field_validator("routing_base_url")
    @classmethod
    def _routing_is_https(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError("routing base url must use https")
        return value.rstrip("/")

    @field_validator("map_attribution")
    @classmethod
    def _attribution_not_empty(cls, value: list[AttributionItem]) -> list[AttributionItem]:
        if not value:
            raise ValueError("at least one attribution line is required")
        return value

    @model_validator(mode="after")
    def _token_secret_rules(self) -> Self:
        if self.token_secret is None:
            if self.environment == "production":
                raise ValueError(
                    "DETOUR_TOKEN_SECRET is required when DETOUR_ENVIRONMENT=production"
                )
            self.token_secret = SecretStr(DEV_TOKEN_SECRET)
        elif len(self.token_secret.get_secret_value()) < MIN_TOKEN_SECRET_LENGTH:
            raise ValueError(
                f"DETOUR_TOKEN_SECRET must have at least {MIN_TOKEN_SECRET_LENGTH} characters"
            )
        return self

    @property
    def sqlalchemy_url(self) -> str | None:
        if self.database_url is None:
            return None
        return normalize_database_url(self.database_url.get_secret_value())

    @property
    def token_secret_bytes(self) -> bytes:
        assert self.token_secret is not None  # set by the validator  # noqa: S101
        return self.token_secret.get_secret_value().encode()


@lru_cache
def get_settings() -> Settings:
    return Settings()
