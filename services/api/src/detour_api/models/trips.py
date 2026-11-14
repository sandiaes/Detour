"""Models for trips, user places, itineraries, days and items."""

import uuid
from datetime import date, datetime, time, timedelta
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from detour_api.models.common import Latitude, Longitude, PlaceName, StrictModel
from detour_api.models.images import Photo

MealType = Literal["breakfast", "lunch", "dinner", "snack"]


# -- trips -------------------------------------------------------------------------------------


MIN_STOPS = 2
MAX_STOPS = 6


class StopIn(StrictModel):
    """A stop of a multi-city trip, in the user's order (ADR 024)."""

    city_id: int = Field(ge=1, description="The city's GeoNames id (a destination search result)")
    days: int = Field(ge=1, le=30)


class TripCreate(StrictModel):
    title: str = Field(
        min_length=1,
        max_length=120,
        description="Ignored for a multi-city trip, whose name follows its stops",
    )
    destination_kind: Literal["city", "area", "route"]
    destination_ref: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description="The city or area; not sent for a multi-city trip (route)",
    )
    stops: list[StopIn] | None = Field(
        default=None,
        description="Only for a multi-city trip: 2 to 6 cities in order, whose days add up to "
        "duration_days",
    )
    duration_days: int = Field(ge=1, le=30)
    start_date: date | None = None

    @model_validator(mode="after")
    def _destination_or_stops(self) -> Self:
        if self.destination_kind == "route":
            if self.stops is None:
                raise ValueError("a multi-city trip needs its stops")
            if self.destination_ref is not None:
                raise ValueError("a multi-city trip has stops, not destination_ref")
        else:
            if self.destination_ref is None:
                raise ValueError("destination_ref is required")
            if self.stops is not None:
                raise ValueError("only a multi-city trip (route) has stops")
        return self


class TripStop(BaseModel):
    position: int = Field(description="1 for the first city")
    city_id: int
    name: str
    country_iso2: str | None
    lat: float
    lon: float
    days: int


class TripUpdate(StrictModel):
    """Only the fields present are changed. The destination is fixed after creation."""

    title: str | None = Field(default=None, min_length=1, max_length=120)
    duration_days: int | None = Field(default=None, ge=1, le=30)
    start_date: date | None = None
    selected_itinerary_id: uuid.UUID | None = None


class Destination(BaseModel):
    """For a multi-city trip (route): ``ref`` is the first stop's city and ``name`` the trip's."""

    kind: Literal["city", "area", "route"]
    ref: str
    name: str
    lat: float
    lon: float


class Trip(BaseModel):
    id: uuid.UUID
    title: str
    destination: Destination
    duration_days: int
    start_date: date | None
    end_date: date | None = Field(
        description="start_date + duration_days - 1, if start_date is set"
    )
    selected_itinerary_id: uuid.UUID | None
    status: Literal["active", "past"]
    archived_at: datetime | None
    is_seed: bool = Field(description="True for the illustrative seed trip; not user data")
    cover_image: Photo | None = Field(
        default=None,
        description="The trip's photo: the one the user chose, else the one found for the "
        "destination city; null when there is none (the app then shows its illustration)",
    )
    stops: list[TripStop] = Field(
        default_factory=list, description="A multi-city trip's cities in order; empty otherwise"
    )
    stops_version: int = Field(
        default=0, description="Counts applied stop edits; a plan records the one it was made for"
    )
    created_at: datetime
    updated_at: datetime


def end_date_of(start: date | None, days: int) -> date | None:
    return None if start is None else start + timedelta(days=days - 1)


class TripVisit(BaseModel):
    id: uuid.UUID
    kind: Literal["city", "attraction"]
    name: str
    lat: float
    lon: float
    geo_place_ref: str | None
    day_number: int
    confirmed: bool


class TripVisitUpdate(StrictModel):
    confirmed: bool


class ArchiveInfo(BaseModel):
    """What a past trip keeps, and how much room it takes (ADR 006)."""

    trip_id: uuid.UUID
    cities: int = Field(description="Archived city rows (each base city once)")
    attractions: int
    skipped: int = Field(description="Visits the user cleared (confirmed = false)")
    size_bytes: int = Field(
        description="Stored row data of the trip row and its visit rows (PostgreSQL "
        "pg_column_size). Indexes and page overhead are not counted"
    )


