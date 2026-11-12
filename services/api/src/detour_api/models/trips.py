"""Models for trips, user places, itineraries, days and items."""

import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from itertools import pairwise
from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from detour_api.models.common import CurrencyCode, Latitude, Longitude, StrictModel

MealType = Literal["breakfast", "lunch", "dinner"]
ALLOWED_MEAL_TYPES = ("breakfast", "lunch", "dinner", "snack")
Money = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]


# -- trips -------------------------------------------------------------------------------------


def _check_thresholds(value: list[Decimal] | None) -> list[Decimal] | None:
    if value is None:
        return None
    if len(value) != 3:
        raise ValueError("price_band_thresholds needs exactly three upper bounds")
    if any(v <= 0 for v in value) or any(a >= b for a, b in pairwise(value)):
        raise ValueError("price_band_thresholds must be positive and strictly increasing")
    return value


class TripCreate(StrictModel):
    title: str = Field(min_length=1, max_length=120)
    destination_kind: Literal["city", "area"]
    destination_ref: str = Field(min_length=1, max_length=64)
    duration_days: int = Field(ge=1, le=30)
    start_date: date | None = None
    currency_code: CurrencyCode | None = Field(
        default=None, description="Defaults to the destination country's currency, if known"
    )
    meal_budget_per_person: Money | None = None
    price_band_thresholds: list[Decimal] | None = Field(
        default=None,
        description="Upper bounds of budget, moderate and upscale, in the trip currency; "
        "fine dining is above the third. Null until set.",
    )

    @field_validator("price_band_thresholds")
    @classmethod
    def _thresholds(cls, value: list[Decimal] | None) -> list[Decimal] | None:
        return _check_thresholds(value)


class TripUpdate(StrictModel):
    """Only the fields present are changed. Destination and currency are fixed after creation."""

    title: str | None = Field(default=None, min_length=1, max_length=120)
    duration_days: int | None = Field(default=None, ge=1, le=30)
    start_date: date | None = None
    meal_budget_per_person: Money | None = None
    price_band_thresholds: list[Decimal] | None = None
    selected_itinerary_id: uuid.UUID | None = None

    @field_validator("price_band_thresholds")
    @classmethod
    def _thresholds(cls, value: list[Decimal] | None) -> list[Decimal] | None:
        return _check_thresholds(value)


class Destination(BaseModel):
    kind: Literal["city", "area"]
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
    currency_code: str
    meal_budget_per_person: Money | None
    price_band_thresholds: list[Decimal] | None
    selected_itinerary_id: uuid.UUID | None
    status: Literal["active", "past"]
    archived_at: datetime | None
    is_seed: bool = Field(description="True for the illustrative seed trip; not user data")
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


# -- user places -------------------------------------------------------------------------------


def _clean_list(
    values: list[str] | None, label: str, allowed: tuple[str, ...] | None
) -> list[str] | None:
    if values is None:
        return None
    cleaned = sorted({v.strip().lower().replace(" ", "_") for v in values if v.strip()})
    if not cleaned:
        return None
    for item in cleaned:
        if allowed is not None and item not in allowed:
            raise ValueError(f"{label}: {item!r} is not one of {', '.join(allowed)}")
        if allowed is None and not (1 <= len(item) <= 40 and item.replace("_", "").isalnum()):
            raise ValueError(f"{label}: {item!r} is not a valid cuisine name")
    return cleaned


class UserPlaceCreate(StrictModel):
    kind: Literal["city", "location", "restaurant"]
    name: str = Field(min_length=1, max_length=200)
    lat: Latitude
    lon: Longitude
    cuisines: list[str] | None = Field(default=None, max_length=10, description="Restaurants only")
    meal_types: list[str] | None = Field(default=None, max_length=4, description="Restaurants only")
    source: Literal["manual_pin", "search_result"]
    search_provider: Literal["photon"] | None = None
    search_ref: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def _rules(self) -> Self:
        self.cuisines = _clean_list(self.cuisines, "cuisines", None)
        self.meal_types = _clean_list(self.meal_types, "meal_types", ALLOWED_MEAL_TYPES)
        if self.kind != "restaurant" and (self.cuisines or self.meal_types):
            raise ValueError("cuisines and meal_types are only for restaurants")
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
    cuisines: list[str] | None = None
    meal_types: list[str] | None = None

    @model_validator(mode="after")
    def _rules(self) -> Self:
        if (self.lat is None) != (self.lon is None):
            raise ValueError("lat and lon must be changed together")
        self.cuisines = _clean_list(self.cuisines, "cuisines", None)
        self.meal_types = _clean_list(self.meal_types, "meal_types", ALLOWED_MEAL_TYPES)
        return self


class UserPlace(BaseModel):
    id: uuid.UUID
    kind: Literal["city", "location", "restaurant"]
    name: str
    lat: float
    lon: float
    cuisines: list[str] | None
    meal_types: list[str] | None
    source: Literal["manual_pin", "search_result"]
    search_provider: str | None
    search_ref: str | None
    created_at: datetime
    updated_at: datetime


# -- itineraries -------------------------------------------------------------------------------


class ItemCreate(StrictModel):
    type: Literal["visit", "meal", "free_time"]
    meal_type: MealType | None = None
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
        if self.type == "meal" and self.meal_type is None:
            raise ValueError("a meal needs meal_type")
        if self.type != "meal" and self.meal_type is not None:
            raise ValueError("meal_type is only for meals")
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
    meal_type: MealType | None = None


class Item(BaseModel):
    id: uuid.UUID
    day_id: uuid.UUID
    position: int
    type: Literal["visit", "meal", "free_time"]
    meal_type: MealType | None
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
    reasons: list[str]


class Day(BaseModel):
    id: uuid.UUID
    day_index: int
    date: date | None
    base_city_id: int | None
    items: list[Item]


class ItinerarySummary(BaseModel):
    id: uuid.UUID
    trip_id: uuid.UUID
    profile: Literal["essentials", "wider", "manual"]
    status: Literal["proposed", "selected", "superseded"]
    version: int
    engine_version: str
    config_version: str
    import_run_id: uuid.UUID | None
    created_at: datetime


class Itinerary(ItinerarySummary):
    days: list[Day]
