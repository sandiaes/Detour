"""Area destinations: base cities and the allocation of days to them (architecture section 5.2,
step 1; ADR 016).

An area (an OSM administrative boundary) is planned from one or more **base cities**: gazetteer
towns of the area where the traveller stays, each for a run of consecutive days. Nothing here is
a fact about accommodation (not modelled, product brief section 9); a base is the point a day's
visits are chosen around.

1. **Eligible towns.** A town of the area is eligible if at least ``min_base_sights`` named sights
   lie within ``base_sight_radius_m`` of it. Its score is the sum of those sights' base values
   (scoring.py: notability and category points) plus population points
   (``population // base_population_divisor``, at most ``base_population_cap``; unknown counts 0).
   Sections of a city (GeoNames ``PPLX``) are not offered as towns (``repo/planning.py``). Of
   towns closer together than ``min_base_separation_m``, only the most populous can be a base
   (the main town of the cluster; ties by city id): a village next to a city is not a base.
   All integers; ties by city id.
2. **How many bases.** ``ceil(days / profile.days_per_base)``, at most ``max_bases``, the number of
   days and the number of eligible towns. Essentials uses fewer bases (fewer moves), Wider more.
3. **Which.** Best score first, skipping any town closer than ``min_base_separation_m`` to one
   already chosen.
4. **Days.** One day each, the rest shared in proportion to the score by the largest-remainder
   method (ties by score order).
5. **Order.** Start at the best base, then always the nearest remaining base by inter-city travel
   time from the travel-time service (ties by city id). The first day at each later base starts
   with that drive.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from detour_api.planner import scoring
from detour_api.planner.config import PlannerConfig, Profile
from detour_api.planner.travel import TravelLookup, minutes
from detour_api.planner.types import BaseCity, Candidate
from detour_api.travel.types import distance_m


@dataclass(frozen=True)
class EligibleBase:
    city: BaseCity
    score: int
    sights: int


def eligible_bases(
    cities: Sequence[BaseCity], candidates: Sequence[Candidate], config: PlannerConfig
) -> list[EligibleBase]:
    out: list[EligibleBase] = []
    for city in sorted(cities, key=lambda c: c.city_id):
        near = [
            c for c in candidates if distance_m(city.coord, c.coord) <= config.base_sight_radius_m
        ]
        if len(near) < config.min_base_sights:
            continue
        value = sum(scoring.base_value(c, config) for c in near)
        population = 0
        if city.population is not None:
            population = min(
                city.population // config.base_population_divisor, config.base_population_cap
            )
        out.append(EligibleBase(city, value + population, len(near)))
    main_towns: list[EligibleBase] = []
    for b in sorted(out, key=lambda b: (-(b.city.population or 0), b.city.city_id)):
        if all(
            distance_m(b.city.coord, m.city.coord) >= config.min_base_separation_m
            for m in main_towns
        ):
            main_towns.append(b)
    main_towns.sort(key=lambda b: (-b.score, b.city.city_id))
    return main_towns


def base_count(days: int, eligible: int, profile: Profile, config: PlannerConfig) -> int:
    return min(math.ceil(days / profile.days_per_base), config.max_bases, days, eligible)


def choose_bases(
    eligible: Sequence[EligibleBase], days: int, profile: Profile, config: PlannerConfig
) -> list[EligibleBase]:
    want = base_count(days, len(eligible), profile, config)
    chosen: list[EligibleBase] = []
    for b in eligible:
        if len(chosen) == want:
            break
        if all(
            distance_m(b.city.coord, c.city.coord) >= config.min_base_separation_m for c in chosen
        ):
            chosen.append(b)
    return chosen


def allocate_days(bases: Sequence[EligibleBase], days: int) -> list[int]:
    """Days per base, in the order given: at least one each, the rest by score (largest
    remainder, ties by position)."""
    n = len(bases)
    rest = days - n
    if n == 0 or rest <= 0:
        return [1] * n
    weights = [max(0, b.score) for b in bases]
    total = sum(weights)
    if total == 0:
        weights, total = [1] * n, n
    numerators = [rest * w for w in weights]
    whole = [x // total for x in numerators]
    by_remainder = sorted(range(n), key=lambda i: (-(numerators[i] % total), i))
    for i in by_remainder[: rest - sum(whole)]:
        whole[i] += 1
    return [1 + w for w in whole]


def order_bases(bases: Sequence[EligibleBase], lookup: TravelLookup) -> list[EligibleBase]:
    """The best base first, then the nearest remaining one by travel time each time."""
    if not bases:
        return []
    route = [bases[0]]
    left = list(bases[1:])
    while left:
        here = route[-1].city.coord
        nxt = min(
            left,
            key=lambda b: (minutes(lookup.get(here, b.city.coord).seconds), b.city.city_id),
        )
        route.append(nxt)
        left.remove(nxt)
    return route
