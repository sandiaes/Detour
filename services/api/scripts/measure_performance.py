"""Phase 9 performance pass (docs/kpis.md, section 3): the planner, the multi-city planner and
Optimize on the largest synthetic fixtures, without a database or a routing provider.

Run from services/api:  python scripts/measure_performance.py
Each figure is the median and the slowest of several runs on this machine; it measures the engine
only (no network, no database). Provider calls are capped separately (planner_provider_max_seconds).
"""

import random
import statistics
import sys
import time
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.planner_helpers import candidates, request, route_request

from detour_api.planner import engine
from detour_api.planner.optimize import Stop, optimize
from detour_api.planner.travel import FixedTravelSource, TravelLookup


def timed(fn: Callable[[], object], runs: int) -> tuple[float, float]:
    times = []
    for _ in range(runs):
        started = time.perf_counter()
        fn()
        times.append((time.perf_counter() - started) * 1000)
    return statistics.median(times), max(times)


def plan(name: str, days: int) -> None:
    engine.generate(request(name, days), candidates(name), FixedTravelSource())


def route(stops: list[tuple[int, int, str | None]]) -> None:
    engine.generate(route_request(stops), candidates("area"), FixedTravelSource())


def stops_for(n: int, days: int, seed: int = 7) -> tuple[list[Stop], list[int]]:
    rng = random.Random(seed)  # noqa: S311 - a fixed seed for a fixture
    per_day = [n // days + (1 if d < n % days else 0) for d in range(days)]
    out: list[Stop] = []
    for d, count in enumerate(per_day, start=1):
        t = 540
        for i in range(count):
            dur = rng.choice([30, 45, 60])
            out.append(
                Stop(
                    id=f"d{d}s{i}",
                    kind="visit",
                    name=f"d{d}s{i}",
                    lat=48.0 + rng.random() * 0.08,
                    lon=16.0 + rng.random() * 0.12,
                    day=d,
                    start=t,
                    end=t + dur,
                    duration=dur,
                    fixed=False,
                    allowed_days=frozenset(range(1, days + 1)),
                )
            )
            t += dur + 10
    return out, list(range(1, days + 1))


def opt(n: int, days: int, scope: str) -> Callable[[], object]:
    stops, day_list = stops_for(n, days)

    def go() -> object:
        lookup = TravelLookup(FixedTravelSource(), 2_000)
        return optimize(stops, day_list, scope=scope, lookup=lookup, use_provider=False)  # type: ignore[arg-type]

    return go


def main() -> None:
    rows: list[tuple[str, float, float, str]] = []
    for days in (3, 7, 14):
        med, worst = timed(lambda d=days: plan("city-large", d), 5)  # type: ignore[misc]
        rows.append((f"Generate, city-large, {days} days (two plans)", med, worst, "5 s"))
    for days in (3, 7, 14):
        med, worst = timed(lambda d=days: plan("area", d), 3)  # type: ignore[misc]
        rows.append((f"Generate, area, {days} days", med, worst, "5 s"))
    six = [(990001, 2, "AT"), (990002, 2, "AT"), (990003, 2, "AT")] * 2
    for name, stops in (
        ("Multi-city, 3 cities, 6 days", [(990001, 2, "AT"), (990003, 2, "AT"), (990002, 2, "AT")]),
        ("Multi-city, 6 stops, 12 days", six),
    ):
        med, worst = timed(lambda s=stops: route(s), 3)  # type: ignore[misc]
        rows.append((name, med, worst, "5 s"))
    for n, days in ((12, 3), (30, 7), (60, 14), (200, 14)):
        for scope in ("within_days", "across_days"):
            med, worst = timed(opt(n, days, scope), 3)
            target = "5 s (up to 30 stops)" if n <= 30 else "none (over the KPI's 30 stops)"
            rows.append((f"Optimize, {n} stops over {days} days, {scope}", med, worst, target))
    print(f"{'Measurement':58} {'median ms':>10} {'worst ms':>10}  target (p95)")
    for name, med, worst, target in rows:
        print(f"{name:58} {med:10.0f} {worst:10.0f}  {target}")


if __name__ == "__main__":
    main()
