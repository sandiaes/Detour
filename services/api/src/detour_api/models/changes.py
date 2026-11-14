"""Models for change sets (preview, apply, discard) and itinerary versions (Phase 7, ADR 018)."""

import uuid
from datetime import datetime, time
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from detour_api.models.common import StrictModel
from detour_api.models.trips import Itinerary, MealType, PlanNote, StopIn


class ChangeSetCreate(StrictModel):
    """Preview adding a place (an imported attraction, or one of your own places of kind city or
    location), adding a restaurant to a meal slot, or removing a visit. Nothing changes until the
    change set is applied."""

    action: Literal["add_place", "remove_place", "add_restaurant"]
    place_id: uuid.UUID | None = Field(
        default=None,
        description="add_place: an imported attraction. add_restaurant: an imported place to eat",
    )
    user_place_id: uuid.UUID | None = Field(
        default=None,
        description="add_place: one of your places (kind city or location). add_restaurant: one "
        "of your restaurants (kind restaurant)",
    )
    duration_minutes: int | None = Field(
        default=None,
        ge=5,
        le=720,
        description="add_place: how long to stay. Required for your own places; for an "
        "attraction the category's default length is used when it is not given",
    )
    item_id: uuid.UUID | None = Field(default=None, description="remove_place: the visit to remove")
    day: int | None = Field(
        default=None,
        ge=1,
        le=60,
        description="add_restaurant: the day (a suggestion's day). add_place: optional, only this "
        "day is tried (a place suggestion's day); without it the day that costs the plan least",
    )
    meal_type: MealType | None = Field(
        default=None, description="add_restaurant: the meal (a suggestion's meal_type)"
    )
    after_item_id: uuid.UUID | None = Field(
        default=None,
        description="add_restaurant: the visit (or meal you fixed) the meal follows, as a "
        "suggestion gives it; null puts the meal first in the day",
    )

    @model_validator(mode="after")
    def _shape(self) -> Self:
        slot = self.day is not None or self.meal_type is not None or self.after_item_id is not None
        if self.action == "remove_place":
            if self.item_id is None:
                raise ValueError("remove_place needs item_id")
            if self.place_id or self.user_place_id or self.duration_minutes or slot:
                raise ValueError("remove_place takes item_id only")
            return self
        if (self.place_id is None) == (self.user_place_id is None):
            raise ValueError(f"{self.action} needs exactly one of place_id and user_place_id")
        if self.item_id is not None:
            raise ValueError("item_id is only for remove_place")
        if self.action == "add_place":
            if self.meal_type is not None or self.after_item_id is not None:
                raise ValueError("meal_type and after_item_id are only for add_restaurant")
        else:
            if self.day is None or self.meal_type is None:
                raise ValueError("add_restaurant needs day and meal_type")
            if self.duration_minutes is not None:
                raise ValueError("a meal's length follows its meal type and venue")
        return self


class DiffItem(BaseModel):
    day: int
    kind: Literal["visit", "meal"]
    name: str
    meal_type: MealType | None
    start_time: time
    end_time: time
    added_by_you: bool = Field(description="True for the place you add (and places you added)")


class DiffMove(BaseModel):
    kind: Literal["visit", "meal"]
    name: str
    from_day: int
    to_day: int
    old_start_time: time
    new_start_time: time


class DiffRetime(BaseModel):
    kind: Literal["visit", "meal"]
    name: str
    day: int
    meal_type: MealType | None
    old_start_time: time
    new_start_time: time


class DiffBase(BaseModel):
    day: int
    old_base_name: str | None
    new_base_name: str | None


class DiffLeg(BaseModel):
    day: int
    from_name: str
    to_name: str
    mode: Literal["walk", "drive"]
    minutes: int


