"""Models for adding a restaurant or cafe (ADR 019, narrowed by ADR 026): search through Photon.

Restaurants and cafes are not imported. The provider gives a name, a point, the OpenStreetMap key
and value and an address; nothing else is stored or shown (no cuisine, no meal types).
"""

from typing import Literal

from pydantic import BaseModel, Field

from detour_api.models.search import ExternalPlace
from detour_api.models.trips import UserPlace


class ExternalRestaurant(ExternalPlace):
    """A restaurant or cafe from the external provider (Photon). Not part of our data: save it as
    a user place (kind restaurant or cafe, source search_result) to add it to a plan."""

    venue_type: Literal["restaurant", "cafe"] = Field(
        description="From the OpenStreetMap amenity value; also the kind to save it as"
    )


class ExternalRestaurantStatus(BaseModel):
    state: Literal[
        "not_requested", "not_needed", "ok", "cached", "unavailable", "budget_exhausted", "disabled"
    ] = Field(
        description="not_requested: include_external was false. not_needed: your saved places "
        "match. unavailable, budget_exhausted and disabled: no external results; you can always "
        "enter the place by hand (a name, a kind and a map pin)."
    )
    provider: Literal["photon"] | None = None
    results: list[ExternalRestaurant] = Field(default_factory=list)


class RestaurantSearchResponse(BaseModel):
    query: str
    your_places: list[UserPlace] = Field(
        description="Restaurants and cafes you saved before whose name matches"
    )
    external: ExternalRestaurantStatus
