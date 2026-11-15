"""Value types of the planning engine. Plain frozen dataclasses: no database, no clock."""

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from detour_api.planner.config import ProfileName
from detour_api.travel.types import Confidence, Coord, EstimateReason, Mode

# Parameters of a note: only what a fixed template needs, all JSON-safe.
NoteParams = dict[str, int | str | list[int]]


@dataclass(frozen=True)
class Candidate:
    """An imported attraction the engine may plan. Everything here comes from ``geo``; a value the
    data does not have is ``None`` (unknown), never a guess."""

    place_id: str
    name: str
    category: str
    lat: float
    lon: float
    # The OSM-derived signal flags of geo.place_signal (has_wikidata, has_wikipedia, ...); empty
    # when the place has no signal row.
    signals: dict[str, Any] = field(default_factory=dict)
    sitelink_count: int | None = None

    @property
    def coord(self) -> Coord:
        return Coord.from_degrees(self.lat, self.lon)


@dataclass(frozen=True)
class BaseCity:
    """A gazetteer city (``geo.city``): the destination of a city trip, or a possible base of an
    area trip."""

    city_id: int
    name: str
    lat: float
    lon: float
    population: int | None = None

    @property
    def coord(self) -> Coord:
        return Coord.from_degrees(self.lat, self.lon)


@dataclass(frozen=True)
class RouteStop:
    """A stop of a multi-city trip (ADR 024): a city the user chose, with its days."""

    city: BaseCity
    days: int
    country_iso2: str | None


@dataclass(frozen=True)
class StayPoint:
    """Where the traveller sleeps on days ``first_day`` to ``last_day`` (ADR 030)."""

    first_day: int
    last_day: int
    coord: Coord


@dataclass(frozen=True)
class PlanRequest:
    destination_name: str
    lat: float
    lon: float
    days: int
    start_date: date | None
    # The geo.import_run the candidates came from: the data version stored on the itinerary.
    data_version: str | None
    # "city": ``base_cities`` holds the destination city alone. "area": the towns of the area
    # that may become bases (the engine chooses among them). "route": ``stops`` are the user's
    # cities in order with their days (ADR 024); the engine neither chooses nor reorders them.
    kind: Literal["city", "area", "route"] = "city"
    base_cities: tuple[BaseCity, ...] = ()
    stops: tuple[RouteStop, ...] = ()
    # Where each day starts: the stay of its day, when it has one (ADR 030).
    stays: tuple[StayPoint, ...] = ()

    @property
    def centre(self) -> Coord:
        return Coord.from_degrees(self.lat, self.lon)


@dataclass(frozen=True)
class Note:
    """A plan-level explanation: a code rendered through a fixed template (reasons.py)."""

    code: str
    params: NoteParams = field(default_factory=dict)


@dataclass(frozen=True)
class Leg:
    """A transfer: from an item to the next one of the same day, or, for the first day at a new
    base city, from the previous base city."""

    mode: Mode
    seconds: int
    meters: int
    minutes: int  # what the schedule reserves: seconds rounded up to whole minutes
    confidence: Confidence
    estimate_reason: EstimateReason | None


@dataclass(frozen=True)
class PlannedItem:
    """A visit to an attraction or a meal at a place to eat."""

    kind: Literal["visit", "meal"]
    place_id: str
    name: str
    # Visits: the attraction's category. Meals: the venue type (restaurant, cafe).
    category: str
    lat: float
    lon: float
    start_minute: int
    end_minute: int
    duration_minutes: int
    reasons: tuple[str, ...]
    transfer: Leg | None  # to the next item of the day; None for the last one


@dataclass(frozen=True)
class DayPlan:
    day_index: int
    date: date | None
    items: tuple[PlannedItem, ...]
    base_city_id: int | None = None
    base_city_name: str | None = None
    # Travel from the previous day's base city, at the start of the day; None when the base
    # does not change.
    arrival: Leg | None = None
    # The base changed but the journey's time is not known (a leg into or out of a country
    # travelled by rail, ADR 024): no time is invented and the day is planned in full.
    arrival_unknown: bool = False

    @property
    def visits(self) -> tuple[PlannedItem, ...]:
        return tuple(i for i in self.items if i.kind == "visit")

    @property
    def meals(self) -> tuple[PlannedItem, ...]:
        return tuple(i for i in self.items if i.kind == "meal")


@dataclass(frozen=True)
class PlanStats:
    visits: int
    days_with_visits: int
    visit_minutes: int
    travel_minutes: int
    travel_seconds: int
    routed_transfers: int
    estimated_transfers: int
    # Planned minutes (visits, meals, transfers and inter-city travel) as permille of the day
    # window of all days.
    day_utilisation_permille: int
    # Transfer and inter-city minutes as permille of planned minutes.
    travel_share_permille: int
    meals: int = 0
    meal_minutes: int = 0
    # Inter-city legs (area trips); their minutes are part of travel_minutes, and their labels
    # are counted in routed_transfers and estimated_transfers.
    intercity_legs: int = 0


@dataclass(frozen=True)
class Plan:
    profile: ProfileName
    days: tuple[DayPlan, ...]
    notes: tuple[Note, ...]
    stats: PlanStats

    def place_ids(self) -> frozenset[str]:
        """The visits of the plan (meals do not count for the diversity gate)."""
        return frozenset(v.place_id for d in self.days for v in d.visits)

    def allocation(self) -> tuple[tuple[int | None, int], ...]:
        """Base cities in visiting order, each with its number of consecutive days."""
        out: list[tuple[int | None, int]] = []
        for d in self.days:
            if out and out[-1][0] == d.base_city_id:
                out[-1] = (d.base_city_id, out[-1][1] + 1)
            else:
                out.append((d.base_city_id, 1))
        return tuple(out)


@dataclass(frozen=True)
class Generation:
    """The engine's answer: one or two plans, and how they compare."""

    engine_version: str
    config_version: str
    data_version: str | None
    seed: int
    plans: tuple[Plan, ...]
    # Jaccard similarity of the two plans' visit sets as permille; None with a single plan.
    jaccard_permille: int | None
    distinct: bool
    notes: tuple[Note, ...]


@dataclass(frozen=True)
class Issue:
    """Why a plan cannot be made at all."""

    code: str
    params: NoteParams = field(default_factory=dict)


class PlanningImpossible(Exception):
    def __init__(self, issues: list[Issue]) -> None:
        super().__init__(", ".join(i.code for i in issues))
        self.issues = issues


class PlanInvalid(Exception):
    """The independent validator rejected a generated plan: a bug, never shown as a plan."""

    def __init__(self, profile: str, violations: list[Any]) -> None:
        super().__init__(f"{profile}: {violations}")
        self.profile = profile
        self.violations = violations
