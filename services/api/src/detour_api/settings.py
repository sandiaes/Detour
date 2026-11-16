"""Environment-based configuration.

Every value comes from an environment variable with the prefix ``DETOUR_``. Secrets (the
database URL and the token secret) are set only in the hosting provider's settings, never in the
repository (see ``.env.example`` and ``docs/deployment.md``).
"""

import uuid
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
    # Starting a region import from the app (ADR 033, step 3): the backend asks GitHub to run the
    # repository's "Import region" workflow. The token is a fine-grained personal access token
    # limited to this repository with the Actions read and write permission, kept as a secret of
    # the hosting settings; without it the app's Import button answers 503. The daily budget is
    # our own limit (GitHub's primary limit for a token is 5,000 requests an hour, read 2026-11-17).
    github_token: SecretStr | None = None
    github_api_url: str = "https://api.github.com"
    github_repository: str = "sandiaes/Detour"
    github_workflow: str = "import-region.yml"
    github_ref: str = "main"
    github_user_agent: str = "Detour-backend/0.1 (+https://github.com/sandiaes/Detour)"
    github_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    github_daily_budget: int = Field(default=20, ge=0)
    # An import not reported on for this long is shown as stalled (and may be asked for again).
    import_job_stall_minutes: int = Field(default=45, ge=5)

    # The installations of the server's owner, comma separated (ADR 033): only they may remove a
    # region. Empty means nobody may. An installation's id is shown in the app under More.
    owner_installation_ids: str = ""

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

    # Reference photos (ADR 022): Wikidata and the Wikimedia Commons API, backend-side only. Terms
    # read 2026-11-14 (ADR 022): a descriptive User-Agent with contact information, at most 3
    # concurrent requests (the adapter makes one at a time), obey Retry-After, batch with "|".
    # The interval, budget and size limits below are our own, not Wikimedia figures.
    wikimedia_enabled: bool = True
    wikimedia_user_agent: str = "Detour-bot/0.1 (+https://github.com/sandiaes/Detour)"
    wikidata_api_url: str = "https://www.wikidata.org/w/api.php"
    commons_api_url: str = "https://commons.wikimedia.org/w/api.php"
    # English Wikipedia's lead images: the third step of the fallback chain (ADR 022 amendment).
    enwiki_api_url: str = "https://en.wikipedia.org/w/api.php"
    wikimedia_timeout_seconds: float = Field(default=20.0, gt=0, le=120)
    wikimedia_min_interval_seconds: float = Field(default=1.0, ge=0.5, le=60)
    wikimedia_daily_budget: int = Field(default=3000, ge=0)
    # The API's maxlag: the server refuses a request while it reports more lag than this many
    # seconds. The first real run (2026-11-14, ADR 022) was refused for seven minutes at a
    # reported lag of 14 to 15 s, so 5 (the figure in the etiquette page's examples) is not usable
    # for reads; 30 still stops the run when the servers are genuinely struggling.
    wikimedia_maxlag_seconds: int = Field(default=30, ge=1, le=120)
    wikimedia_max_download_bytes: int = Field(default=12_000_000, ge=100_000)
    # Thumbnail width asked of Commons; it must be one of Wikimedia's standard thumbnail steps.
    image_source_width: int = 1280
    # The stored rendition (ADR 022, decision 5) and the cap on stored images (decision 6).
    image_max_side: int = Field(default=1080, ge=320, le=2000)
    image_jpeg_quality: int = Field(default=75, ge=40, le=95)
    image_max_stored: int = Field(default=4000, ge=1)
    # Supabase Storage for the stored renditions; both are secrets of the hosting settings.
    supabase_url: str | None = None
    supabase_service_key: SecretStr | None = None
    photos_bucket: str = "photos"

    # Plan generation (Phase 4, ADR 014). Whether it may ask the routing provider for the
    # transfers a plan uses (cached times are always read), and the total time it may spend
    # waiting on the provider; transfers not reached are estimated and labelled. Our own limits.
    planner_use_provider: bool = True
    planner_provider_max_seconds: float = Field(default=3.0, ge=0, le=30)
    # Recalculation after an added or removed place (Phase 7, ADR 018): the time a preview may
    # wait on the provider for the changed days' legs (the KPI is 3 s for the whole preview).
    recalc_provider_max_seconds: float = Field(default=2.0, ge=0, le=30)

    # Abuse limits on the public API (Phase 9, docs/security.md). The API has no accounts, so
    # anyone who learns its address can register installations. These are our own numbers, set
    # far above what one person's phone does: per installation, sustained requests per minute and
    # the burst allowed; and for the whole service, new registrations per hour and their burst.
    # Counted per process (the API runs as one process on Render's free plan).
    rate_limit_enabled: bool = True
    rate_limit_per_minute: float = Field(default=300.0, gt=0)
    rate_limit_burst: int = Field(default=150, ge=1)
    # Photos (GET /v1/images/...) are loaded by the phone's image view without the token, so they
    # share one bucket for the whole service; a list of trips loads many at once.
    image_requests_per_minute: float = Field(default=600.0, gt=0)
    image_requests_burst: int = Field(default=300, ge=1)
    registrations_per_hour: float = Field(default=20.0, gt=0)
    registrations_burst: int = Field(default=10, ge=1)
    # Typing a code to join a phone to a person (ADR 034): per phone 5 in 10 minutes, and for the
    # whole service 20 an hour, so the 8-letter one-time codes cannot be guessed.
    join_attempts_per_hour: float = Field(default=30.0, gt=0)
    join_attempts_burst: int = Field(default=5, ge=1)
    join_attempts_service_per_hour: float = Field(default=20.0, gt=0)
    join_attempts_service_burst: int = Field(default=10, ge=1)

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

    @field_validator("wikidata_api_url", "commons_api_url", "enwiki_api_url")
    @classmethod
    def _wikimedia_is_https(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError("wikimedia api urls must use https")
        return value

    @field_validator("supabase_url")
    @classmethod
    def _supabase_is_https(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith("https://"):
            raise ValueError("supabase url must use https")
        return None if value is None else value.rstrip("/")

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
    def owner_installations(self) -> frozenset[uuid.UUID]:
        """The owner's installation ids; entries that are not UUIDs are ignored."""
        found: set[uuid.UUID] = set()
        for part in self.owner_installation_ids.split(","):
            try:
                found.add(uuid.UUID(part.strip()))
            except ValueError:
                continue
        return frozenset(found)

    @property
    def token_secret_bytes(self) -> bytes:
        assert self.token_secret is not None  # set by the validator  # noqa: S101
        return self.token_secret.get_secret_value().encode()


@lru_cache
def get_settings() -> Settings:
    return Settings()
