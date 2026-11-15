"""The planning engine, version 3: sights and days, for a city, an area or a route of cities
(ADR 014, ADR 016, ADR 024; ADR 026 removed the meals).

    1. scope: a city is one base for every day; an area gets base cities per profile, with days
       allocated to them and ordered by inter-city travel time (areas.py)
    2. score each base's candidates for the profile (scoring.py)
    3. read the cached travel times of a sparse cell set: each candidate against its nearest
       others (ADR 013); any other pair is the labelled estimate
    4. solve Essentials, then Wider, base by base, keeping time for the midday gap; if the
       visit sets overlap too much and the bases are the same, solve Wider again with the shared
       visits weighted down (the diversity gate, architecture section 5.3)
    5. lay out each day: visits in order with one unplanned midday gap, no meals (daylayout.py)
    6. ask the travel source for the transfers and inter-city legs the plans actually use (the
       provider is called here, within a time limit, only if ``use_provider``)
    7. lay out again with those times; if a day no longer fits, drop its lowest-value visit
    8. reason codes, notes and statistics; the independent validator checks every plan

Deterministic: candidates and towns are handled in identifier order, every tie is
broken by identifier, there is no randomness and no clock. The only input that can change between
two runs with the same data is what the travel source returns, and every transfer records which
kind of value it is.
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import timedelta
from typing import Any

from detour_api.planner import areas, scoring
from detour_api.planner.config import DEFAULT_CONFIG, ENGINE_VERSION, PlannerConfig, Profile
from detour_api.planner.daylayout import DayLayout, lay_out_day
from detour_api.planner.durations import visit_minutes
from detour_api.planner.reasons import ITEM_TEMPLATES
from detour_api.planner.sequencer import HeuristicSequencer, Sequencer, SequencingProblem
from detour_api.planner.travel import Cell, TravelLookup, TravelSource, minutes
from detour_api.planner.types import (
    Candidate,
    DayPlan,
    Generation,
    Issue,
    Leg,
    Note,
    Plan,
    PlanInvalid,
    PlannedItem,
    PlanningImpossible,
    PlanRequest,
    PlanStats,
    StayPoint,
)
from detour_api.planner.validator import validate_generation, validate_plan
from detour_api.travel.types import Coord, TravelTime

_REASON_ORDER = {code: i for i, code in enumerate(ITEM_TEMPLATES)}
FOLLOW_UP_FETCHES = 2
_GENERAL_NOTES = (
    Note("NOTABILITY_FROM_TAGS"),
    Note("DURATIONS_ARE_DEFAULTS"),
    Note("NO_OPENING_HOURS"),
    Note("SIGHTS_ONLY"),
)

Allocation = tuple[tuple[int | None, int], ...]


def _km(meters: int) -> int:
    return meters // 1000


def _jaccard_ok(a: frozenset[str], b: frozenset[str], config: PlannerConfig) -> bool:
    union = len(a | b)
    if union == 0:
        return False
    return len(a & b) * config.max_jaccard_den <= config.max_jaccard_num * union


def _distinct(
    a: frozenset[str],
    b: frozenset[str],
    alloc_a: Allocation,
    alloc_b: Allocation,
    config: PlannerConfig,
) -> bool:
    """Two visit sets make two plans: both non-empty, overlapping at most the threshold **or**
    dividing the days between different base cities, and the second large enough to be a real
    alternative."""
    return (
        bool(a and b)
        and (_jaccard_ok(a, b, config) or alloc_a != alloc_b)
        and len(b) * 100 >= config.min_second_variant_pct * len(a)
    )


def _alike_stops(first: "_ProfilePlan", second: "_ProfilePlan", config: PlannerConfig) -> list[str]:
    """Stops of a multi-city trip where both plans have at least three visits and still overlap
    more than the gate allows, in stop order (ADR 024, decision 14)."""
    out: list[str] = []
    for a, b in zip(first.segments, second.segments, strict=True):
        va = frozenset(p for r in a.routes for p in r)
        vb = frozenset(p for r in b.routes for p in r)
        if len(va) >= 3 and len(vb) >= 3 and not _jaccard_ok(va, vb, config):
            out.append(a.base_name)
    return out


def _jaccard_permille(a: frozenset[str], b: frozenset[str]) -> int:
    union = len(a | b)
    return 0 if union == 0 else len(a & b) * 1000 // union


class _Pool:
    """One base's scored candidates for one profile, in place-id order."""

    def __init__(self, profile: Profile, scored: list[scoring.Scored]) -> None:
        self.profile = profile
        self.items = sorted(scored, key=lambda s: s.candidate.place_id)
        self.value = {s.candidate.place_id: s.value for s in self.items}
        self.distance = {s.candidate.place_id: s.distance_m for s in self.items}