class ChangeDiff(BaseModel):
    """What applying the change set does to the plan."""

    added: list[DiffItem]
    removed: list[DiffItem] = Field(description="Items no longer in the plan (left out or removed)")
    moved: list[DiffMove] = Field(description="Visits that change day")
    retimed: list[DiffRetime] = Field(description="Items on the same day at another time")
    base_changes: list[DiffBase] = Field(description="Days planned from another base city")
    days_changed: list[int]
    travel_minutes_before: int
    travel_minutes_after: int
    travel_minutes_added: int = Field(description="Negative when the plan travels less")
    estimated_legs: list[DiffLeg] = Field(
        description="Travel times in the changed days that are straight-line estimates, not routed"
    )


class ChangeSet(BaseModel):
    id: uuid.UUID
    itinerary_id: uuid.UUID
    action: Literal["add_place", "remove_place", "add_restaurant", "edit_stops"]
    target_name: str
    status: Literal["pending", "applied", "discarded", "expired"] = Field(
        description="pending: previewed, nothing changed yet. expired: the itinerary changed "
        "after the preview (or a newer preview was made); preview again"
    )
    base_version: int = Field(description="The itinerary version the preview was made from")
    restores_version: int | None = Field(
        description="Set when applying restores an earlier version exactly (removing a place "
        "right after adding it)"
    )
    result_version: int | None = Field(description="The version created by applying it")
    diff: ChangeDiff
    notes: list[PlanNote]
    created_at: datetime
    decided_at: datetime | None


class ChangeSetApplied(BaseModel):
    change_set: ChangeSet
    itinerary: Itinerary


class ItineraryVersion(BaseModel):
    version: int
    replaced_at: datetime
    change_set_id: uuid.UUID | None = Field(description="Null when a hand edit replaced it")
    action: Literal["add_place", "remove_place", "add_restaurant", "edit_stops"] | None
    target_name: str | None


class PlaceSuggestionRequest(StrictModel):
    """Where a place could go in a planned itinerary (ADR 021): the same place as an add_place
    change set, without a day."""

    place_id: uuid.UUID | None = Field(default=None, description="An imported attraction")
    user_place_id: uuid.UUID | None = Field(
        default=None, description="One of your places (kind city or location)"
    )
    duration_minutes: int | None = Field(
        default=None,
        ge=5,
        le=720,
        description="How long to stay. Required for your own places; for an attraction the "
        "category's default length is used when it is not given",
    )

    @model_validator(mode="after")
    def _shape(self) -> Self:
        if (self.place_id is None) == (self.user_place_id is None):
            raise ValueError("give exactly one of place_id and user_place_id")
        return self


class SuggestionReason(BaseModel):
    code: str
    text: str = Field(description="The code rendered through its fixed template")


class PlaceSuggestion(BaseModel):
    rank: int = Field(description="1 is the best day")
    day: int = Field(description="Pass it as day to the add_place preview to place it here")
    start_time: time
    end_time: time
    after_name: str | None = Field(description="The stop before it; null: first of the day")
    before_name: str | None = Field(description="The stop after it; null: last of the day")
    new_base_name: str | None = Field(
        description="Set when the day would be planned from another base city near the place"
    )
    travel_minutes_added: int = Field(
        description="Travel the plan gains (negative: less), from cached times and labelled "
        "straight-line estimates; the preview asks the routing provider"
    )
    estimated: bool = Field(description="True when some changed travel time is an estimate")
    diff: ChangeDiff = Field(description="What placing it here would change: moves, left out")
    reasons: list[SuggestionReason]


class PlaceSuggestions(BaseModel):
    name: str
    duration_minutes: int
    duration_source: Literal["category_default", "user"]
    suggestions: list[PlaceSuggestion] = Field(description="At most three, best first")
    days_considered: int
    issues: list[SuggestionReason] = Field(
        description="Why no day can take it, when there are no suggestions"
    )


class StopsEdit(StrictModel):
    """A multi-city trip's new stops, in order (ADR 024): add, remove, reorder or change days."""

    stops: list[StopIn] = Field(description="2 to 6 cities; their days become the trip's length")