# -- user places -------------------------------------------------------------------------------


class UserPlaceCreate(StrictModel):
    kind: Literal["city", "location", "restaurant", "cafe"]
    name: str = Field(min_length=1, max_length=200)
    lat: Latitude
    lon: Longitude
    source: Literal["manual_pin", "search_result"]
    search_provider: Literal["photon", "geonames"] | None = Field(
        default=None,
        description="photon: an external search result (ref like N123). geonames: a town from "
        "destination search, saved to add it to a plan (ref: its gazetteer id)",
    )
    search_ref: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def _rules(self) -> Self:
        has_provider = self.search_provider is not None and self.search_ref is not None
        if self.source == "search_result" and not has_provider:
            raise ValueError("a search_result needs search_provider and search_ref")
        if self.source == "manual_pin" and (self.search_provider or self.search_ref):
            raise ValueError("a manual_pin has no search_provider or search_ref")
        return self


class UserPlaceUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    lat: Latitude | None = None
    lon: Longitude | None = None

    @model_validator(mode="after")
    def _rules(self) -> Self:
        if (self.lat is None) != (self.lon is None):
            raise ValueError("lat and lon must be changed together")
        return self


class UserPlace(BaseModel):
    id: uuid.UUID
    kind: Literal["city", "location", "restaurant", "cafe"]
    name: str
    lat: float
    lon: float
    source: Literal["manual_pin", "search_result"]
    search_provider: str | None
    search_ref: str | None
    created_at: datetime
    updated_at: datetime


# -- itineraries -------------------------------------------------------------------------------


class ItemCreate(StrictModel):
    type: Literal["visit", "meal", "free_time"]
    place_id: uuid.UUID | None = Field(default=None, description="A geo.place")
    user_place_id: uuid.UUID | None = None
    start_time: time | None = Field(default=None, description="Local time at the destination")
    duration_minutes: int | None = Field(
        default=None,
        ge=1,
        le=1440,
        description="Required unless the place has a known default (none exists yet)",
    )
    position: int | None = Field(default=None, ge=1, description="Defaults to the end of the day")
    locked: bool = False

    @model_validator(mode="after")
    def _shape(self) -> Self:
        both = self.place_id is not None and self.user_place_id is not None
        neither = self.place_id is None and self.user_place_id is None
        if self.type == "free_time":
            if not neither:
                raise ValueError("free_time has no place")
        elif both or neither:
            raise ValueError("exactly one of place_id and user_place_id is required")
        if self.start_time is not None and self.start_time.tzinfo is not None:
            raise ValueError("start_time is a local time without a time zone")
        return self


class ItemUpdate(StrictModel):
    """Only the fields present are changed; ``start_time: null`` clears the schedule."""

    start_time: time | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    locked: bool | None = None
    position: int | None = Field(default=None, ge=1)
    day_index: int | None = Field(default=None, ge=1, description="Move to another day")


class Transfer(BaseModel):
    to_item_id: uuid.UUID
    mode: Literal["walk", "drive"]
    seconds: int
    meters: int
    confidence: Literal["routed", "estimated"] = Field(
        description="routed: from the routing provider; estimated: straight-line distance times "
        "a detour factor, an assumption and not a measurement"
    )


class Arrival(BaseModel):
    """The drive from the previous day's base city that starts the first day at a new one."""

    from_base_city_id: int | None
    from_base_city_name: str | None
    mode: Literal["walk", "drive", "unknown"] = Field(
        description="unknown: a leg into or out of a country travelled by rail, which Detour "
        "does not plan yet; no time or distance is given (ADR 024)"
    )
    seconds: int | None
    meters: int | None
    confidence: Literal["routed", "estimated", "unknown"]


class RestaurantInfo(BaseModel):
    """What is known about a restaurant or cafe stop: only its kind. There is no cuisine, meal
    type, price, rating or opening hours (ADR 026)."""

    venue_type: Literal["restaurant", "cafe"] | None = Field(
        description="The kind of the user's place; null when unknown"
    )