@dataclass
class _Segment:
    """A base city with a run of consecutive days."""

    base_id: int | None
    base_name: str
    base: Coord
    days: int
    sights: int  # sights within the base radius (for the BASE_CITY note)
    previous: "_Segment | None"
    pool: _Pool
    routes: list[list[str]] = field(default_factory=list)
    # A multi-city leg into or out of a country travelled by rail (ADR 024): the base changes but
    # no travel time is known, so none is used and the first day is planned in full.
    unknown_arrival: bool = False


@dataclass
class _ProfilePlan:
    profile: Profile
    segments: list[_Segment]
    stays: tuple[StayPoint, ...] = ()

    def ids(self) -> frozenset[str]:
        return frozenset(p for s in self.segments for r in s.routes for p in r)

    def allocation(self) -> Allocation:
        return tuple((s.base_id, s.days) for s in self.segments)

    def value(self) -> dict[str, int]:
        return {k: v for s in self.segments for k, v in s.pool.value.items()}


@dataclass(frozen=True)
class _LaidOutDay:
    segment: _Segment
    arrival: TravelTime | None
    arrival_cell: Cell | None
    route: list[str]
    layout: DayLayout
    removed: int
    arrival_unknown: bool = False
    # From the day's stay to its first visit (ADR 030): the day's first visit starts that long
    # after the day does.
    start_cell: Cell | None = None


