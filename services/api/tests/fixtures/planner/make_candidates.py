"""Write the planner's synthetic candidate fixtures (run once; the JSON files are committed).

    python tests/fixtures/planner/make_candidates.py

**Synthetic, invented data.** The points, names, categories, signals and towns are
drawn with fixed seeds around invented centre points; they are not real places and must never reach
a real database. They exist so the engine's golden tests have a fixed, varied input. The JSON
files, not this script, are the fixtures: the tests never regenerate them.

Each kind of data has its own random stream, so adding or removing one (the places to eat, removed
by ADR 026, and the area of Phase 6) leaves the sights of the city fixtures byte-identical.
"""

import json
import math
import random
from pathlib import Path

HERE = Path(__file__).parent
CENTRE = (48.2082, 16.3738)
CATEGORIES = [
    ("museum", 14), ("church", 12), ("attraction", 10), ("monument", 8), ("castle", 4),
    ("palace", 4), ("gallery", 6), ("viewpoint", 8), ("ruins", 4), ("statue", 6),
    ("fountain", 5), ("chapel", 6), ("memorial", 4), ("tower", 3), ("zoo", 1),
    ("archaeological_site", 2), ("historic_building", 3), ("city_gate", 2),
]  # fmt: skip


def _point(
    rng: random.Random, max_km: float, scale_km: float, centre: tuple[float, float] = CENTRE
) -> tuple[float, float]:
    while True:
        d = rng.expovariate(1 / scale_km)
        if d <= max_km:
            break
    bearing = rng.uniform(0, 2 * math.pi)
    lat = centre[0] + (d / 111.32) * math.cos(bearing)
    lon = centre[1] + (d / (111.32 * math.cos(math.radians(centre[0])))) * math.sin(bearing)
    return round(lat, 6), round(lon, 6)


def _signals(rng: random.Random) -> dict[str, bool]:
    wikidata = rng.random() < 0.45
    return {
        "has_wikidata": wikidata,
        "has_wikipedia": wikidata and rng.random() < 0.6,
        "has_heritage": rng.random() < 0.2,
        "tourism_attraction": rng.random() < 0.25,
        "has_name": True,
        "has_website": rng.random() < 0.3,
    }


def large(seed: int = 4) -> list[dict[str, object]]:
    rng = random.Random(seed)  # noqa: S311 - fixture data, not security
    names = [c for c, w in CATEGORIES for _ in range(w)]
    out = []
    for i in range(1, 181):
        lat, lon = _point(rng, 14.0, 3.0)
        out.append(
            {
                "place_id": f"00000000-0000-4000-8000-{i:012d}",
                "name": f"Synthetic sight {i:03d}",
                "category": rng.choice(names),
                "lat": lat,
                "lon": lon,
                "signals": _signals(rng),
                "sitelink_count": None,
            }
        )
    return out


def sparse() -> list[dict[str, object]]:
    """Incomplete data: few places, most without signal rows, an unlisted category, a few
    sitelink counts present."""
    rng = random.Random(11)  # noqa: S311 - fixture data, not security
    rows = []
    cats = ["church", "historic_tomb", "unlisted_category", "museum", "chapel", "statue",
            "viewpoint", "theme_park"]  # fmt: skip
    for i, cat in enumerate(cats, start=1):
        lat, lon = _point(rng, 4.0, 1.5)
        rows.append(
            {
                "place_id": f"00000000-0000-4000-9000-{i:012d}",
                "name": f"Sparse synthetic sight {i}",
                "category": cat,
                "lat": lat,
                "lon": lon,
                "signals": {} if i % 2 else {"has_name": True, "has_wikidata": i == 4},
                "sitelink_count": 60 if i == 4 else None,
            }
        )
    return rows


# An invented area: towns (id, name, population or None, centre, sights around it). Town 5 lies
# 12 km from town 1 (too close to be a second base), town 6 has too few sights to be a base. The
# distances between towns 2, 3 and 4 exceed 150 km, so their legs are single-route requests.
AREA_CENTRE = (47.55, 13.9)
TOWNS = [
    (990001, "Synthetic Town A", 250_000, (47.80, 13.04), 60),
    (990002, "Synthetic Town B", 200_000, (48.30, 14.29), 50),
    (990003, "Synthetic Town C", 120_000, (47.07, 15.44), 40),
    (990004, "Synthetic Town D", 15_000, (47.26, 11.40), 25),
    (990005, "Synthetic Town E", 8_000, (47.85, 13.20), 6),
    (990006, "Synthetic Town F", None, (47.60, 14.60), 2),
]


def area() -> dict[str, object]:
    rng = random.Random(23)  # noqa: S311 - fixture data, not security
    names = [c for c, w in CATEGORIES for _ in range(w)]
    candidates: list[dict[str, object]] = []
    n = 0
    for _, _, _, centre, sights in TOWNS:
        for _ in range(sights):
            n += 1
            lat, lon = _point(rng, 9.0, 2.0, centre)
            candidates.append(
                {
                    "place_id": f"00000000-0000-4000-a000-{n:012d}",
                    "name": f"Area synthetic sight {n:03d}",
                    "category": rng.choice(names),
                    "lat": lat,
                    "lon": lon,
                    "signals": _signals(rng),
                    "sitelink_count": None,
                }
            )
    towns = [
        {"city_id": i, "name": nm, "lat": c[0], "lon": c[1], "population": pop}
        for i, nm, pop, c, _ in TOWNS
    ]
    return {"towns": towns, "candidates": candidates}


def main() -> None:
    meta = {
        "synthetic": True,
        "note": "Invented test data: not real places. See make_candidates.py.",
        "centre": {"lat": CENTRE[0], "lon": CENTRE[1]},
    }
    for name, rows in (("city-large", large()), ("city-sparse", sparse())):
        path = HERE / f"{name}.json"
        body = {**meta, "candidates": rows}
        path.write_text(json.dumps(body, indent=1) + "\n")
    area_meta = {**meta, "centre": {"lat": AREA_CENTRE[0], "lon": AREA_CENTRE[1]}}
    (HERE / "area.json").write_text(json.dumps({**area_meta, **area()}, indent=1) + "\n")


if __name__ == "__main__":
    main()
