"""The planner's versioned configuration (ADR 014).

Everything the engine weighs is here, as integers, so a plan never depends on floating point
rounding: the day window, the walking threshold, the two strategy profiles, the notability and
category points, and the diversity gate. ``CONFIG_VERSION`` is stored on every itinerary; change it
whenever a value below (or the duration table) changes, and regenerate the golden files.

None of these numbers is a fact about a place. They are planning choices, to be tuned with the
owner on real destinations (app plan, Phase 4 risks).
"""

from dataclasses import dataclass, field
from typing import Literal

from detour_api.planner.durations import DURATIONS_VERSION

ENGINE_VERSION = "planner-1.0.0"
CONFIG_VERSION = f"2026-11-12.2+durations-{DURATIONS_VERSION}"

ProfileName = Literal["essentials", "wider"]


@dataclass(frozen=True)
class Profile:
    """One strategy of the engine (architecture section 5.3)."""

    name: ProfileName
    # Candidates farther than this from the destination point are not used.
    radius_m: int
    # Visits and transfers end by this time (minutes after midnight); the rest of the day window
    # is left free (meals arrive in Phase 6).
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


ESSENTIALS = Profile(
    name="essentials",
    radius_m=5_000,
    day_end_minute=18 * 60,
    travel_weight=10,
    edge_value_pct=50,
    repeat_category_pct=(100, 85, 70, 60),
)

WIDER = Profile(
    name="wider",
    radius_m=15_000,
    day_end_minute=19 * 60,
    travel_weight=4,
    edge_value_pct=85,
    repeat_category_pct=(100, 60, 40, 30),
)


@dataclass(frozen=True)
class PlannerConfig:
    version: str = CONFIG_VERSION
    # The day window (architecture section 5.1). Days start at the first visit (no accommodation,
    # product brief section 9). The validator holds every item inside it.
    day_start_minute: int = 9 * 60
    day_window_end_minute: int = 21 * 60
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


DEFAULT_CONFIG = PlannerConfig()
