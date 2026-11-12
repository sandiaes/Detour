"""The planning engine, version 1: two itineraries of attractions for a city (ADR 014).

    1. score the candidates for each profile (scoring.py)
    2. read the cached travel times of a sparse cell set: each candidate against its nearest
       others (ADR 013); any other pair is the labelled estimate
    3. solve Essentials, then Wider; if their visit sets overlap too much, solve Wider again with
       the shared visits weighted down (the diversity gate, architecture section 5.3)
    4. ask the travel source for the transfers the plans actually use (the provider is called
       here, within a time limit, only if ``use_provider``)
    5. schedule each day from 09:00; if routed times no longer fit, drop the lowest-value visit
    6. reason codes, notes and statistics; the independent validator checks every plan

Deterministic: candidates are handled in place-id order, every tie is broken by place id, there is
no randomness and no clock. The only input that can change between two runs with the same data is
what the travel source returns (a routed time that arrived in the cache, or a provider that did
not answer in time), and every transfer records which kind of value it is.
"""

import itertools
from collections.abc import Iterable, Sequence
from dataclasses import asdict
from datetime import timedelta
from typing import Any

from detour_api.planner import scoring
from detour_api.planner.config import DEFAULT_CONFIG, ENGINE_VERSION, PlannerConfig, Profile
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
    PlannedVisit,
    PlanningImpossible,
    PlanRequest,
    PlanStats,
)
from detour_api.planner.validator import validate_generation, validate_plan

_REASON_ORDER = {code: i for i, code in enumerate(ITEM_TEMPLATES)}
FOLLOW_UP_FETCHES = 2
_GENERAL_NOTES = (
    Note("NOTABILITY_FROM_TAGS"),
    Note("DURATIONS_ARE_DEFAULTS"),
    Note("NO_OPENING_HOURS"),
    Note("NO_MEALS_YET"),
)


def _km(meters: int) -> int:
    return meters // 1000


def _jaccard_ok(a: frozenset[str], b: frozenset[str], config: PlannerConfig) -> bool:
    union = len(a | b)
    if union == 0:
        return False
    return len(a & b) * config.max_jaccard_den <= config.max_jaccard_num * union


def _distinct(a: frozenset[str], b: frozenset[str], config: PlannerConfig) -> bool:
    """Two visit sets make two plans: both non-empty, overlapping at most the threshold, and the
    second large enough to be a real alternative."""
    return (
        bool(a and b)
        and _jaccard_ok(a, b, config)
        and len(b) * 100 >= config.min_second_variant_pct * len(a)
    )


def _jaccard_permille(a: frozenset[str], b: frozenset[str]) -> int:
    union = len(a | b)
    return 0 if union == 0 else len(a & b) * 1000 // union


