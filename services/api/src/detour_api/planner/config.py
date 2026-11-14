"""The planner's versioned configuration (ADR 014, ADR 016).

Everything the engine weighs is here, as integers, so a plan never depends on floating point
rounding: the day window, the walking threshold, the two strategy profiles, the notability and
category points, the diversity gate, the meal windows and meal lengths, and the rules for base
cities of an area. ``CONFIG_VERSION`` is stored on every itinerary; change it
whenever a value below (or the duration table) changes, and regenerate the golden files.

None of these numbers is a fact about a place. They are planning choices, to be tuned with the
owner on real destinations (app plan, Phase 4 risks).
"""

from dataclasses import dataclass, field
from typing import Literal

from detour_api.planner.durations import DURATIONS_VERSION

ENGINE_VERSION = "planner-2.0.0"
CONFIG_VERSION = f"2026-11-14.2+durations-{DURATIONS_VERSION}"

ProfileName = Literal["essentials", "wider"]
MealType = Literal["breakfast", "lunch", "dinner", "snack"]
MEAL_TYPES: tuple[MealType, ...] = ("breakfast", "lunch", "snack", "dinner")  # in time order


@dataclass(frozen=True)
class MealWindow:
    """When a meal of this type may take place: it starts at or after ``start_minute`` and ends
    by ``end_minute`` (minutes after midnight, local time at the destination)."""

    meal_type: MealType
    start_minute: int
    end_minute: int


@dataclass(frozen=True)
class Profile:
    """One strategy of the engine (architecture section 5.3)."""

    name: ProfileName
    # Candidates farther than this from the destination point are not used.
    radius_m: int
    # Every item of the day (visits, meals, transfers) ends by this time (minutes after midnight).
    day_end_minute: int
    # Value units (tenths of a point) one minute of travel costs. Higher means compact days and
    # less travel: 10 means a 20-point sight is worth at most 20 minutes of travel.
    travel_weight: int
    # Percent of a place's value kept at the radius edge (100 % at the destination point,
    # linear in between).
    edge_value_pct: int
    # Percent of value kept by the 1st, 2nd, 3rd, ... place of the same category (the last entry
    # repeats). Steeper means more variety of categories.
    repeat_category_pct: tuple[int, ...]
    # The meals placed on every day with visits, in time order (a subset of MEAL_TYPES).
    # Breakfast is not placed by default: the day starts at the first visit, after breakfast,
    # because accommodation is not modelled (product brief section 9).
    meals: tuple[MealType, ...] = ("lunch", "dinner")
    # Minutes of each day the sequencer leaves unplanned, so days are not packed edge to edge
    # (KPI: planned time 60-90 % of the day window). Lunch is aimed at 13:00 and dinner at 20:00
    # (owner request, 2026-11-14), so the day runs to 22:00; the 90 and 60 minutes this added to
    # Essentials and Wider are kept here, leaving the sightseeing volume as it was.
    free_minutes: int = 60
    # Area destinations: one base city per this many days (rounded up). Fewer bases means fewer
    # moves; more bases means more cities.
    days_per_base: int = 4


ESSENTIALS = Profile(
    name="essentials",
    radius_m=5_000,
    day_end_minute=22 * 60,
    travel_weight=10,
    edge_value_pct=50,
    repeat_category_pct=(100, 85, 70, 60),
    meals=("lunch", "dinner"),
    free_minutes=150,
    days_per_base=4,
)

WIDER = Profile(
    name="wider",
    radius_m=15_000,
    day_end_minute=22 * 60,
    travel_weight=4,
    edge_value_pct=85,
    repeat_category_pct=(100, 60, 40, 30),
    meals=("lunch", "snack", "dinner"),
    free_minutes=150,
    days_per_base=3,
)


