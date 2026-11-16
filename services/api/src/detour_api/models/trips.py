"""Models for trips, user places, itineraries, days and items."""

import re
import uuid
from datetime import date, datetime, time, timedelta
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from detour_api.models.common import Latitude, Longitude, PlaceName, StrictModel
from detour_api.models.images import Photo

# -- trips -------------------------------------------------------------------------------------


MIN_STOPS = 2
MAX_STOPS = 6


# A place destination's reference names its provider (ADR 027).
PLACE_REF = re.compile(r"photon:[NWR][0-9]{1,20}|geonames:[0-9]{1,12}|area:[0-9a-fA-F-]{36}|manual")


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
    destination_kind: Literal["city", "area", "route", "place"]
    destination_ref: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description="The city or area; not sent for a multi-city trip (route). For a place "
        "(ADR 027): photon:N123, geonames:2761369, area:<uuid> or manual",
    )
    destination_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="Only for a place: the name the user chose, stored as a snapshot",
    )
    destination_lat: Latitude | None = Field(default=None, description="Only for a place")
    destination_lon: Longitude | None = Field(default=None, description="Only for a place")
    destination_country: str | None = Field(
        default=None,
        pattern="^[A-Za-z]{2}$",
        description="Only for a place: the ISO 3166-1 alpha-2 country code, if known",
    )
    stops: list[StopIn] | None = Field(
        default=None,
        description="Only for a multi-city trip: 2 to 6 cities in order, whose days add up to "
        "duration_days",
    )
    duration_days: int = Field(ge=1, le=30)
    start_date: date | None = None
    uses_car: bool = Field(
        default=True,
        description="False: Optimize considers walking only, never driving",
    )

    @model_validator(mode="after")
    def _destination_or_stops(self) -> Self:
        place_fields = (
            self.destination_name,
            self.destination_lat,
            self.destination_lon,
            self.destination_country,
        )
        if self.destination_kind == "place":
            if self.stops is not None:
                raise ValueError("only a multi-city trip (route) has stops")
            if self.destination_ref is None or not PLACE_REF.fullmatch(self.destination_ref):
                raise ValueError(
                    "a place needs destination_ref photon:N123, geonames:123, area:<uuid> or manual"
                )
            if None in (self.destination_name, self.destination_lat, self.destination_lon):
                raise ValueError("a place needs destination_name, destination_lat, destination_lon")
            return self
        if any(f is not None for f in place_fields):
            raise ValueError("only a place has a destination name, point or country")
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
    uses_car: bool | None = None


class Destination(BaseModel):
    """For a multi-city trip (route): ``ref`` is the first stop's city and ``name`` the trip's."""

    kind: Literal["city", "area", "route", "place"]
    ref: str
    name: str
    lat: float
    lon: float
    country_iso2: str | None = Field(default=None, description="Known for a place trip (ADR 027)")


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
    uses_car: bool = Field(
        default=True, description="False: Optimize considers walking only, never driving"
    )
    created_at: datetime
    updated_at: datetime


def end_date_of(start: date | None, days: int) -> date | None:
    return None if start is None else start + timedelta(days=days - 1)


class TripVisit(BaseModel):
    """One stop of a past trip's day record, or one of its base cities (ADR 006, ADR 026)."""

    id: uuid.UUID
    kind: Literal["city", "attraction", "restaurant", "cafe"]
    name: str
    lat: float
    lon: float
    geo_place_ref: str | None
    day_number: int
    position: int | None = Field(
        description="Order within the day; null for a base city row and for rows archived before "
        "the day record existed"
    )
    start_time: str | None = Field(description="HH:MM; null when the stop had no time")
    duration_minutes: int | None
    confirmed: bool = Field(description="Visited. Set when archived; the user can clear it")


class TripVisitUpdate(StrictModel):
    confirmed: bool


class ArchiveInfo(BaseModel):
    """What a past trip keeps, and how much room it takes (ADR 006)."""

    trip_id: uuid.UUID
    cities: int = Field(description="Archived city rows (each base city once)")
    attractions: int
    places_to_eat: int = Field(description="Restaurants and cafes the user added")
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

TransportMode = Literal["train", "bus", "metro_tram", "ferry", "taxi", "walk", "other"]

# How a leg's mode reads in its name ("Train to Florence"); the app has the same words.
TRANSPORT_LABELS: dict[str, str] = {
    "train": "Train",
    "bus": "Bus",
    "metro_tram": "Metro or tram",
    "ferry": "Ferry",
    "taxi": "Taxi or ride",
    "walk": "Walk",
    "other": "Transport",
}


class TransportInfo(StrictModel):
    """A transport leg the user entered by hand (ADR 032). Every value is the user's: nothing is
    computed or looked up. A point is given only when the end was picked from the trip (a stop, a
    city or a stay); a typed name has none. No price, operator or booking (ADR 017)."""

    mode: TransportMode
    from_name: str = Field(min_length=1, max_length=120)
    from_lat: Latitude | None = None
    from_lon: Longitude | None = None
    to_name: str = Field(min_length=1, max_length=120)
    to_lat: Latitude | None = None
    to_lon: Longitude | None = None
    is_journey: bool = Field(
        default=False,
        description="The journey between two cities: it covers the day's computed arrival",
    )
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _points(self) -> Self:
        if (self.from_lat is None) != (self.from_lon is None):
            raise ValueError("from_lat and from_lon are given together")
        if (self.to_lat is None) != (self.to_lon is None):
            raise ValueError("to_lat and to_lon are given together")
        if self.note is not None and not self.note:
            self.note = None
        return self

    def display_name(self) -> str:
        return f"{TRANSPORT_LABELS[self.mode]} to {self.to_name}"[:200]


