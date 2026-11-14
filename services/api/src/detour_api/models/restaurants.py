"""Models for adding a restaurant (Phase 8, ADR 019): restaurant search, slot suggestions."""

from typing import Literal

from pydantic import BaseModel, Field

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