class Item(BaseModel):
    id: uuid.UUID
    day_id: uuid.UUID
    position: int
    type: Literal["visit", "meal", "free_time"]
    place_id: uuid.UUID | None
    user_place_id: uuid.UUID | None
    display_name: str
    lat: float | None
    lon: float | None
    start_time: time | None
    end_time: time | None
    duration_minutes: int
    duration_source: Literal["category_default", "user"]
    origin: Literal["engine", "user"]
    locked: bool
    reasons: list[str] = Field(description="Reason codes")
    reason_texts: list[str] = Field(
        description="The reason codes rendered through fixed templates, in the same order"
    )
    transfer: Transfer | None = Field(
        default=None,
        description="To the next item of the day. Null for the last item, or when no transfer "
        "has been computed (items added or moved by hand)",
    )
    restaurant: RestaurantInfo | None = Field(
        default=None, description="Restaurant and cafe stops only: its kind"
    )
    image: Photo | None = Field(
        default=None,
        description="Photo of an imported place, when one was found (restaurants have none yet)",
    )
    names: PlaceName | None = Field(
        default=None,
        description="Imported places: the resolved English-facing name and the original local "
        "name (ADR 025), read when the plan is read. display_name stays the stored snapshot",
    )


class Day(BaseModel):
    id: uuid.UUID
    day_index: int
    date: date | None
    base_city_id: int | None
    base_city_name: str | None = Field(
        default=None, description="The city the day is planned from (a snapshot)"
    )
    base_city_lat: float | None = Field(
        default=None,
        description="The base city's position, read from the gazetteer by base_city_id when the "
        "plan is read (not stored on the day); null when the city is not in the gazetteer",
    )
    base_city_lon: float | None = Field(default=None, description="See base_city_lat")
    arrival: Arrival | None = Field(
        default=None,
        description="Travel from the previous day's base city at the start of the day; null "
        "when the base does not change",
    )
    items: list[Item]


class PlanNote(BaseModel):
    code: str = Field(description="Stable code")
    text: str = Field(description="The code rendered through its fixed template")


class PlanStats(BaseModel):
    visits: int
    days_with_visits: int
    visit_minutes: int
    travel_minutes: int
    travel_seconds: int
    routed_transfers: int
    estimated_transfers: int
    day_utilisation_permille: int = Field(
        description="Visits, meals and transfers as permille of the 09:00-22:00 window of all days"
    )
    travel_share_permille: int = Field(description="Transfer time as permille of planned time")
    meals: int = 0
    meal_minutes: int = 0
    intercity_legs: int = Field(
        default=0, description="Drives between base cities; included in travel_minutes"
    )


class ItinerarySummary(BaseModel):
    id: uuid.UUID
    trip_id: uuid.UUID
    generation_id: uuid.UUID = Field(description="Shared by the variants of one generation")
    profile: Literal["essentials", "wider", "manual"]
    status: Literal["proposed", "selected", "superseded"]
    version: int
    engine_version: str
    config_version: str
    import_run_id: uuid.UUID | None = Field(description="The data version the plan was built on")
    seed: int | None
    diversity_score: float | None = Field(
        description="Jaccard similarity of the visit sets of the generation's two variants"
    )
    notes: list[PlanNote] = Field(description="Plan-level explanations; empty for manual plans")
    stats: PlanStats | None = Field(description="Null for manual itineraries")
    created_at: datetime
    stops_version: int | None = Field(
        default=None,
        description="A multi-city trip's stop version this plan was made for; a plan whose "
        "version is not the trip's was made for earlier cities and cannot be chosen",
    )


class Itinerary(ItinerarySummary):
    days: list[Day]


class GenerationResult(BaseModel):
    generation_id: uuid.UUID
    distinct: bool = Field(
        description="True when two meaningfully different itineraries were made; false when the "
        "destination supports only one (the notes say why)"
    )
    jaccard_permille: int | None = Field(
        description="Overlap of the two variants' visit sets; null with one itinerary"
    )
    max_jaccard_permille: int
    notes: list[PlanNote]
    itineraries: list[Itinerary]
