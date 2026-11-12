"""Write the planner's synthetic candidate fixtures (run once; the JSON files are committed).

    python tests/fixtures/planner/make_candidates.py

**Synthetic, invented data.** The points, names, categories and signals are drawn with a fixed
seed around a centre point; they are not real places and must never reach a real database. They
exist so the engine's golden tests have a fixed, varied input. The JSON files, not this script,
are the fixtures: the tests never regenerate them.
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


def _point(rng: random.Random, max_km: float, scale_km: float) -> tuple[float, float]:
    while True:
        d = rng.expovariate(1 / scale_km)
        if d <= max_km:
            break
    bearing = rng.uniform(0, 2 * math.pi)
    lat = CENTRE[0] + (d / 111.32) * math.cos(bearing)
    lon = CENTRE[1] + (d / (111.32 * math.cos(math.radians(CENTRE[0])))) * math.sin(bearing)
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


def main() -> None:
    meta = {
        "synthetic": True,
        "note": "Invented test data: not real places. See make_candidates.py.",
        "centre": {"lat": CENTRE[0], "lon": CENTRE[1]},
    }
    for name, rows in (("city-large", large()), ("city-sparse", sparse())):
        path = HERE / f"{name}.json"
        path.write_text(json.dumps({**meta, "candidates": rows}, indent=1) + "\n")


if __name__ == "__main__":
    main()