@dataclass(frozen=True)
class PlannerConfig:
    version: str = CONFIG_VERSION
    # The day window (architecture section 5.1). Days start at the first visit (no accommodation,
    # product brief section 9). The validator holds every item inside it.
    day_start_minute: int = 9 * 60
    day_window_end_minute: int = 22 * 60
    # A transfer up to this straight-line distance is walked, a longer one driven.
    walk_max_m: int = 2_000
    # How many candidates a profile plans with: base + per_day x days, at most cap.
    max_candidates_base: int = 20
    max_candidates_per_day: int = 12
    max_candidates_cap: int = 150
    # The sparse cell set (ADR 013): each candidate against this many nearest others.
    neighbours: int = 6
    # A visit counts as "near the previous item" up to this transfer time.
    near_previous_minutes: int = 10
    # A visit counts as "near the centre" up to this distance from the destination point.
    near_centre_m: int = 1_500
    # Diversity gate (product brief section 5): Jaccard similarity of the visit sets at most
    # max_jaccard_num / max_jaccard_den.
    max_jaccard_num: int = 3
    max_jaccard_den: int = 5
    # Re-solves of the second profile when the gate fails: percent of value kept by the visits
    # the first profile already has. 0 excludes them.
    diversity_rounds_pct: tuple[int, ...] = (50, 20, 0)
    # The second variant counts as a real alternative only with at least this percentage of the
    # first variant's number of visits; otherwise one plan is shown.
    min_second_variant_pct: int = 50
    # No randomness is used; the field is stored on every itinerary as the determinism rules ask.
    seed: int = 0
    profiles: tuple[Profile, ...] = (ESSENTIALS, WIDER)
    # Value points (scoring.py). Notability: OSM tags that link to Wikidata, Wikipedia or a
    # heritage listing, and the tourism=attraction tag.
    base_points: int = 10
    # A candidate's value is its points times this (so travel weights can be fine-grained).
    value_scale: int = 10
    notability_points: dict[str, int] = field(
        default_factory=lambda: {
            "has_wikidata": 30,
            "has_wikipedia": 20,
            "has_heritage": 20,
            "tourism_attraction": 10,
        }
    )
    # Wikidata sitelink count, when the import has it (not fetched yet: data-model section 2.8):
    # (at least this many sitelinks, points), first match wins.
    sitelink_points: tuple[tuple[int, int], ...] = ((50, 30), (20, 20), (5, 10))
    default_category_points: int = 10
    category_points: dict[str, int] = field(
        default_factory=lambda: {
            "museum": 30,
            "castle": 30,
            "palace": 30,
            "archaeological_site": 25,
            "attraction": 20,
            "gallery": 20,
            "zoo": 20,
            "aquarium": 20,
            "theme_park": 15,
            "viewpoint": 20,
            "fortress": 20,
            "fort": 15,
            "ruins": 15,
            "monastery": 20,
            "abbey": 20,
            "church": 15,
            "temple": 20,
            "city_gate": 15,
            "tower": 15,
            "aqueduct": 15,
            "monument": 10,
            "chapel": 5,
            "statue": 5,
            "fountain": 5,
            "memorial": 5,
        }
    )
    # Categories at or above this many points count as a "highlight" category (a reason code).
    highlight_category_points: int = 25

    # -- meals (ADR 016) ---------------------------------------------------------------------
    # Fixed windows by meal type. A meal starts inside its window and ends by its end (and by the
    # profile's day end). Opening hours are not known (ADR 003): a window is a planning choice.
    meal_windows: tuple[MealWindow, ...] = (
        MealWindow("breakfast", 7 * 60 + 30, 10 * 60),
        MealWindow("lunch", 13 * 60, 15 * 60),
        MealWindow("snack", 15 * 60, 17 * 60 + 30),
        MealWindow("dinner", 20 * 60, 22 * 60),
    )
    # Meal length in minutes by (meal type, venue type). The venue types are the ones the import
    # stores (geo.restaurant_profile.venue_type); another venue type takes the meal type's
    # default below.
    meal_minutes_by_venue: dict[tuple[str, str], int] = field(
        default_factory=lambda: {
            ("breakfast", "cafe"): 30,
            ("snack", "cafe"): 30,
            ("lunch", "restaurant"): 60,
            ("dinner", "restaurant"): 90,
        }
    )
    meal_minutes_default: dict[str, int] = field(
        default_factory=lambda: {"breakfast": 30, "lunch": 60, "snack": 30, "dinner": 90}
    )
    # Time the sequencer keeps free per meal for walking to and from the place to eat.
    meal_allowance_minutes: int = 15
    # Places to eat are looked for within these distances of the route (straight line), nearest
    # ring first; none within the last ring means the meal is not planned (and a note says so).
    meal_search_m: tuple[int, ...] = (600, 1_500, 3_000)
    # Choosing among the places in a ring, by the detour they add in metres plus these penalties:
    # a cuisine the plan already has, and a cuisine the data does not state (it may repeat one).
    cuisine_repeat_penalty_m: int = 400
    unknown_cuisine_penalty_m: int = 150

    # -- area destinations (ADR 016) -----------------------------------------------------------
    # A town of the area can be a base city if at least this many named sights lie within this
    # distance of it.
    base_sight_radius_m: int = 5_000
    min_base_sights: int = 3
    # Bases are at least this far apart (straight line), at most this many per plan.
    min_base_separation_m: int = 20_000
    max_bases: int = 6
    # Population points of a base: population // this, at most the cap (unknown population: 0).
    # About one sight's worth of points per 40,000 people.
    base_population_divisor: int = 1_000
    base_population_cap: int = 1_000
    # Countries planned as single-city trips only: travel between Japanese cities is mostly by
    # rail, which the planner does not model yet (app plan D4).
    single_city_countries: tuple[str, ...] = ("JP",)

    def profile(self, name: ProfileName) -> Profile:
        for p in self.profiles:
            if p.name == name:
                return p
        raise KeyError(name)

    def max_candidates(self, days: int) -> int:
        return min(
            self.max_candidates_cap, self.max_candidates_base + self.max_candidates_per_day * days
        )

    def day_minutes(self, profile: Profile) -> int:
        return profile.day_end_minute - self.day_start_minute

    def meal_window(self, meal_type: str) -> MealWindow:
        for w in self.meal_windows:
            if w.meal_type == meal_type:
                return w
        raise KeyError(meal_type)

    def meal_minutes(self, meal_type: str, venue_type: str | None) -> int:
        if venue_type is not None and (meal_type, venue_type) in self.meal_minutes_by_venue:
            return self.meal_minutes_by_venue[(meal_type, venue_type)]
        return self.meal_minutes_default[meal_type]

    def meal_reserve(self, profile: Profile) -> int:
        """Minutes of a day the sequencer keeps for the profile's meals."""
        return sum(
            self.meal_minutes_default[m] + self.meal_allowance_minutes for m in profile.meals
        )

    def visit_budget(self, profile: Profile) -> int:
        """Minutes of a day for visits and the transfers between them."""
        return max(0, self.day_minutes(profile) - self.meal_reserve(profile) - profile.free_minutes)


DEFAULT_CONFIG = PlannerConfig()
