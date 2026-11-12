"""Spike S3 (throwaway): matrix latency and memory for a built Valhalla graph.

Usage: python3 -I bench.py <valhalla.json> <city-lat> <city-lon> > bench.json
Cases (50 x 50 points each, sources = targets):
  city_pedestrian / city_auto : a 10 x 5 grid around the given centre, 400 m spacing
  intercity_auto              : 50 points spread over mainland Italian cities
The first call of each case is a warm-up and is reported separately. Nothing here is
production code and the intercity list is only a benchmark input.
"""
import json
import resource
import statistics
import sys
import time

from valhalla import Actor

RUNS = 5

# Mainland Italian cities, approximate centres. Benchmark input only.
CITIES = [
    (41.9028, 12.4964), (45.4642, 9.1900), (40.8518, 14.2681), (45.0703, 7.6869),
    (43.7696, 11.2558), (44.4949, 11.3426), (45.4408, 12.3155), (44.4056, 8.9463),
    (41.1171, 16.8719), (45.4384, 10.9916), (45.4064, 11.8768), (45.6495, 13.7768),
    (43.7228, 10.4017), (43.3188, 11.3308), (43.1107, 12.3908), (43.6158, 13.5189),
    (42.3498, 13.3995), (44.8015, 10.3279), (45.5416, 10.2118), (46.0748, 11.1217),
]


def rss_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # Linux: KB


def city_points(lat0, lon0):
    pts = []
    for i in range(10):
        for j in range(5):
            pts.append((lat0 + (j - 2) * 0.0036, lon0 + (i - 5) * 0.0052))
    return pts


def intercity_points():
    pts = []
    k = 0
    while len(pts) < 50:
        lat, lon = CITIES[k % len(CITIES)]
        step = k // len(CITIES)
        pts.append((lat + 0.01 * step, lon + 0.01 * step))
        k += 1
    return pts


def run_case(actor, name, points, costing):
    locs = [{"lat": a, "lon": b} for a, b in points]
    body = {"sources": locs, "targets": locs, "costing": costing}
    times = []
    first = None
    unreachable = None
    error = None
    for n in range(RUNS + 1):
        t = time.perf_counter()
        try:
            res = actor.matrix(body)
        except Exception as exc:  # report, do not hide
            error = f"{type(exc).__name__}: {exc}"
            break
        dt = (time.perf_counter() - t) * 1000
        if n == 0:
            first = dt
        else:
            times.append(dt)
        cells = [c for row in res["sources_to_targets"] for c in row]
        unreachable = sum(1 for c in cells if c.get("distance") is None)
    out = {"case": name, "costing": costing, "points": len(points), "error": error}
    if first is not None:
        out["warmup_ms"] = round(first, 1)
    if times:
        out.update(median_ms=round(statistics.median(times), 1),
                   min_ms=round(min(times), 1), max_ms=round(max(times), 1),
                   unreachable_cells=unreachable, cells=len(points) ** 2)
    out["peak_rss_mb_after"] = round(rss_mb(), 1)
    return out


def main():
    cfg_path, lat0, lon0 = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
    with open(cfg_path, encoding="utf-8") as fh:
        config = json.load(fh)
    config["logging"]["type"] = ""  # keep stdout as clean JSON
    rss_before = rss_mb()
    t = time.perf_counter()
    actor = Actor(config)
    load_s = time.perf_counter() - t
    results = {
        "actor_load_s": round(load_s, 2),
        "peak_rss_mb_before_load": round(rss_before, 1),
        "cases": [
            run_case(actor, "city_pedestrian", city_points(lat0, lon0), "pedestrian"),
            run_case(actor, "city_auto", city_points(lat0, lon0), "auto"),
            run_case(actor, "intercity_auto", intercity_points(), "auto"),
        ],
    }
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
