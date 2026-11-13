"""Seed data: one small illustrative trip, clearly marked as seed data.

``python -m detour_api.seed`` builds a two-day trip **from places that exist in the imported
data** (nothing is typed in by hand, so no name, coordinate or fact is invented). It belongs to a
fixed seed installation, carries ``is_seed = true`` and a title starting ``SEED DATA``, and every
item has the reason code ``SEED_DATA``. Running it again replaces the previous seed trip.

The only invented numbers are the item durations, which the importer cannot know (the category
rule table arrives in Phase 4): every item gets a flat placeholder, labelled as a user-given
duration in the seed trip.

Needs a database with an import (``DETOUR_DATABASE_URL``). With ``--print-token`` it prints a
bearer token for the seed installation, for local development only: it refuses to do so when
``DETOUR_ENVIRONMENT=production``.
"""

import argparse
import sys
import uuid
from collections.abc import Sequence

from sqlalchemy import Connection, text

from detour_api.db import make_engine
from detour_api.models.trips import ItemCreate, TripCreate
from detour_api.repo import itineraries, trips
from detour_api.settings import get_settings
from detour_api.textnorm import stable_uuid
from detour_api.tokens import sign_token

SEED_INSTALLATION_ID = stable_uuid("seed", "installation")
SEED_TITLE = "SEED DATA: two illustrative days"
SEED_REASON = "SEED_DATA"
PLACEHOLDER_VISIT_MINUTES = 60
PLACEHOLDER_MEAL_MINUTES = 60
VISITS_PER_DAY = 3


class SeedError(RuntimeError):
    pass


def _pick_city(conn: Connection, region_id: str | None) -> tuple[int, str, str]:
    row = conn.execute(
        text(
            """
            SELECT c.id, c.name, p.region_id, count(*) AS attractions
            FROM geo.place p JOIN geo.city c ON c.id = p.city_id
            WHERE p.is_active AND p.kind = 'attraction' AND p.name IS NOT NULL
              AND (CAST(:r AS text) IS NULL OR p.region_id = :r)
            GROUP BY c.id, c.name, p.region_id, c.population
            HAVING count(*) >= 2
            ORDER BY count(*) DESC, c.population DESC NULLS LAST, c.id LIMIT 1
            """
        ),
        {"r": region_id},
    ).first()
    if row is None:
        raise SeedError(
            "no city has attractions: run the region import and the gazetteer import first"
        )
    return row.id, row.name, row.region_id


def _attractions(conn: Connection, city_id: int, limit: int) -> list[tuple[uuid.UUID, str]]:
    rows = conn.execute(
        text(
            "SELECT p.id, p.name FROM geo.place p JOIN geo.place_signal s ON s.place_id = p.id"
            " WHERE p.city_id = :c AND p.is_active AND p.kind = 'attraction' AND p.name IS NOT NULL"
            " ORDER BY s.score DESC, p.name, p.id LIMIT :n"
        ),
        {"c": city_id, "n": limit},
    ).all()
    return [(r.id, r.name) for r in rows]


def _restaurant(conn: Connection, city_id: int) -> uuid.UUID | None:
    row = conn.execute(
        text(
            "SELECT p.id FROM geo.place p JOIN geo.restaurant_profile rp ON rp.place_id = p.id"
            " WHERE p.city_id = :c AND p.is_active AND p.name IS NOT NULL"
            " ORDER BY (rp.cuisines IS NOT NULL) DESC, p.name, p.id LIMIT 1"
        ),
        {"c": city_id},
    ).first()
    return None if row is None else row.id


def build_seed_trip(conn: Connection, region_id: str | None = None) -> uuid.UUID:
    """Replace the seed trip with a fresh one. Returns the trip id."""
    city_id, city_name, _ = _pick_city(conn, region_id)
    visits = _attractions(conn, city_id, VISITS_PER_DAY * 2)
    if len(visits) < 2:
        raise SeedError("fewer than two attractions in the chosen city")
    restaurant = _restaurant(conn, city_id)
    city = conn.execute(
        text("SELECT ST_Y(geom) lat, ST_X(geom) lon FROM geo.city WHERE id = :i"),
        {"i": city_id},
    ).one()

    conn.execute(
        text(
            "INSERT INTO app.installation (id, is_seed) VALUES (:i, true)"
            " ON CONFLICT (id) DO NOTHING"
        ),
        {"i": SEED_INSTALLATION_ID},
    )
    conn.execute(
        text("DELETE FROM app.trip WHERE installation_id = :i AND is_seed"),
        {"i": SEED_INSTALLATION_ID},
    )
    trip = trips.create_trip(
        conn,
        SEED_INSTALLATION_ID,
        TripCreate(
            title=SEED_TITLE,
            destination_kind="city",
            destination_ref=str(city_id),
            duration_days=2,
        ),
        destination_name=city_name,
        lat=city.lat,
        lon=city.lon,
        is_seed=True,
    )
    itinerary = itineraries.create_manual(conn, SEED_INSTALLATION_ID, trip.id)
    per_day = [visits[:VISITS_PER_DAY], visits[VISITS_PER_DAY:]]
    for day_index, day_visits in enumerate(per_day, start=1):
        for place_id, _ in day_visits:
            itineraries.create_item(
                conn,
                SEED_INSTALLATION_ID,
                itinerary.id,
                day_index,
                ItemCreate(
                    type="visit", place_id=place_id, duration_minutes=PLACEHOLDER_VISIT_MINUTES
                ),
            )
    if restaurant is not None:
        itineraries.create_item(
            conn,
            SEED_INSTALLATION_ID,
            itinerary.id,
            1,
            ItemCreate(
                type="meal",
                meal_type="lunch",
                place_id=restaurant,
                duration_minutes=PLACEHOLDER_MEAL_MINUTES,
            ),
        )
    conn.execute(
        text(
            "UPDATE app.itinerary_item i SET reasons = ARRAY[:r] FROM app.itinerary_day d"
            " WHERE d.id = i.day_id AND d.itinerary_id = :it"
        ),
        {"r": SEED_REASON, "it": itinerary.id},
    )
    return trip.id


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m detour_api.seed", description=__doc__)
    parser.add_argument("--region", help="region id to take the places from (default: any)")
    parser.add_argument(
        "--print-token", action="store_true", help="print a bearer token for the seed installation"
    )
    args = parser.parse_args(argv)
    settings = get_settings()
    if args.print_token and settings.environment == "production":
        print("Refusing to print a token when DETOUR_ENVIRONMENT=production.", file=sys.stderr)
        return 2
    url = settings.sqlalchemy_url
    if not url:
        print("DETOUR_DATABASE_URL is not set.", file=sys.stderr)
        return 2
    engine = make_engine(url)
    try:
        with engine.begin() as conn:
            trip_id = build_seed_trip(conn, args.region)
    except SeedError as exc:
        print(f"Seed failed: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    print(f"Seed trip {trip_id} for installation {SEED_INSTALLATION_ID}")
    if args.print_token:
        print(f"Token: {sign_token(settings.token_secret_bytes, SEED_INSTALLATION_ID)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
