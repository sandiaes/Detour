"""The planner's versioned configuration (ADR 014, ADR 016).

Everything the engine weighs is here, as integers, so a plan never depends on floating point
rounding: the day window, the walking threshold, the two strategy profiles, the notability and
category points, the diversity gate, the midday gap, and the rules for base cities of an area.
Generated plans contain sights only (ADR 026): no meals, no places to eat; each day with visits
keeps one unplanned stretch around midday instead. ``CONFIG_VERSION`` is stored on every
itinerary; change it whenever a value below (or the duration table) changes, and regenerate the
golden files.

None of these numbers is a fact about a place. They are planning choices, to be tuned with the
owner on real destinations (app plan, Phase 4 risks).
"""

from dataclasses import dataclass, field
from typing import Literal

from detour_api.planner.durations import DURATIONS_VERSION

ENGINE_VERSION = "planner-3.0.0"
CONFIG_VERSION = f"2026-11-14.3+durations-{DURATIONS_VERSION}"

ProfileName = Literal["essentials", "wider"]


@dataclass(frozen=True)
class MiddayGap:
    """One unplanned stretch a day (ADR 026, item 5). It starts at ``earliest_start`` or when the
    traveller reaches the next stop, whichever is later, and lasts ``minutes``; the next stop is
    done first only if that does not push the gap's start past ``latest_start``. It names no place
    and no meal and is not stored as an item: it is only time between two stops (minutes after
    midnight, local time)."""

    earliest_start: int = 12 * 60 + 30
    latest_start: int = 14 * 60
    minutes: int = 90


@dataclass(frozen=True)
class Profile:
    """One strategy of the engine (architecture section 5.3)."""

    name: ProfileName
    # Candidates farther than this from the destination point are not used.
    radius_m: int
    # Every visit of the day, with its transfers, ends by this time (minutes after midnight).
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
    # Minutes of each day the sequencer leaves unplanned besides the midday gap, so days are not
    # packed edge to edge (KPI: planned time 60-90 % of the day window). With the 09:00-20:00 window
    # and the 90-minute gap these keep the sightseeing volume (the visit budget) at what it was
    # before ADR 026: 450 minutes for Essentials, 405 for Wider.
    free_minutes: int = 120
    # Area destinations: one base city per this many days (rounded up). Fewer bases means fewer
    # moves; more bases means more cities.
    days_per_base: int = 4


ESSENTIALS = Profile(
    name="essentials",
    radius_m=5_000,
    day_end_minute=20 * 60,
    travel_weight=10,
    edge_value_pct=50,
    repeat_category_pct=(100, 85, 70, 60),
    free_minutes=120,
    days_per_base=4,
)

WIDER = Profile(
    name="wider",
    radius_m=15_000,
    day_end_minute=20 * 60,
    travel_weight=4,
    edge_value_pct=85,
    repeat_category_pct=(100, 60, 40, 30),
    free_minutes=165,
    days_per_base=3,
)


@dataclass(frozen=True)
class PlannerConfig:
    version: str = CONFIG_VERSION
    # The day window (architecture section 5.1). Days start at the first visit (no accommodation,
    # product brief section 9). The validator holds every item inside it.
    day_start_minute: int = 9 * 60
    day_window_end_minute: int = 20 * 60
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

    # -- the midday gap (ADR 026) ----------------------------------------------------------------
    midday_gap: MiddayGap = field(default_factory=MiddayGap)

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

    def visit_budget(self, profile: Profile) -> int:
        """Minutes of a day for visits and the transfers between them."""
        return max(0, self.day_minutes(profile) - self.midday_gap.minutes - profile.free_minutes)


DEFAULT_CONFIG = PlannerConfig()
