"""Value types of the planning engine. Plain frozen dataclasses: no database, no clock."""

from dataclasses import dataclass, field
from datetime import date
from typing import Any

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
class PlanRequest:
    destination_name: str
    lat: float
    lon: float
    days: int
    start_date: date | None
    currency_code: str
    # The geo.import_run the candidates came from: the data version stored on the itinerary.
    data_version: str | None

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
    """The transfer from a visit to the next one of the same day."""

    mode: Mode
    seconds: int
    meters: int
    minutes: int  # what the schedule reserves: seconds rounded up to whole minutes
    confidence: Confidence
    estimate_reason: EstimateReason | None


@dataclass(frozen=True)
class PlannedVisit:
    place_id: str
    name: str
    category: str
    lat: float
    lon: float
    start_minute: int
    end_minute: int
    duration_minutes: int
    reasons: tuple[str, ...]
    transfer: Leg | None  # to the next visit of the day; None for the last one


@dataclass(frozen=True)
class DayPlan:
    day_index: int
    date: date | None
    visits: tuple[PlannedVisit, ...]


@dataclass(frozen=True)
class PlanStats:
    visits: int
    days_with_visits: int
    visit_minutes: int
    travel_minutes: int
    travel_seconds: int
    routed_transfers: int
    estimated_transfers: int
    # Planned minutes (visits and transfers) as permille of the day window of all days.
    day_utilisation_permille: int
    # Transfer minutes as permille of planned minutes.
    travel_share_permille: int


@dataclass(frozen=True)
class Plan:
    profile: ProfileName
    days: tuple[DayPlan, ...]
    notes: tuple[Note, ...]
    stats: PlanStats

    def place_ids(self) -> frozenset[str]:
        return frozenset(v.place_id for d in self.days for v in d.visits)


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