class _Pool:
    """One profile's scored candidates, in place-id order."""

    def __init__(self, profile: Profile, scored: list[scoring.Scored]) -> None:
        self.profile = profile
        self.items = sorted(scored, key=lambda s: s.candidate.place_id)
        self.value = {s.candidate.place_id: s.value for s in self.items}
        self.distance = {s.candidate.place_id: s.distance_m for s in self.items}


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
    centre = request.centre
    limit = config.max_candidates(request.days)
    pools = [
        _Pool(p, scoring.score(by_id.values(), centre, p, config, limit)) for p in config.profiles
    ]
    _check_possible(request, pools, config)

    lookup = TravelLookup(source, config.walk_max_m)
    pooled = sorted({s.candidate.place_id for pool in pools for s in pool.items})
    near = scoring.nearest([(pid, by_id[pid].coord) for pid in pooled], config.neighbours)
    lookup.fetch(
        ((by_id[a].coord, by_id[b].coord) for a in pooled for b in near[a]), use_provider=False
    )

    first, second = pools
    routes_first = _solve(first, lookup, sequencer, config, request.days, {})
    set_first = _ids(routes_first)
    routes_second = _solve(second, lookup, sequencer, config, request.days, {})
    initial_jaccard = _jaccard_permille(set_first, _ids(routes_second))
    adjusted: int | None = None
    if (
        set_first
        and _ids(routes_second)
        and not _jaccard_ok(set_first, _ids(routes_second), config)
    ):
        for pct in config.diversity_rounds_pct:
            adjusted = pct
            routes_second = _solve(
                second, lookup, sequencer, config, request.days, dict.fromkeys(set_first, pct)
            )
            if _jaccard_ok(set_first, _ids(routes_second), config):
                break

    set_second = _ids(routes_second)
    distinct = _distinct(set_first, set_second, config)
    plans_routes: list[tuple[_Pool, list[list[str]]]]
    if distinct:
        plans_routes = [(first, routes_first), (second, routes_second)]
    elif set_first:
        plans_routes = [(first, routes_first)]
    else:
        plans_routes = [(second, routes_second)]

    if use_provider:
        lookup.fetch(_provider_cells(plans_routes, by_id, near, lookup), use_provider=True)
        # Fitting a day after routing can join two visits that were never asked about; ask for
        # those legs too (twice at most; any left over stay labelled estimates).
        for _ in range(FOLLOW_UP_FETCHES):
            missing = _unanswered_legs(plans_routes, by_id, lookup, config)
            if not missing:
                break
            lookup.fetch(missing, use_provider=True)

    plans: list[Plan] = []
    for pool, routes in plans_routes:
        notes: list[Note] = []
        if pool is second and adjusted is not None and distinct:
            notes.append(Note("DIVERSITY_ADJUSTED", {"kept_percent": adjusted}))
        plans.append(_build_plan(request, pool, routes, by_id, lookup, config, notes))

    general: list[Note] = []
    jaccard: int | None = None
    candidates_count = len(pooled)
    if len(plans) == 2:
        a, b = plans[0].place_ids(), plans[1].place_ids()
        jaccard = _jaccard_permille(a, b)
        if not _distinct(a, b, config):
            # Visits dropped after routing made the plans too alike: show one.
            plans = plans[:1]
            distinct = False
            general.append(Note("NOT_ENOUGH_DISTINCT_PLACES_AFTER_ROUTING"))
            jaccard = None
        else:
            general.append(
                Note(
                    "DISTINCT_PLANS",
                    {"jaccard_percent": jaccard // 10, "max_percent": _max_percent(config)},
                )
            )
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


def _ids(routes: list[list[str]]) -> frozenset[str]:
    return frozenset(pid for r in routes for pid in r)


def _check_possible(request: PlanRequest, pools: list[_Pool], config: PlannerConfig) -> None:
    widest = max(pools, key=lambda p: p.profile.radius_m)
    if not any(pool.items for pool in pools):
        raise PlanningImpossible(
            [
                Issue(
                    "NO_CANDIDATES",
                    {
                        "radius_km": _km(widest.profile.radius_m),
                        "destination": request.destination_name,
                    },
                )
            ]
        )
    longest_day = max(config.day_minutes(p.profile) for p in pools)
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


def _solve(
    pool: _Pool,
    lookup: TravelLookup,
    sequencer: Sequencer,
    config: PlannerConfig,
    days: int,
    kept_pct: dict[str, int],
) -> list[list[str]]:
    """Routes of place ids, one per day, in the canonical day order."""
    items = pool.items
    ids = tuple(s.candidate.place_id for s in items)
    coords = [s.candidate.coord for s in items]
    values = tuple(s.value * kept_pct.get(s.candidate.place_id, 100) // 100 for s in items)
    travel = tuple(
        tuple(0 if i == j else minutes(lookup.get(a, b).seconds) for j, b in enumerate(coords))
        for i, a in enumerate(coords)
    )
    problem = SequencingProblem(
        ids=ids,
        value=values,
        duration=tuple(visit_minutes(s.candidate.category) for s in items),
        travel=travel,
        days=days,
        day_minutes=config.day_minutes(pool.profile),
        travel_weight=pool.profile.travel_weight,
    )
    routes = [[ids[i] for i in r] for r in sequencer.solve(problem)]
    return _canonical_days(routes, pool.value)


def _canonical_days(routes: list[list[str]], value: dict[str, int]) -> list[list[str]]:
    """Days are interchangeable (no opening hours, no dates that matter): fullest day first."""
    return sorted(
        routes,
        key=lambda r: (not r, -sum(value[p] for p in r), r[0] if r else ""),
    )


def _provider_cells(
    plans_routes: list[tuple[_Pool, list[list[str]]]],
    by_id: dict[str, Candidate],
    near: dict[str, list[str]],
    lookup: TravelLookup,
) -> list[Cell]:
    """The transfers the plans use, plus each transfer source's nearest others in the same mode.
    The extra cells ride in the same one-source request (ADR 013), so they cost no extra call and
    warm the cache for the next plan of the destination."""
    cells: set[Cell] = set()
    source_modes: dict[str, set[str]] = {}
    for _, routes in plans_routes:
        for r in routes:
            for a, b in itertools.pairwise(r):
                ca, cb = by_id[a].coord, by_id[b].coord
                cells.add((ca, cb))
                source_modes.setdefault(a, set()).add(lookup.mode(ca, cb))
    for a, modes in source_modes.items():
        ca = by_id[a].coord
        for b in near.get(a, []):
            cb = by_id[b].coord
            if lookup.mode(ca, cb) in modes:
                cells.add((ca, cb))
    return sorted(cells)


def _unanswered_legs(
    plans_routes: list[tuple[_Pool, list[list[str]]]],
    by_id: dict[str, Candidate],
    lookup: TravelLookup,
    config: PlannerConfig,
) -> list[Cell]:
    missing: set[Cell] = set()
    day_minutes = {pool.profile.name: config.day_minutes(pool.profile) for pool, _ in plans_routes}
    for pool, routes in plans_routes:
        for route in routes:
            fitted, _, _ = _fit_day(route, pool, by_id, lookup, day_minutes[pool.profile.name])
            for a, b in itertools.pairwise(fitted):
                cell = (by_id[a].coord, by_id[b].coord)
                if not lookup.answered(*cell):
                    missing.add(cell)
    return sorted(missing)


def _legs(route: list[str], by_id: dict[str, Candidate], lookup: TravelLookup) -> list[Leg]:
    legs: list[Leg] = []
    for a, b in itertools.pairwise(route):
        ca, cb = by_id[a].coord, by_id[b].coord
        t = lookup.get(ca, cb)
        legs.append(
            Leg(
                mode=lookup.mode(ca, cb),
                seconds=t.seconds,
                meters=t.meters,
                minutes=minutes(t.seconds),
                confidence=t.confidence,
                estimate_reason=t.reason,
            )
        )
    return legs


def _fit_day(
    route: list[str],
    pool: _Pool,
    by_id: dict[str, Candidate],
    lookup: TravelLookup,
    day_minutes: int,
) -> tuple[list[str], list[Leg], int]:
    """The route with the lowest-value visits removed until it fits (only needed when routed
    times are longer than the times it was planned with)."""
    route = list(route)
    removed = 0
    while True:
        legs = _legs(route, by_id, lookup)
        total = sum(visit_minutes(by_id[p].category) for p in route) + sum(x.minutes for x in legs)
        if total <= day_minutes or not route:
            return route, legs, removed
        drop = min(route, key=lambda p: (pool.value[p], p))
        route.remove(drop)
        removed += 1


def _build_plan(
    request: PlanRequest,
    pool: _Pool,
    routes: list[list[str]],
    by_id: dict[str, Candidate],
    lookup: TravelLookup,
    config: PlannerConfig,
    notes: list[Note],
) -> Plan:
    profile = pool.profile
    day_minutes = config.day_minutes(profile)
    removed_total = 0
    fitted: list[tuple[list[str], list[Leg]]] = []
    for route in routes:
        route2, legs, removed = _fit_day(route, pool, by_id, lookup, day_minutes)
        removed_total += removed
        fitted.append((route2, legs))
    fitted.sort(
        key=lambda f: (not f[0], -sum(pool.value[p] for p in f[0]), f[0][0] if f[0] else "")
    )

    seen_categories: set[str] = set()
    days: list[DayPlan] = []
    for index, (route, legs) in enumerate(fitted, start=1):
        visits: list[PlannedVisit] = []
        clock = config.day_start_minute
        for pos, pid in enumerate(route):
            c = by_id[pid]
            duration = visit_minutes(c.category)
            reasons = scoring.static_reasons(c, pool.distance[pid], config)
            if pos > 0 and legs[pos - 1].minutes <= config.near_previous_minutes:
                reasons.append("NEAR_PREVIOUS_ITEM")
            if profile.name == "wider" and seen_categories and c.category not in seen_categories:
                reasons.append("ADDS_VARIETY")
            seen_categories.add(c.category)
            if not reasons:
                reasons.append("NAMED_SIGHT")
            leg = legs[pos] if pos < len(legs) else None
            visits.append(
                PlannedVisit(
                    place_id=pid,
                    name=c.name,
                    category=c.category,
                    lat=c.lat,
                    lon=c.lon,
                    start_minute=clock,
                    end_minute=clock + duration,
                    duration_minutes=duration,
                    reasons=tuple(sorted(set(reasons), key=_REASON_ORDER.__getitem__)),
                    transfer=leg,
                )
            )
            clock += duration + (leg.minutes if leg else 0)
        day_date = None if request.start_date is None else request.start_date + timedelta(index - 1)
        days.append(DayPlan(day_index=index, date=day_date, visits=tuple(visits)))

    stats = compute_stats(days, request.days, config)
    radius_note = Note(
        "PROFILE_ESSENTIALS" if profile.name == "essentials" else "PROFILE_WIDER",
        {"radius_km": _km(profile.radius_m)},
    )
    out = [radius_note, *notes]
    empty = sum(1 for d in days if not d.visits)
    if empty:
        out.append(
            Note(
                "DAYS_WITHOUT_VISITS",
                {
                    "candidates": len(pool.items),
                    "radius_km": _km(profile.radius_m),
                    "empty_days": empty,
                    "days": request.days,
                },
            )
        )
    if removed_total:
        out.append(Note("VISITS_REMOVED_AFTER_ROUTING", {"removed": removed_total}))
    transfers = stats.routed_transfers + stats.estimated_transfers
    if stats.estimated_transfers:
        out.append(
            Note(
                "ESTIMATED_TRANSFERS",
                {"estimated": stats.estimated_transfers, "transfers": transfers},
            )
        )
    return Plan(profile=profile.name, days=tuple(days), notes=tuple(out), stats=stats)


def compute_stats(days: Iterable[DayPlan], day_count: int, config: PlannerConfig) -> PlanStats:
    visit_min = travel_min = travel_sec = routed = est = visits = with_visits = 0
    for d in days:
        if d.visits:
            with_visits += 1
        for v in d.visits:
            visits += 1
            visit_min += v.duration_minutes
            if v.transfer is not None:
                travel_min += v.transfer.minutes
                travel_sec += v.transfer.seconds
                if v.transfer.confidence == "routed":
                    routed += 1
                else:
                    est += 1
    planned = visit_min + travel_min
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
