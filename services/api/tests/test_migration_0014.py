"""Migration 0014 (ADR 026, data step) on a database that already holds restaurants.

The structure tests start from an empty database; this one fills revision 0013 first: an imported
restaurant and cafe with everything that hangs on them, a plan with a meal stop on each, a user's
restaurant with cuisine and meal types, and a change set that added a restaurant. After the
migration no stored stop has lost its name, point or times, and the cuisine and meal data is gone.
"""

import uuid
from typing import Any

import psycopg
import pytest
from alembic import command

from tests.test_database import alembic_config

pytestmark = pytest.mark.db

INSTALLATION = uuid.uuid4()
OTHER = uuid.uuid4()
RUN = uuid.uuid4()
RESTAURANT, CAFE, SIGHT = (uuid.uuid4() for _ in range(3))


def _fill(conn: psycopg.Connection[Any]) -> dict[str, uuid.UUID]:
    conn.execute(
        "INSERT INTO geo.region (id, name, country_codes) VALUES ('r', 'R', '{AT}'),"
        " ('s', 'S', '{AT}')"
    )
    conn.execute(
        "INSERT INTO geo.import_run (id, region_id, importer_version, rules_version, started_at)"
        " VALUES (%s, 'r', 'i', 'v', now())",
        (RUN,),
    )
    for pid, kind, category, name in (
        (RESTAURANT, "restaurant", "restaurant", "Zur Alten Post"),
        (CAFE, "restaurant", "cafe", "Café Test"),
        (SIGHT, "attraction", "museum", "Museum"),
    ):
        conn.execute(
            "INSERT INTO geo.place (id, region_id, kind, category, name, name_norm, geom,"
            " first_import_run_id, last_changed_import_run_id)"
            " VALUES (%s, 'r', %s, %s, %s, lower(%s), ST_SetSRID(ST_MakePoint(16.3, 48.2), 4326),"
            " %s, %s)",
            (pid, kind, category, name, name, RUN, RUN),
        )
        conn.execute(
            "INSERT INTO geo.place_source (place_id, source, source_ref, licence_code, tags,"
            " import_run_id) VALUES (%s, 'osm', %s, 'ODbL-1.0', '{}', %s)",
            (pid, f"node/{pid}", RUN),
        )
        conn.execute(
            "INSERT INTO geo.place_signal (place_id, osm_signals, score) VALUES (%s, '{}', 0)",
            (pid,),
        )
        conn.execute(
            "INSERT INTO geo.place_name_lookup (entity_kind, entity_ref, source, status,"
            " checked_at, retry_after) VALUES ('place', %s, 'wikidata', 'no_item', now(), now())",
            (str(pid),),
        )
    conn.execute(
        "INSERT INTO geo.restaurant_profile (place_id, cuisines, venue_type, meal_types)"
        " VALUES (%s, '{austrian}', 'restaurant', '{lunch,dinner}'),"
        " (%s, NULL, 'cafe', '{breakfast,snack}')",
        (RESTAURANT, CAFE),
    )
    ids: dict[str, uuid.UUID] = {}
    for name, inst in (("one", INSTALLATION), ("two", OTHER)):
        conn.execute("INSERT INTO app.installation (id) VALUES (%s)", (inst,))
        trip, itinerary, day = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        ids[name] = itinerary
        conn.execute(
            "INSERT INTO app.trip (id, installation_id, title, destination_kind, destination_ref,"
            " destination_name, destination_point, duration_days)"
            " VALUES (%s, %s, 't', 'city', '1', 'X', ST_MakePoint(1, 2), 1)",
            (trip, inst),
        )
        conn.execute(
            "INSERT INTO app.itinerary (id, trip_id, generation_id, profile, engine_version,"
            " config_version) VALUES (%s, %s, %s, 'manual', 'm', 'm')",
            (itinerary, trip, uuid.uuid4()),
        )
        conn.execute(
            "INSERT INTO app.itinerary_day (id, itinerary_id, day_index) VALUES (%s, %s, 1)",
            (day, itinerary),
        )
        for pos, (place, meal_type, typ, label) in enumerate(
            ((RESTAURANT, "lunch", "meal", "Zur Alten Post"), (CAFE, "snack", "meal", "Café Test")),
            start=1,
        ):
            conn.execute(
                "INSERT INTO app.itinerary_item (id, day_id, position, type, meal_type, place_id,"
                " display_name, display_point, start_time, end_time, duration_minutes,"
                " duration_source, origin) VALUES (%s, %s, %s, %s, %s, %s, %s,"
                " ST_SetSRID(ST_MakePoint(16.3, 48.2), 4326), %s, %s, 60, 'user', 'user')",
                (uuid.uuid4(), day, pos, typ, meal_type, place, label, f"1{pos}:00", f"1{pos}:30"),
            )
        conn.execute(
            "INSERT INTO app.itinerary_item (id, day_id, position, type, place_id, display_name,"
            " duration_minutes, duration_source, origin)"
            " VALUES (%s, %s, 3, 'visit', %s, 'Museum', 60, 'category_default', 'engine')",
            (uuid.uuid4(), day, SIGHT),
        )
        conn.execute(
            "INSERT INTO app.change_set (id, itinerary_id, base_version, action, user_place_id,"
            " target_name, diff, proposal, slot_day, slot_meal) VALUES (%s, %s, 1,"
            " 'add_restaurant', %s, 'x', '{}', '{}', 1, 'lunch')",
            (uuid.uuid4(), itinerary, uuid.uuid4()),
        )
    conn.execute(
        "INSERT INTO app.user_place (id, installation_id, kind, name, geom, cuisines, meal_types,"
        " source) VALUES (%s, %s, 'restaurant', 'Mine', ST_MakePoint(1, 2), '{ramen}', '{lunch}',"
        " 'manual_pin')",
        (uuid.uuid4(), INSTALLATION),
    )
    return ids


