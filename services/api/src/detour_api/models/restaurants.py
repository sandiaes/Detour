"""Models for adding a restaurant (Phase 8, ADR 019): restaurant search, slot suggestions."""

import uuid
from datetime import time
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from detour_api.models.common import StrictModel
from detour_api.models.search import ExternalPlace, PlaceSummary
from detour_api.models.trips import MealType, UserPlace


class RestaurantResult(PlaceSummary):
    """An imported place to eat. ``cuisines`` null means the data states none: shown as
    "Cuisine not specified"."""

    meal_types: list[MealType] | None = Field(
        default=None, description="Derived from the venue type by the import's fixed rule"
    )


class ExternalRestaurant(ExternalPlace):
    """A restaurant or café from the external provider (Photon). Not part of our data: save it as
    a user place (kind restaurant, source search_result) to add it to a plan. The provider gives
    no cuisine, so it is not specified unless you give one."""

    venue_type: Literal["restaurant", "cafe"]
    meal_types: list[MealType] = Field(
        description="From the venue type by the same fixed rule as imported places: a restaurant "
        "serves lunch and dinner, a café breakfast and a snack. You can change them."
    )
    meal_types_basis: Literal["venue_type"] = "venue_type"
    cuisines: list[str] | None = Field(
        default=None, description="Always null: the provider's answer carries none"
    )


class ExternalRestaurantStatus(BaseModel):
    state: Literal[
        "not_requested", "not_needed", "ok", "cached", "unavailable", "budget_exhausted", "disabled"
    ] = Field(
        description="not_requested: include_external was false. not_needed: there are local or "
        "own results. unavailable, budget_exhausted and disabled: no external results; you can "
        "always enter the restaurant by hand (a name and a map pin)."
    )
    provider: Literal["photon"] | None = None
    results: list[ExternalRestaurant] = Field(default_factory=list)


class RestaurantSearchResponse(BaseModel):
    query: str
    results: list[RestaurantResult] = Field(description="Imported places to eat, searched first")
    your_places: list[UserPlace] = Field(
        description="Restaurants you saved before (kind restaurant) whose name matches"
    )
    external: ExternalRestaurantStatus


class SlotRequest(StrictModel):
    """Suggest where a restaurant fits in a planned itinerary."""

    place_id: uuid.UUID | None = Field(default=None, description="An imported place to eat")
    user_place_id: uuid.UUID | None = Field(
        default=None, description="One of your restaurants (kind restaurant)"
    )
    day: int | None = Field(default=None, ge=1, le=60, description="Only this day")
    meal_type: MealType | None = Field(default=None, description="Only this meal")

    @model_validator(mode="after")
    def _one_place(self) -> Self:
        if (self.place_id is None) == (self.user_place_id is None):
            raise ValueError("give exactly one of place_id and user_place_id")
        return self


class SlotReason(BaseModel):
    code: str
    text: str


class MovedItem(BaseModel):
    kind: Literal["visit", "meal"]
    name: str
    old_start_time: time
    new_start_time: time


class SlotSuggestion(BaseModel):
    rank: int = Field(description="1 is the best slot")
    day: int
    meal_type: MealType
    start_time: time
    end_time: time
    after_item_id: uuid.UUID | None = Field(
        description="Pass this, with day and meal_type, to the change-set preview to place the "
        "meal here. Null: first in the day"
    )
    after_name: str | None = Field(description="The stop before the meal; null: first of the day")
    before_name: str | None = Field(description="The stop after the meal; null: last of the day")
    travel_minutes_added: int = Field(
        description="Travel the day gains (negative: less). Estimated from the cache and "
        "straight-line distance, not routed, unless travel_label says routed"
    )
    travel_label: Literal["routed", "estimated"]
    detour_metres: int = Field(
        description="Straight-line detour from the stops before and after the meal"
    )
    replaces: str | None = Field(description="The meal of this type the plan has now, replaced")
    items_moved: list[MovedItem] = Field(description="Other items that start at another time")
    reasons: list[SlotReason]
    score: int = Field(description="Lower is better; ties go to the earlier day, then the start")


class SlotRestaurant(BaseModel):
    name: str
    venue_type: str | None
    cuisines: list[str] | None = Field(description="Null: Cuisine not specified")
    meal_types: list[MealType] | None = Field(description="Null: not known")
    meal_types_basis: Literal["venue_type", "you", "unknown"]


class SlotSuggestions(BaseModel):
    restaurant: SlotRestaurant
    suggestions: list[SlotSuggestion] = Field(description="At most three, best first")
    slots_considered: int = Field(description="Day and meal combinations that could be tried")
    issues: list[SlotReason] = Field(description="Why there is nothing to suggest, when empty")
