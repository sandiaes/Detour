"""Spike S5 (throwaway): generate the three synthetic fixture trips.

Usage: python3 -I make_fixtures.py <out-dir>

The fixtures are SYNTHETIC. Visit points are drawn with a fixed seed around city centres; they
are not real places, their scores are not real notability, and their travel times are not
routed. Only the city-centre coordinates are real (approximate centres, the same values as in
spikes/s3-routing/bench.py). Travel times use one fixed estimate rule (straight line x detour
factor / speed, the shape of the architecture's `estimated` fallback) and are stored as integer
minutes, so the solvers never compute floating-point geometry themselves.

The generated files are committed; regenerating them is only for transparency.
"""
import json
import math
import random
import sys
from pathlib import Path

SEED = 20261112

# Approximate city centres (copied from spikes/s3-routing/bench.py).
CENTRES = {
    "florence": (43.7696, 11.2558),
    "pisa": (43.7228, 10.4017),
    "siena": (43.3188, 11.3308),
    "bologna": (44.4949, 11.3426),
    "milan": (45.4642, 9.1900),
    "venice": (45.4408, 12.3155),
    "rome": (41.9028, 12.4964),
}
CODES = {"florence": "fl", "pisa": "pi", "siena": "si", "bologna": "bo",
         "milan": "mi", "venice": "ve", "rome": "ro"}

# Category -> default visit minutes (a stand-in for the Phase 4 rule table) and draw weight.
CATEGORIES = [
    ("museum", 120, 3), ("gallery", 90, 2), ("church", 45, 4), ("monument", 30, 3),
    ("viewpoint", 30, 2), ("park", 60, 2), ("castle", 90, 1), ("archaeological_site", 90, 1),
    ("attraction", 60, 3),
]

DAY_START = 9 * 60          # 09:00
DAY_END = 21 * 60           # 21:00
MEALS = [                   # start window and duration, minutes after midnight
    {"name": "lunch", "earliest": 12 * 60, "latest": 14 * 60, "duration": 60},
    {"name": "dinner", "earliest": 18 * 60 + 30, "latest": 19 * 60 + 45, "duration": 75},
]


def haversine_km(a, b):
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def travel_minutes(d_km):
    """Estimate rule: the fastest of walking, local driving and inter-city driving.

    walk:       d x 1.30 / 4.5 km/h
    local:      d x 1.30 / 30 km/h + 12 min (parking, access)
    inter-city: d x 1.25 / 80 km/h + 20 min
    The minimum of concave functions is concave, so the rule keeps the triangle inequality.
    """
    if d_km == 0:
        return 0
    walk = d_km * 1.30 / 4.5 * 60
    local = d_km * 1.30 / 30 * 60 + 12
    inter = d_km * 1.25 / 80 * 60 + 20
    return max(1, math.ceil(min(walk, local, inter)))


def draw_category(rng):
    total = sum(w for _, _, w in CATEGORIES)
    x = rng.uniform(0, total)
    for name, minutes, w in CATEGORIES:
        x -= w
        if x <= 0:
            return name, minutes
    return CATEGORIES[-1][0], CATEGORIES[-1][1]


def make_visits(rng, city, count):
    lat0, lon0 = CENTRES[city]
    out = []
    for k in range(1, count + 1):
        if rng.random() < 0.75:      # historic core
            dx = max(-2.5, min(2.5, rng.gauss(0, 0.7)))
            dy = max(-2.5, min(2.5, rng.gauss(0, 0.7)))
            core = True
        else:                        # outskirts
            r = rng.uniform(2.5, 7.0)
            a = rng.uniform(0, 2 * math.pi)
            dx, dy = r * math.cos(a), r * math.sin(a)
            core = False
        lat = lat0 + dy / 111.32
        lon = lon0 + dx / (111.32 * math.cos(math.radians(lat0)))
        cat, minutes = draw_category(rng)
        u = rng.random()
        score = 1 + int(99 * u ** (2.0 if core else 3.0))
        out.append({"id": f"{CODES[city]}-{k:03d}", "kind": "visit", "city": city,
                    "lat": round(lat, 5), "lon": round(lon, 5), "category": cat,
                    "duration": minutes, "score": score})
    return out


def centre_node(city):
    lat, lon = CENTRES[city]
    return {"id": f"{CODES[city]}-centre", "kind": "city_centre", "city": city,
            "lat": lat, "lon": lon}


def build(name, description, nodes, days):
    pts = [(n["lat"], n["lon"]) for n in nodes]
    matrix = [[travel_minutes(haversine_km(a, b)) for b in pts] for a in pts]
    return {
        "name": name,
        "synthetic": True,
        "description": description,
        "seed": SEED,
        "day_start": DAY_START,
        "day_end": DAY_END,
        "meals": MEALS,
        "days": days,
        "nodes": nodes,
        "travel_rule": "estimated: min(walk 4.5 km/h, local 30 km/h + 12 min, inter-city "
                       "80 km/h + 20 min) on straight-line distance x 1.30 (1.25 inter-city)",
        "travel_minutes": matrix,
    }


def city3(rng):
    nodes = make_visits(rng, "florence", 60)
    days = [{"day": d, "city": "florence", "start": None, "end": None} for d in (1, 2, 3)]
    return build("city3-florence", "3-day single-city trip; days start at the first item and "
                 "end after the last (no accommodation).", nodes, days)


def region7(rng):
    nodes = [centre_node("florence")]
    for city, n in (("florence", 45), ("pisa", 15), ("siena", 20), ("bologna", 20)):
        nodes += make_visits(rng, city, n)
    days = [{"day": d, "city": None, "start": "fl-centre", "end": "fl-centre"}
            for d in range(1, 8)]
    return build("region7-tuscany", "7-day regional trip from one base city; every day starts "
                 "and ends at the base; any visit may go on any day.", nodes, days)


def multi14(rng):
    plan = [("milan", 3), ("venice", 3), ("florence", 4), ("rome", 4)]
    nodes = [centre_node(c) for c, _ in plan]
    for city, _ in plan:
        nodes += make_visits(rng, city, 40)
    days = []
    prev = None
    d = 1
    for city, n in plan:
        for i in range(n):
            if i == 0 and prev:
                # the drive between cities is fixed and unavoidable: the day starts at the new
                # city's centre once the drive (leaving at 09:00) is over
                drive = travel_minutes(haversine_km(CENTRES[prev], CENTRES[city]))
                days.append({"day": d, "city": city, "start": f"{CODES[city]}-centre",
                             "end": None, "earliest_start": DAY_START + drive})
            else:
                days.append({"day": d, "city": city, "start": None, "end": None})
            d += 1
        prev = city
    return build("multi14-italy", "14-day multi-city trip with a fixed allocation of days to "
                 "cities (Milan 3, Venice 3, Florence 4, Rome 4); a move day leaves the previous "
                 "city at 09:00 and starts at the new city's centre when the fixed drive ends.",
                 nodes, days)


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    for fx in (city3(rng), region7(rng), multi14(rng)):
        path = out / f"{fx['name']}.json"
        with open(path, "w", encoding="utf-8") as f:
            # one matrix row per line keeps the file reviewable
            matrix = fx.pop("travel_minutes")
            text = json.dumps(fx, indent=1, ensure_ascii=False)
            rows = ",\n  ".join(json.dumps(r, separators=(",", ":")) for r in matrix)
            f.write(text[:-2] + ',\n "travel_minutes": [\n  ' + rows + "\n ]\n}\n")
        print(path, len(fx["nodes"]), "nodes")


if __name__ == "__main__":
    main()