def test_stored_restaurant_stops_survive_as_the_users_own_places(
    scratch_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DETOUR_DATABASE_URL", scratch_database_url)
    cfg = alembic_config()
    command.upgrade(cfg, "0013")
    with psycopg.connect(scratch_database_url, autocommit=True) as conn:
        _fill(conn)

    command.upgrade(cfg, "0014")

    with psycopg.connect(scratch_database_url, autocommit=True) as conn:
        kinds = conn.execute("SELECT DISTINCT kind FROM geo.place").fetchall()
        assert kinds == [("attraction",)]
        for table in ("place_source", "place_signal", "place_name_lookup"):
            [(n,)] = conn.execute(f"SELECT count(*) FROM geo.{table}").fetchall()  # noqa: S608
            assert n == 1, table  # only the museum is left
        assert conn.execute(
            "SELECT count(*) FROM information_schema.tables"
            " WHERE table_schema = 'geo' AND table_name = 'restaurant_profile'"
        ).fetchone() == (0,)

        # Every stop is still there with its name, point and times, now on the installation's own
        # place: a restaurant or a cafe by the imported category.
        rows = conn.execute(
            "SELECT t.installation_id, i.display_name, i.place_id, i.start_time::text,"
            " i.duration_minutes, up.kind, up.name, ST_X(up.geom)"
            " FROM app.itinerary_item i JOIN app.itinerary_day d ON d.id = i.day_id"
            " JOIN app.itinerary it ON it.id = d.itinerary_id JOIN app.trip t ON t.id = it.trip_id"
            " LEFT JOIN app.user_place up ON up.id = i.user_place_id"
            " WHERE i.type = 'meal' ORDER BY t.installation_id, i.position"
        ).fetchall()
        assert len(rows) == 4
        by_inst: dict[uuid.UUID, list[Any]] = {}
        for r in rows:
            by_inst.setdefault(r[0], []).append(r)
            assert r[2] is None and r[6] == r[1] and r[7] == pytest.approx(16.3)
        for inst_rows in by_inst.values():
            assert [(r[1], r[3], r[4], r[5]) for r in inst_rows] == [
                ("Zur Alten Post", "11:00:00", 60, "restaurant"),
                ("Café Test", "12:00:00", 60, "cafe"),
            ]
        # One place per installation and imported restaurant: they are not shared.
        [(n,)] = conn.execute(
            "SELECT count(*) FROM app.user_place WHERE name IN ('Zur Alten Post', 'Café Test')"
        ).fetchall()
        assert n == 4
        # The sight is untouched.
        assert conn.execute(
            "SELECT count(*) FROM app.itinerary_item WHERE type = 'visit' AND place_id = %s",
            (SIGHT,),
        ).fetchone() == (2,)

        # No cuisine or meal type is stored anywhere; add_restaurant change sets are gone.
        cols = conn.execute(
            "SELECT table_name, column_name FROM information_schema.columns"
            " WHERE column_name IN ('cuisines', 'meal_types', 'meal_type', 'slot_meal',"
            " 'after_item_id')"
        ).fetchall()
        assert cols == []
        assert conn.execute("SELECT count(*) FROM app.change_set").fetchone() == (0,)
        mine = conn.execute("SELECT kind FROM app.user_place WHERE name = 'Mine'").fetchone()
        assert mine == ("restaurant",)  # the user's own restaurant stays, minus its cuisine

        # The new kind and the narrowed constraints.
        conn.execute(
            "INSERT INTO app.user_place (id, installation_id, kind, name, geom, source)"
            " VALUES (%s, %s, 'cafe', 'New', ST_MakePoint(1, 2), 'manual_pin')",
            (uuid.uuid4(), INSTALLATION),
        )
        with pytest.raises(psycopg.Error):
            conn.execute(
                "INSERT INTO geo.place (id, region_id, kind, category, geom, first_import_run_id,"
                " last_changed_import_run_id) VALUES (gen_random_uuid(), 'r', 'restaurant', 'x',"
                " ST_MakePoint(1, 2), %s, %s)",
                (RUN, RUN),
            )
        with pytest.raises(psycopg.Error):
            conn.execute(
                "INSERT INTO app.change_set (id, itinerary_id, base_version, action, target_name,"
                " diff, proposal) SELECT gen_random_uuid(), id, 1, 'add_restaurant', 'x', '{}',"
                " '{}' FROM app.itinerary LIMIT 1"
            )

    command.downgrade(cfg, "0013")  # the structure comes back (the deleted data does not)
    with psycopg.connect(scratch_database_url, autocommit=True) as conn:
        assert conn.execute("SELECT count(*) FROM geo.restaurant_profile").fetchone() == (0,)
