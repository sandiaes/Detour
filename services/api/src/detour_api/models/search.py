"""Models for region, attribution, destination and place search."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from detour_api.models.common import PlaceName


class DataVersion(BaseModel):
    import_run_id: uuid.UUID
    osm_snapshot_date: date | None = Field(
        description="Replication date of the OpenStreetMap extract; null if the file had none"
    )
    finished_at: datetime | None


class RegionInfo(BaseModel):
    id: str
    name: str
    country_codes: list[str]
    status: Literal["available", "importing", "disabled"]
    data_version: DataVersion | None = Field(description="Null until a first import succeeded")
    counts: dict[str, int] = Field(description="Places by kind in the current data version")


class AttributionEntry(BaseModel):
    name: str
    text: str
    url: str
    licence: str | None
    applies_to: str


class ExternalPlace(BaseModel):
    """A result from the external provider (Photon). Not part of our data: use it to create a
    user place with ``source = search_result``."""

    provider: Literal["photon"] = "photon"
    ref: str | None = Field(description="Provider reference, for example N123 (OSM node 123)")
    name: str
    lat: float
    lon: float
    osm_key: str | None
    osm_value: str | None
    country_code: str | None
    country: str | None
    state: str | None
    city: str | None
    street: str | None
    housenumber: str | None
    postcode: str | None
    licence: Literal["ODbL-1.0"] = "ODbL-1.0"


class ExternalStatus(BaseModel):
    state: Literal[
        "not_requested", "not_needed", "ok", "cached", "unavailable", "budget_exhausted", "disabled"
    ] = Field(
        description="not_requested: include_external was false. not_needed: local results exist. "
        "unavailable, budget_exhausted and disabled: no external results, local results unchanged."
    )
    provider: Literal["photon"] | None = None
    results: list[ExternalPlace] = Field(default_factory=list)


MatchQuality = Literal["exact", "prefix", "word_prefix", "contains", "similar"]


class DestinationResult(BaseModel):
    kind: Literal["city", "area"]
    ref: str = Field(description="geo.city id (kind city) or geo.admin_area id (kind area)")
    name: str
    country_iso2: str | None
    country_name: str | None
    admin1_name: str | None = Field(description="Name of the first-level division, if known")
    population: int | None = Field(description="Null when unknown")
    admin_level: int | None = Field(description="OSM admin_level, areas only")
    lat: float
    lon: float
    region_id: str | None = Field(description="The import region that covers this destination")
    planning_available: bool = Field(
        description="True only if the covering region is available (passed its readiness gates)"
    )
    unavailable_reason: Literal["region_not_available", "area_single_city_only"] | None = Field(
        default=None,
        description="Null when a trip to this destination can be planned. region_not_available: "
        "the region has not passed its readiness gates. area_single_city_only: an area in a "
        "country planned as single-city trips only (Japan, for now); choose a city.",
    )
    match: MatchQuality


class DestinationSearchResponse(BaseModel):
    query: str
    results: list[DestinationResult]
    external: ExternalStatus


class PlaceSource(BaseModel):
    source: str
    source_ref: str
    licence: str
    attribution: str


class PlaceSummary(BaseModel):
    id: uuid.UUID
    name: str | None = Field(description="Null when the source has no name")
    name_en: str | None = Field(
        default=None,
        description="The English name the source gives (OpenStreetMap name:en), only when it "
        "differs from the name; null = none. Never machine-translated.",
    )
    names: PlaceName | None = Field(
        default=None,
        description="The resolved English-facing name with the original local name (ADR 025)",
    )
    kind: Literal["attraction", "transport_hub", "other"]
    category: str
    lat: float
    lon: float
    region_id: str
    city_id: int | None
    city_name: str | None
    distance_m: float | None = Field(default=None, description="From the search point, if given")
    match: MatchQuality | None = None


class PlaceDetail(PlaceSummary):
    names_i18n: dict[str, str] | None
    address: dict[str, str] | None
    default_visit_minutes: int | None = Field(
        description="Null: no category rule table exists yet (Phase 4); never a guess"
    )
    is_active: bool
    wikidata_id: str | None
    sources: list[PlaceSource]


class PlaceSearchResponse(BaseModel):
    query: str | None
    results: list[PlaceSummary]
    external: ExternalStatus


class RemovalTrip(BaseModel):
    id: uuid.UUID
    title: str
    status: Literal["active", "past"]


class RegionRemoval(BaseModel):
    """What removing a region's imported data takes away and keeps (ADR 033). A place, or an area,
    that one of the trips, a past-trip record or a display-name override names is kept (inactive,
    with its names and photo link), so no trip loses anything it shows."""

    region_id: str
    name: str
    places_total: int
    places_removed: int
    places_kept: int = Field(description="Places a trip still names: kept, no longer searchable")
    admin_areas_removed: int
    admin_areas_kept: int
    trips: list[RemovalTrip] = Field(
        description="The caller's trips that use this region's data, past trips included"
    )
    bytes_freed_estimate: int = Field(
        description="About how much database space the removal frees; an estimate from row sizes"
    )


class ImportJob(BaseModel):
    """A region import started from the app (ADR 033). ``stalled`` means it was not reported on
    for too long: the workflow probably failed before it could say so."""

    id: uuid.UUID
    status: Literal["requested", "running", "succeeded", "failed", "stalled"]
    message: str | None
    run_url: str | None = Field(description="The workflow run on GitHub, when GitHub gave it")
    requested_at: datetime
    updated_at: datetime


class CatalogRegion(BaseModel):
    id: str
    name: str
    country_codes: list[str]
    state: Literal["not_imported", "available", "disabled", "importing"]
    places: int = Field(description="Searchable places of the region in the database")
    places_kept: int = Field(description="Places kept for trips after a removal (not searchable)")
    bytes: int | None = Field(
        description="About how much database space the region's places take (an estimate: its "
        "share of the place tables' size); null when it has none"
    )
    job: ImportJob | None = Field(description="The latest import started from the app")


class RegionCatalog(BaseModel):
    can_manage: bool = Field(description="True for the owner: only they may import or remove")
    import_enabled: bool = Field(description="False when the server has no GitHub token")
    geo_bytes: int = Field(description="Space the imported data takes in the database")
    geo_limit_bytes: int = Field(description="The limit ADR 009 gate 6 allows for all regions")
    regions: list[CatalogRegion]


class ImportRequest(BaseModel):
    gazetteer: bool = Field(default=True, description="Also import the GeoNames cities first")