class ItemCreate(StrictModel):
    type: Literal["visit", "meal", "free_time", "transport"]
    place_id: uuid.UUID | None = Field(default=None, description="A geo.place")
    user_place_id: uuid.UUID | None = None
    start_time: time | None = Field(default=None, description="Local time at the destination")
    duration_minutes: int | None = Field(
        default=None,
        ge=1,
        le=1440,
        description="Required unless the place has a known default (none exists yet)",
    )
    position: int | None = Field(
        default=None,
        ge=1,
        description="Defaults to the end of the day; a journey leg defaults to the start",
    )
    locked: bool = False
    transport: TransportInfo | None = Field(
        default=None,
        description="Required for type transport (ADR 032), and only then. Its length may be "
        "left out: it is then unknown",
    )
    shift_later_minutes: int | None = Field(
        default=None,
        ge=1,
        le=1440,
        description="A transport leg only (ADR 032): move every timed item after the leg on its "
        "day this many minutes later, in the same edit, so the leg fits. Refused when one would "
        "end after midnight",
    )

    @model_validator(mode="after")
    def _shape(self) -> Self:
        both = self.place_id is not None and self.user_place_id is not None
        neither = self.place_id is None and self.user_place_id is None
        if (self.type == "transport") != (self.transport is not None):
            raise ValueError("transport is given for a transport item, and only for one")
        if self.shift_later_minutes is not None and self.type != "transport":
            raise ValueError("shift_later_minutes is for a transport leg only")
        if self.type in ("free_time", "transport"):
            if not neither:
                raise ValueError(f"{self.type} has no place")
        elif both or neither:
            raise ValueError("exactly one of place_id and user_place_id is required")
        if self.start_time is not None and self.start_time.tzinfo is not None:
            raise ValueError("start_time is a local time without a time zone")
        return self


class ItemUpdate(StrictModel):
    """Only the fields present are changed; ``start_time: null`` clears the schedule."""

    start_time: time | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    use_default_duration: bool | None = Field(
        default=None,
        description="true: go back to the stop's default length (it is no longer marked as set "
        "by the user); wins over duration_minutes",
    )
    locked: bool | None = None
    position: int | None = Field(default=None, ge=1)
    day_index: int | None = Field(default=None, ge=1, description="Move to another day")
    transport: TransportInfo | None = Field(
        default=None,
        description="A transport leg only: replaces what the user entered (ADR 032). On a leg, "
        "duration_minutes: null makes its length unknown",
    )
    shift_later_minutes: int | None = Field(
        default=None,
        ge=1,
        le=1440,
        description="A transport leg only (ADR 032): move every timed item after the leg on its "
        "day this many minutes later, in the same edit, so the leg fits. Refused when one would "
        "end after midnight",
    )


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
    covered_by_item_id: uuid.UUID | None = Field(
        default=None,
        description="A journey leg the user entered for this day (ADR 032): show it instead of "
        "this computed leg, and count its length, not this one",
    )


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
    type: Literal["visit", "meal", "free_time", "transport"]
    place_id: uuid.UUID | None
    user_place_id: uuid.UUID | None
    display_name: str
    lat: float | None
    lon: float | None
    start_time: time | None
    end_time: time | None = Field(
        description="Null when unscheduled; a transport leg may have a start without an end: "
        "its length is unknown, or it arrives the next day"
    )
    duration_minutes: int | None = Field(
        description="Null only for a transport leg whose length the user did not enter (unknown)"
    )
    duration_source: Literal["category_default", "user"]
    default_duration_minutes: int | None = Field(
        default=None,
        description="The length 'use the default' would give this stop; null when none is known",
    )
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
    transport: TransportInfo | None = Field(
        default=None, description="Transport legs only (ADR 032): what the user entered"
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


class StayStart(BaseModel):
    """The traveller's morning at their stay: the leg from it to the day's first stop with a
    place. Worked out when the plan is read (cached times, labelled estimates), not stored."""

    stay_id: uuid.UUID
    name: str
    lat: float
    lon: float
    to_item_id: uuid.UUID
    mode: Literal["walk", "drive"]
    seconds: int
    meters: int
    confidence: Literal["routed", "estimated"]


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
    start: StayStart | None = Field(
        default=None,
        description="From the stay of this day to its first stop with a place (ADR 030); null "
        "without a stay or a stop",
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
        description=(
            "Visits, places to eat and transfers as permille of the 09:00-20:00 window of all "
            "days (ADR 026)"
        )
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


class Stay(BaseModel):
    """Where the traveller sleeps for a range of days of a trip (ADR 030)."""

    id: uuid.UUID
    trip_id: uuid.UUID
    name: str
    lat: float
    lon: float
    first_day: int = Field(ge=1)
    last_day: int = Field(ge=1)
    created_at: datetime


class StayCreate(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    first_day: int = Field(ge=1, le=30)
    last_day: int = Field(ge=1, le=30)


class StayUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    first_day: int | None = Field(default=None, ge=1, le=30)
    last_day: int | None = Field(default=None, ge=1, le=30)