def generate(
    request: PlanRequest,
    candidates: Sequence[Candidate],
    source: TravelSource,
    *,
    config: PlannerConfig = DEFAULT_CONFIG,
    sequencer: Sequencer | None = None,
    use_provider: bool = False,
) -> Generation:
    if request.days < 1:
        raise ValueError("days must be at least 1")
    sequencer = sequencer or HeuristicSequencer()
    by_id = {c.place_id: c for c in candidates}
    if len(by_id) != len(candidates):
        raise ValueError("duplicate place ids among the candidates")
    lookup = TravelLookup(source, config.walk_max_m)

    eligible: list[areas.EligibleBase] = []
    if request.kind == "area":
        eligible = areas.eligible_bases(request.base_cities, list(by_id.values()), config)
        if not eligible:
            raise PlanningImpossible(
                [
                    Issue(
                        "NO_BASE_CITIES",
                        {
                            "destination": request.destination_name,
                            "min_sights": config.min_base_sights,
                            "radius_km": _km(config.base_sight_radius_m),
                        },
                    )
                ]
            )
    states = [
        _scope(request, profile, by_id, eligible, lookup, config) for profile in config.profiles
    ]
    _check_possible(request, states, config)
    for state in states:
        state.stays = request.stays

    # The sparse cell set of every base's candidates, read from the cache only.
    near: dict[str, list[str]] = {}
    for state in states:
        for seg in state.segments:
            ids = [s.candidate.place_id for s in seg.pool.items]
            for pid, others in scoring.nearest(
                [(pid, by_id[pid].coord) for pid in ids], config.neighbours
            ).items():
                merged = near.setdefault(pid, [])
                merged.extend(o for o in others if o not in merged)
    lookup.fetch(
        ((by_id[a].coord, by_id[b].coord) for a in sorted(near) for b in near[a]),
        use_provider=False,
    )
    if request.stays:
        lookup.fetch(_stay_cells(states, request.stays), use_provider=False)

    first, second = states
    _solve(first, lookup, sequencer, config, {})
    set_first = first.ids()
    _solve(second, lookup, sequencer, config, {})
    initial_jaccard = _jaccard_permille(set_first, second.ids())
    adjusted: int | None = None
    route = request.kind == "route"

    def alike() -> bool:
        whole = not _jaccard_ok(set_first, second.ids(), config)
        return whole or (route and bool(_alike_stops(first, second, config)))

    if set_first and second.ids() and first.allocation() == second.allocation() and alike():
        for pct in config.diversity_rounds_pct:
            adjusted = pct
            _solve(second, lookup, sequencer, config, dict.fromkeys(set_first, pct))
            if not alike():
                break

    distinct = _distinct(set_first, second.ids(), first.allocation(), second.allocation(), config)
    chosen: list[_ProfilePlan]
    if distinct:
        chosen = [first, second]
    elif set_first:
        chosen = [first]
    else:
        chosen = [second]

    if use_provider:
        lookup.fetch(_provider_cells(chosen, by_id, near, lookup, config), use_provider=True)
        # Laying out a day after routing can join two places that were never asked about; ask
        # for those legs too (twice at most; any left over stay labelled estimates).
        for _ in range(FOLLOW_UP_FETCHES):
            missing = sorted(
                {
                    cell
                    for state in chosen
                    for day in _lay_out(state, by_id, lookup, config)
                    for cell in _day_cells(day)
                    if not lookup.answered(*cell)
                }
            )
            if not missing:
                break
            lookup.fetch(missing, use_provider=True)

    small_stops: list[str] = []
    if route and len(chosen) == 2:
        # The bases are fixed, so the plans differ by their visits: the whole plan passes the
        # overlap gate, and a stop where they still share too much is named (ADR 024, decision 14).
        small_stops = _alike_stops(first, second, config)
    plans: list[Plan] = []
    for state in chosen:
        notes: list[Note] = []
        if state is second and adjusted is not None and distinct:
            notes.append(Note("DIVERSITY_ADJUSTED", {"kept_percent": adjusted}))
        plans.append(_build_plan(request, state, by_id, lookup, config, notes))

    general: list[Note] = []
    jaccard: int | None = None
    candidates_count = len(
        {s.candidate.place_id for st in states for g in st.segments for s in g.pool.items}
    )
    if len(plans) == 2:
        a, b = plans[0].place_ids(), plans[1].place_ids()
        alloc_a, alloc_b = plans[0].allocation(), plans[1].allocation()
        jaccard = _jaccard_permille(a, b)
        if not _distinct(a, b, alloc_a, alloc_b, config):
            # Visits dropped after routing made the plans too alike: show one.
            plans = plans[:1]
            general.append(Note("NOT_ENOUGH_DISTINCT_PLACES_AFTER_ROUTING"))
            jaccard = None
        elif _jaccard_ok(a, b, config):
            general.append(
                Note(
                    "DISTINCT_PLANS",
                    {"jaccard_percent": jaccard // 10, "max_percent": _max_percent(config)},
                )
            )
        else:
            general.append(Note("DISTINCT_ALLOCATION"))
    if len(plans) == 2:
        general.extend(Note("STOP_TOO_SMALL_TO_VARY", {"name": name}) for name in small_stops)
    if len(plans) == 1 and not general:
        general.append(
            Note(
                "SINGLE_PLAN",
                {
                    "candidates": candidates_count,
                    "radius_km": _km(max(p.radius_m for p in config.profiles)),
                    "jaccard_percent": initial_jaccard // 10,
                    "max_percent": _max_percent(config),
                },
            )
        )
    generation = Generation(
        engine_version=ENGINE_VERSION,
        config_version=config.version,
        data_version=request.data_version,
        seed=config.seed,
        plans=tuple(plans),
        jaccard_permille=jaccard,
        distinct=len(plans) == 2,
        notes=tuple(general) + _GENERAL_NOTES,
    )
    known = lookup.known()
    for plan in generation.plans:
        violations = validate_plan(plan, request, by_id, known, config)
        if violations:
            raise PlanInvalid(plan.profile, violations)
    problems = validate_generation(generation, config)
    if problems:
        raise PlanInvalid("generation", problems)
    return generation


def _max_percent(config: PlannerConfig) -> int:
    return config.max_jaccard_num * 100 // config.max_jaccard_den


# -- scope -------------------------------------------------------------------------------------


def _scope(
    request: PlanRequest,
    profile: Profile,
    by_id: dict[str, Candidate],
    eligible: list[areas.EligibleBase],
    lookup: TravelLookup,
    config: PlannerConfig,
) -> _ProfilePlan:
    """The profile's bases with their days and scored candidates."""
    if request.kind == "city":
        base = request.base_cities[0] if request.base_cities else None
        scored = scoring.score(
            by_id.values(), request.centre, profile, config, config.max_candidates(request.days)
        )
        segment = _Segment(
            base_id=None if base is None else base.city_id,
            base_name=request.destination_name if base is None else base.name,
            base=request.centre,
            days=request.days,
            sights=len(scored),
            previous=None,
            pool=_Pool(profile, scored),
        )
        return _ProfilePlan(profile, [segment])

    if request.kind == "route":
        return _route_scope(request, profile, by_id, config)

    chosen = areas.choose_bases(eligible, request.days, profile, config)
    lookup.fetch(
        ((a.city.coord, b.city.coord) for a in chosen for b in chosen if a is not b),
        use_provider=False,
    )
    ordered = areas.order_bases(chosen, lookup)
    days = areas.allocate_days(ordered, request.days)
    # Each candidate belongs to its nearest base (ties by base order), within the profile radius.
    assigned: dict[int, list[Candidate]] = {b.city.city_id: [] for b in ordered}
    for c in sorted(by_id.values(), key=lambda c: c.place_id):
        dists = [
            (scoring.centre_distance(c, b.city.coord), i, b.city.city_id)
            for i, b in enumerate(ordered)
        ]
        d, _, city_id = min(dists)
        if d <= profile.radius_m:
            assigned[city_id].append(c)
    segments: list[_Segment] = []
    for b, n in zip(ordered, days, strict=True):
        scored = scoring.score(
            assigned[b.city.city_id], b.city.coord, profile, config, config.max_candidates(n)
        )
        segments.append(
            _Segment(
                base_id=b.city.city_id,
                base_name=b.city.name,
                base=b.city.coord,
                days=n,
                sights=b.sights,
                previous=segments[-1] if segments else None,
                pool=_Pool(profile, scored),
            )
        )
    return _ProfilePlan(profile, segments)


def _route_scope(
    request: PlanRequest,
    profile: Profile,
    by_id: dict[str, Candidate],
    config: PlannerConfig,
) -> _ProfilePlan:
    """The user's stops, in their order, with their days (ADR 024): nothing is chosen or reordered.
    Each candidate belongs to its nearest stop within the profile radius; a city that comes back
    later (Tokyo, Kyoto, Tokyo) shares its candidates between its stops, and a place planned at
    one of them is not planned again (``_solve``)."""
    rail = set(config.single_city_countries)
    stops = request.stops
    assigned: list[list[Candidate]] = [[] for _ in stops]
    for c in sorted(by_id.values(), key=lambda c: c.place_id):
        dists = [scoring.centre_distance(c, st.city.coord) for st in stops]
        best = min(dists)
        if best > profile.radius_m:
            continue
        for i, d in enumerate(dists):
            if d == best:
                assigned[i].append(c)
    segments: list[_Segment] = []
    for i, st in enumerate(stops):
        scored = scoring.score(
            assigned[i], st.city.coord, profile, config, config.max_candidates(st.days)
        )
        previous = segments[-1] if segments else None
        unknown = previous is not None and (
            st.country_iso2 in rail or stops[i - 1].country_iso2 in rail
        )
        segments.append(
            _Segment(
                base_id=st.city.city_id,
                base_name=st.city.name,
                base=st.city.coord,
                days=st.days,
                sights=len(scored),
                previous=previous,
                pool=_Pool(profile, scored),
                unknown_arrival=unknown,
            )
        )
    return _ProfilePlan(profile, segments)


def _check_possible(
    request: PlanRequest, states: list[_ProfilePlan], config: PlannerConfig
) -> None:
    pools = [s.pool for st in states for s in st.segments]
    if not any(pool.items for pool in pools):
        widest = max(config.profiles, key=lambda p: p.radius_m)
        raise PlanningImpossible(
            [
                Issue(
                    "NO_CANDIDATES",
                    {"radius_km": _km(widest.radius_m), "destination": request.destination_name},
                )
            ]
        )
    longest_day = max(config.visit_budget(st.profile) for st in states)
    fitting = [
        s
        for pool in pools
        for s in pool.items
        if visit_minutes(s.candidate.category) <= longest_day
    ]
    if not fitting:
        raise PlanningImpossible(
            [
                Issue(
                    "VISITS_LONGER_THAN_DAY",
                    {
                        "candidates": len({s.candidate.place_id for p in pools for s in p.items}),
                        "destination": request.destination_name,
                        "day_minutes": longest_day,
                    },
                )
            ]
        )


# -- solving -----------------------------------------------------------------------------------


def _arrival(segment: _Segment, lookup: TravelLookup) -> tuple[TravelTime, Cell] | None:
    if segment.previous is None or segment.unknown_arrival:
        return None
    cell = (segment.previous.base, segment.base)
    return lookup.get(*cell), cell


def _solve(
    state: _ProfilePlan,
    lookup: TravelLookup,
    sequencer: Sequencer,
    config: PlannerConfig,
    kept_pct: dict[str, int],
) -> None:
    """Routes of place ids for each segment, one per day: the first day at a new base first (it
    is shorter by the drive), the others fullest first."""
    budget = config.visit_budget(state.profile)
    taken: set[str] = set()  # planned at an earlier stop of the same city (multi-city trips)
    offset = 0  # the days before this segment
    for seg in state.segments:
        items = [s for s in seg.pool.items if s.candidate.place_id not in taken]
        ids = tuple(s.candidate.place_id for s in items)
        coords = [s.candidate.coord for s in items]
        values = tuple(s.value * kept_pct.get(s.candidate.place_id, 100) // 100 for s in items)
        travel = tuple(
            tuple(0 if i == j else minutes(lookup.get(a, b).seconds) for j, b in enumerate(coords))
            for i, a in enumerate(coords)
        )
        arrival = _arrival(seg, lookup)
        limits = [budget] * seg.days
        if arrival is not None:
            limits[0] = max(0, budget - minutes(arrival[0].seconds))
        # With stays, a day's travel also counts the leg from its stay to its first visit. The
        # day of a drive to a new base starts from that drive instead.
        start_travel: tuple[tuple[int, ...], ...] | None = None
        has_stays = any(_stay_of(state.stays, offset + k + 1) for k in range(seg.days))
        if has_stays:
            rows = []
            for k in range(seg.days):
                stay = (
                    None
                    if (k == 0 and arrival is not None)
                    else _stay_of(state.stays, offset + k + 1)
                )
                rows.append(
                    tuple(0 for _ in coords)
                    if stay is None
                    else tuple(minutes(lookup.get(stay.coord, c).seconds) for c in coords)
                )
            start_travel = tuple(rows)
        problem = SequencingProblem(
            ids=ids,
            value=values,
            duration=tuple(visit_minutes(s.candidate.category) for s in items),
            travel=travel,
            days=seg.days,
            day_minutes=budget,
            travel_weight=state.profile.travel_weight,
            day_limits=tuple(limits),
            start_travel=start_travel,
        )
        routes = [[ids[i] for i in r] for r in sequencer.solve(problem)]
        head = routes[:1] if arrival is not None else []
        rest = routes[1:] if arrival is not None else routes
        # Days with stays are not interchangeable: they keep the order of their days.
        seg.routes = head + (rest if has_stays else _canonical_days(rest, seg.pool.value))
        taken.update(p for r in seg.routes for p in r)
        offset += seg.days


def _canonical_days(routes: list[list[str]], value: dict[str, int]) -> list[list[str]]:
    """Days at one base are interchangeable (no opening hours, no dates that matter): fullest
    day first."""
    return sorted(
        routes,
        key=lambda r: (not r, -sum(value[p] for p in r), r[0] if r else ""),
    )


# -- laying out the days -----------------------------------------------------------------------


def _fit_day(
    route: list[str],
    value: dict[str, int],
    by_id: dict[str, Candidate],
    lookup: TravelLookup,
    config: PlannerConfig,
    profile: Profile,
    start: int,
    head_of: Callable[[str], int] | None = None,
) -> tuple[list[str], DayLayout, int]:
    """The route with its lowest-value visits removed until the day fits (only needed when routed
    times are longer than the times it was planned with)."""
    route = list(route)
    removed = 0
    while True:
        shift = head_of(route[0]) if head_of is not None and route else 0
        layout = lay_out_day(route, by_id, lookup, config, profile, start + shift)
        if layout is not None:
            return route, layout, removed
        drop = min(route, key=lambda p: (value[p], p))
        route.remove(drop)
        removed += 1


def _lay_out(
    state: _ProfilePlan,
    by_id: dict[str, Candidate],
    lookup: TravelLookup,
    config: PlannerConfig,
) -> list[_LaidOutDay]:
    out: list[_LaidOutDay] = []
    value = state.value()
    number = 0
    for seg in state.segments:
        arrival = _arrival(seg, lookup)
        for n, route in enumerate(seg.routes):
            number += 1
            leg = arrival if n == 0 else None
            start = config.day_start_minute + (minutes(leg[0].seconds) if leg else 0)
            stay = None if leg else _stay_of(state.stays, number)
            head_of = _head_of(stay, by_id, lookup)
            fitted, layout, removed = _fit_day(
                route, value, by_id, lookup, config, state.profile, start, head_of
            )
            start_cell = (
                (stay.coord, by_id[fitted[0]].coord) if stay is not None and fitted else None
            )
            out.append(
                _LaidOutDay(
                    segment=seg,
                    arrival=leg[0] if leg else None,
                    arrival_cell=leg[1] if leg else None,
                    route=fitted,
                    layout=layout,
                    removed=removed,
                    arrival_unknown=seg.unknown_arrival and n == 0,
                    start_cell=start_cell,
                )
            )
    return out


def _stay_of(stays: Sequence[StayPoint], day: int) -> StayPoint | None:
    return next((s for s in stays if s.first_day <= day <= s.last_day), None)


def _head_of(
    stay: StayPoint | None, by_id: dict[str, Candidate], lookup: TravelLookup
) -> Callable[[str], int] | None:
    if stay is None:
        return None

    def head(place_id: str) -> int:
        return minutes(lookup.get(stay.coord, by_id[place_id].coord).seconds)

    return head


def _stay_cells(states: list[_ProfilePlan], stays: Sequence[StayPoint]) -> list[Cell]:
    """Each stay to every candidate of the segments whose days it covers (read from the cache)."""
    cells: set[Cell] = set()
    for state in states:
        offset = 0
        for seg in state.segments:
            for k in range(seg.days):
                stay = _stay_of(stays, offset + k + 1)
                if stay is not None:
                    cells.update((stay.coord, s.candidate.coord) for s in seg.pool.items)
            offset += seg.days
    return sorted(cells)


def _day_cells(day: _LaidOutDay) -> list[Cell]:
    cells = list(day.layout.cells)
    if day.arrival_cell is not None:
        cells.append(day.arrival_cell)
    if day.start_cell is not None:
        cells.append(day.start_cell)
    return cells


def _provider_cells(
    states: list[_ProfilePlan],
    by_id: dict[str, Candidate],
    near: dict[str, list[str]],
    lookup: TravelLookup,
    config: PlannerConfig,
) -> list[Cell]:
    """The transfers and inter-city legs the plans use, plus each visit's nearest others in the
    same mode as its outgoing transfer. The extra cells ride in the same one-source request
    (ADR 013), so they cost no extra call and warm the cache for the next plan."""
    cells: set[Cell] = set()
    source_modes: dict[str, set[str]] = {}
    for state in states:
        for day in _lay_out(state, by_id, lookup, config):
            cells.update(_day_cells(day))
            for slot, (start, end) in zip(day.layout.slots, day.layout.cells, strict=False):
                source_modes.setdefault(slot.place_id, set()).add(lookup.mode(start, end))
    for pid, modes in source_modes.items():
        ca = by_id[pid].coord
        for other in near.get(pid, []):
            cb = by_id[other].coord
            if lookup.mode(ca, cb) in modes:
                cells.add((ca, cb))
    return sorted(cells)


def _leg(t: TravelTime, a: Coord, b: Coord, lookup: TravelLookup) -> Leg:
    return Leg(
        mode=lookup.mode(a, b),
        seconds=t.seconds,
        meters=t.meters,
        minutes=minutes(t.seconds),
        confidence=t.confidence,
        estimate_reason=t.reason,
    )


def _build_plan(
    request: PlanRequest,
    state: _ProfilePlan,
    by_id: dict[str, Candidate],
    lookup: TravelLookup,
    config: PlannerConfig,
    notes: list[Note],
) -> Plan:
    profile = state.profile
    seen_categories: set[str] = set()
    days: list[DayPlan] = []
    removed_total = 0
    travel_notes: list[Note] = []
    for number, day in enumerate(_lay_out(state, by_id, lookup, config), start=1):
        removed_total += day.removed
        layout = day.layout
        items: list[PlannedItem] = []
        for pos, slot in enumerate(layout.slots):
            leg = None
            if pos < len(layout.legs):
                leg = _leg(layout.legs[pos], *layout.cells[pos], lookup)
            prev_leg = items[-1].transfer if items else None
            c = by_id[slot.place_id]
            reasons = scoring.static_reasons(c, day.segment.pool.distance[c.place_id], config)
            if items and prev_leg is not None and prev_leg.minutes <= config.near_previous_minutes:
                reasons.append("NEAR_PREVIOUS_ITEM")
            if profile.name == "wider" and seen_categories and c.category not in seen_categories:
                reasons.append("ADDS_VARIETY")
            seen_categories.add(c.category)
            if not reasons:
                reasons.append("NAMED_SIGHT")
            items.append(
                PlannedItem(
                    kind="visit",
                    place_id=c.place_id,
                    name=c.name,
                    category=c.category,
                    lat=c.lat,
                    lon=c.lon,
                    start_minute=slot.start,
                    end_minute=slot.end,
                    duration_minutes=slot.end - slot.start,
                    reasons=_ordered(reasons),
                    transfer=leg,
                )
            )
        arrival = None
        if day.arrival is not None and day.arrival_cell is not None:
            arrival = _leg(day.arrival, *day.arrival_cell, lookup)
            previous = day.segment.previous
            assert previous is not None  # noqa: S101 - an arrival has a previous base
            travel_notes.append(
                Note(
                    "INTER_CITY_TRAVEL",
                    {
                        "day": number,
                        "minutes": arrival.minutes,
                        "from_name": previous.base_name,
                        "to_name": day.segment.base_name,
                        "label": arrival.confidence,
                    },
                )
            )
        if day.arrival_unknown:
            previous = day.segment.previous
            assert previous is not None  # noqa: S101 - an arrival has a previous base
            travel_notes.append(
                Note(
                    "ARRIVAL_TIME_UNKNOWN",
                    {
                        "day": number,
                        "from_name": previous.base_name,
                        "to_name": day.segment.base_name,
                    },
                )
            )
        day_date = (
            None if request.start_date is None else request.start_date + timedelta(number - 1)
        )
        days.append(
            DayPlan(
                day_index=number,
                date=day_date,
                items=tuple(items),
                base_city_id=day.segment.base_id,
                base_city_name=day.segment.base_name,
                arrival=arrival,
                arrival_unknown=day.arrival_unknown,
            )
        )

    stats = compute_stats(days, request.days, config)
    out = [
        Note(
            "PROFILE_ESSENTIALS" if profile.name == "essentials" else "PROFILE_WIDER",
            {"radius_km": _km(profile.radius_m)},
        ),
        *notes,
    ]
    if request.kind == "area":
        out.extend(
            Note(
                "BASE_CITY",
                {
                    "name": seg.base_name,
                    "days": seg.days,
                    "sights": seg.sights,
                    "radius_km": _km(config.base_sight_radius_m),
                },
            )
            for seg in state.segments
        )
    if request.kind in ("area", "route"):
        out.extend(travel_notes)
    empty = sum(1 for d in days if not d.visits)
    if empty:
        out.append(
            Note(
                "DAYS_WITHOUT_VISITS",
                {
                    "candidates": len(
                        {s.candidate.place_id for g in state.segments for s in g.pool.items}
                    ),
                    "radius_km": _km(profile.radius_m),
                    "empty_days": empty,
                    "days": request.days,
                },
            )
        )
    if removed_total:
        out.append(Note("VISITS_REMOVED_TO_FIT", {"removed": removed_total}))
    transfers = stats.routed_transfers + stats.estimated_transfers
    if stats.estimated_transfers:
        out.append(
            Note(
                "ESTIMATED_TRANSFERS",
                {"estimated": stats.estimated_transfers, "transfers": transfers},
            )
        )
    return Plan(profile=profile.name, days=tuple(days), notes=tuple(out), stats=stats)


def _ordered(reasons: list[str]) -> tuple[str, ...]:
    return tuple(sorted(set(reasons), key=_REASON_ORDER.__getitem__))


def compute_stats(days: Iterable[DayPlan], day_count: int, config: PlannerConfig) -> PlanStats:
    visit_min = meal_min = travel_min = travel_sec = routed = est = 0
    visits = meals = with_visits = intercity = 0
    for d in days:
        if d.visits:
            with_visits += 1
        legs = [i.transfer for i in d.items if i.transfer is not None]
        if d.arrival is not None:
            intercity += 1
            legs.append(d.arrival)
        for item in d.items:
            if item.kind == "visit":
                visits += 1
                visit_min += item.duration_minutes
            else:
                meals += 1
                meal_min += item.duration_minutes
        for leg in legs:
            travel_min += leg.minutes
            travel_sec += leg.seconds
            if leg.confidence == "routed":
                routed += 1
            else:
                est += 1
    planned = visit_min + meal_min + travel_min
    window = day_count * (config.day_window_end_minute - config.day_start_minute)
    return PlanStats(
        visits=visits,
        days_with_visits=with_visits,
        visit_minutes=visit_min,
        travel_minutes=travel_min,
        travel_seconds=travel_sec,
        routed_transfers=routed,
        estimated_transfers=est,
        day_utilisation_permille=planned * 1000 // window if window else 0,
        travel_share_permille=travel_min * 1000 // planned if planned else 0,
        meals=meals,
        meal_minutes=meal_min,
        intercity_legs=intercity,
    )


def to_json(generation: Generation) -> dict[str, Any]:
    """A JSON-safe form of a generation: what the golden files hold."""

    def convert(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: convert(v) for k, v in value.items()}
        if isinstance(value, list | tuple):
            return [convert(v) for v in value]
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return value

    result: dict[str, Any] = convert(asdict(generation))
    return result
