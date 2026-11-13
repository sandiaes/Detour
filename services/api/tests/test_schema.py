"""Database-level guarantees: constraints, schema separation, and index use."""

import uuid
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from psycopg import errors

from detour_api.repo import geo
from tests.conftest import ApiEnv
from tests.import_helpers import migrate

pytestmark = pytest.mark.db

INSTALLATION = uuid.uuid4()


@pytest.fixture
def db(
    scratch_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> Iterator[psycopg.Connection[Any]]:
    migrate(scratch_database_url, monkeypatch)
    with psycopg.connect(scratch_database_url, autocommit=True) as conn:
        conn.execute("INSERT INTO app.installation (id) VALUES (%s)", (INSTALLATION,))
        yield conn


def trip(conn: psycopg.Connection[Any], **over: Any) -> uuid.UUID:
    values: dict[str, Any] = {
        "id": uuid.uuid4(),
        "installation_id": INSTALLATION,
        "title": "t",
        "destination_kind": "city",
        "destination_ref": "1",
        "destination_name": "X",
        "duration_days": 2,
        "status": "active",
    }
    values.update(over)
    columns = ", ".join(values)
    marks = ", ".join(f"%({k})s" for k in values)
    conn.execute(
        f"INSERT INTO app.trip ({columns}, destination_point) VALUES ({marks}, ST_MakePoint(1, 2))",  # noqa: S608
        values,
    )
    trip_id: uuid.UUID = values["id"]
    return trip_id


def day(conn: psycopg.Connection[Any]) -> uuid.UUID:
    itinerary, day_id = uuid.uuid4(), uuid.uuid4()
    conn.execute(
        "INSERT INTO app.itinerary (id, trip_id, generation_id, profile, engine_version,"
        " config_version) VALUES (%s, %s, %s, 'manual', 'm', 'm')",
        (itinerary, trip(conn), uuid.uuid4()),
    )
    conn.execute(
        "INSERT INTO app.itinerary_day (id, itinerary_id, day_index) VALUES (%s, %s, 1)",
        (day_id, itinerary),
    )
    return day_id


def item(conn: psycopg.Connection[Any], day_id: uuid.UUID, **over: Any) -> None:
    values: dict[str, Any] = {
        "id": uuid.uuid4(),
        "day_id": day_id,
        "position": 1,
        "type": "visit",
        "place_id": uuid.uuid4(),
        "display_name": "n",
        "duration_minutes": 30,
        "duration_source": "user",
        "origin": "user",
    }
    values.update(over)
    columns = ", ".join(values)
    marks = ", ".join(f"%({k})s" for k in values)
    conn.execute(f"INSERT INTO app.itinerary_item ({columns}) VALUES ({marks})", values)  # noqa: S608


@pytest.mark.parametrize(
    "over",
    [
        {"type": "visit", "place_id": None},  # visit without a place
        {"type": "visit", "user_place_id": uuid.uuid4()},  # both set (and a missing user place)
        {"type": "free_time", "meal_type": None},  # free time with a place
        {"type": "meal", "meal_type": None},  # meal without meal_type
        {"type": "visit", "meal_type": "lunch"},  # meal_type on a visit
        {"start_time": "10:00", "end_time": None},
        {"start_time": "10:00", "end_time": "10:00"},
        {"start_time": "11:00", "end_time": "10:00"},
        {"duration_minutes": 0},
        {"duration_minutes": 1441},
        {"origin": "robot"},
        {"duration_source": "guess"},
        {"position": 0},
        {"type": "meal", "meal_type": "brunch"},
    ],
)
def test_item_constraints(db: psycopg.Connection[Any], over: dict[str, Any]) -> None:
    with pytest.raises(psycopg.Error):
        item(db, day(db), **over)


def test_meal_types_include_snack_and_the_arrival_leg_is_all_or_nothing(
    db: psycopg.Connection[Any],
) -> None:
    d = day(db)
    for n, meal in enumerate(("breakfast", "lunch", "snack", "dinner"), start=1):
        item(db, d, type="meal", meal_type=meal, position=n)
    db.execute(
        "UPDATE app.itinerary_day SET base_city_name = 'B', arrival_mode = 'drive',"
        " arrival_seconds = 3600, arrival_meters = 80000, arrival_confidence = 'routed'"
        " WHERE id = %s",
        (d,),
    )
    for bad in (
        "arrival_seconds = NULL",
        "arrival_confidence = 'guessed'",
        "arrival_mode = 'fly'",
        "arrival_meters = -1",
    ):
        with pytest.raises(psycopg.Error), db.transaction():
            db.execute(f"UPDATE app.itinerary_day SET {bad} WHERE id = %s", (d,))  # noqa: S608


def test_positions_can_be_swapped_in_one_transaction_and_duplicates_fail_at_commit(
    db: psycopg.Connection[Any],
) -> None:
    d = day(db)
    a, b = uuid.uuid4(), uuid.uuid4()
    item(db, d, id=a, position=1)
    item(db, d, id=b, position=2)
    with db.transaction():
        db.execute("UPDATE app.itinerary_item SET position = 2 WHERE id = %s", (a,))
        db.execute("UPDATE app.itinerary_item SET position = 1 WHERE id = %s", (b,))
    with pytest.raises(errors.UniqueViolation), db.transaction():
        db.execute("UPDATE app.itinerary_item SET position = 1 WHERE id = %s", (a,))


@pytest.mark.parametrize(
    "over",
    [
        {"status": "past"},  # past needs archived_at
        {"duration_days": 0},
        {"duration_days": 31},
        {"title": ""},
        {"currency_code": "EUR"},  # ADR 017: the column is gone
        {"destination_kind": "country"},
    ],
)
def test_trip_constraints(db: psycopg.Connection[Any], over: dict[str, Any]) -> None:
    with pytest.raises(psycopg.Error):
        trip(db, **over)


def test_user_place_constraints(db: psycopg.Connection[Any]) -> None:
    def make(**over: Any) -> None:
        values: dict[str, Any] = {
            "id": uuid.uuid4(),
            "installation_id": INSTALLATION,
            "kind": "location",
            "name": "n",
            "source": "manual_pin",
        }
        values.update(over)
        columns = ", ".join(values)
        marks = ", ".join(f"%({k})s" for k in values)
        db.execute(
            f"INSERT INTO app.user_place ({columns}, geom) VALUES ({marks}, ST_MakePoint(1, 2))",  # noqa: S608
            values,
        )

    make()
    make(source="search_result", search_provider="photon", search_ref="N1")
    for bad in (
        {"source": "search_result"},
        {"search_provider": "photon", "search_ref": "N1"},
        {"cuisines": ["x"]},  # only restaurants have cuisines
        {"kind": "hotel"},
        {"name": ""},
    ):
        with pytest.raises(psycopg.Error):
            make(**bad)


def test_deleting_an_installation_removes_everything_of_theirs(db: psycopg.Connection[Any]) -> None:
    d = day(db)
    item(db, d)
    db.execute("DELETE FROM app.installation WHERE id = %s", (INSTALLATION,))
    for table in (
        "trip",
        "itinerary",
        "itinerary_day",
        "itinerary_item",
        "user_place",
    ):
        row = db.execute(f"SELECT count(*) FROM app.{table}").fetchone()  # noqa: S608
        assert row == (0,), table


def test_geo_constraints(db: psycopg.Connection[Any]) -> None:
    for sql in (
        "INSERT INTO geo.region (id, name, country_codes) VALUES ('Bad Slug', 'x', '{AT}')",
        "INSERT INTO geo.region (id, name, country_codes) VALUES ('ok', 'x', '{}')",
        "INSERT INTO geo.region (id, name, country_codes, status) VALUES ('ok', 'x', '{AT}', 'ready')",
        "INSERT INTO geo.currency (code, name) VALUES ('eur', 'x')",
    ):
        with pytest.raises(psycopg.Error):
            db.execute(sql)


def test_app_and_geo_have_no_foreign_keys_between_them(db: psycopg.Connection[Any]) -> None:
    """The schemas are independent: geo can be rebuilt without touching user data (ADR 005/006)."""
    rows = db.execute(
        """
        SELECT src.nspname, dst.nspname FROM pg_constraint c
        JOIN pg_class sc ON sc.oid = c.conrelid JOIN pg_namespace src ON src.oid = sc.relnamespace
        JOIN pg_class dc ON dc.oid = c.confrelid JOIN pg_namespace dst ON dst.oid = dc.relnamespace
        WHERE c.contype = 'f' AND src.nspname IN ('geo', 'app') AND dst.nspname IN ('geo', 'app')
          AND src.nspname <> dst.nspname
        """
    ).fetchall()
    assert rows == []


def test_every_geometry_column_has_a_gist_index(db: psycopg.Connection[Any]) -> None:
    columns = db.execute(
        "SELECT f_table_schema, f_table_name, f_geometry_column FROM geometry_columns"
        " WHERE f_table_schema IN ('geo', 'app')"
    ).fetchall()
    assert len(columns) == 10
    missing = []
    for schema, table, column in columns:
        indexed = db.execute(
            """
            SELECT 1 FROM pg_index i
            JOIN pg_class t ON t.oid = i.indrelid JOIN pg_namespace n ON n.oid = t.relnamespace
            JOIN pg_class ic ON ic.oid = i.indexrelid JOIN pg_am am ON am.oid = ic.relam
            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY (i.indkey)
            WHERE n.nspname = %s AND t.relname = %s AND a.attname = %s AND am.amname = 'gist'
            """,
            (schema, table, column),
        ).fetchone()
        if indexed is None:
            missing.append(f"{schema}.{table}.{column}")
    assert missing == []


def test_the_phase_1_rules_still_hold_installation_ids_come_from_tokens() -> None:
    from detour_api.tokens import issue_token, verify_token

    installation_id, token = issue_token(b"s" * 32)
    assert verify_token(b"s" * 32, token) == installation_id


# -- queries use their indexes ---------------------------------------------------------------


def plan(env: ApiEnv, sql: str) -> str:
    """EXPLAIN a statement written with ``%%`` for operators (psycopg placeholder syntax)."""
    with psycopg.connect(env.database_url) as conn:
        conn.execute("SET enable_seqscan = off")  # a tiny table would otherwise be scanned
        rows = conn.execute("EXPLAIN " + sql, ()).fetchall()
    return "\n".join(r[0] for r in rows)


def explain_search(
    env: ApiEnv, sql: str, params: dict[str, Any], force_indexes: bool = False
) -> str:
    """The plan of a real query. By default the planner is left alone."""
    from sqlalchemy import text as sa_text

    from detour_api.db import make_engine

    engine = make_engine(env.database_url.replace("postgresql://", "postgresql+psycopg://", 1))
    with engine.connect() as conn:
        if force_indexes:
            conn.execute(sa_text("SET enable_seqscan = off"))  # a tiny table would be scanned
        rows = conn.execute(sa_text("EXPLAIN " + sql), params).all()
    engine.dispose()
    return "\n".join(r[0] for r in rows)


def add_bulk_places(env: ApiEnv, count: int = 20_000) -> None:
    """Pad the test database with synthetic places so planner statistics are realistic."""
    with psycopg.connect(env.database_url, autocommit=True) as conn:
        conn.execute(
            """
            INSERT INTO geo.place (id, region_id, kind, category, name, name_norm, geom,
                                   first_import_run_id, last_changed_import_run_id)
            SELECT md5('bulk' || n)::uuid, 'test-region', 'attraction', 'viewpoint',
                   'Bulk ' || n, 'bulk ' || n || ' ' || md5(n::text),
                   ST_SetSRID(ST_MakePoint(10 + mod(n, 1000) / 100.0, 46 + (n / 1000) / 10.0), 4326),
                   r.current_import_run_id, r.current_import_run_id
            FROM generate_series(1, %s) n, geo.region r WHERE r.id = 'test-region'
            """,
            (count,),
        )
        conn.execute("ANALYZE geo.place")


def test_nearby_place_search_uses_the_spatial_index(api_env: ApiEnv) -> None:
    add_bulk_places(api_env)
    sql, params = geo.build_place_search(
        query=None,
        region=None,
        kind=None,
        category=None,
        lat=48.2082,
        lon=16.3738,
        radius_m=500,
        limit=10,
    )
    explained = explain_search(api_env, sql, params)  # planner not forced
    assert "place_geom_gix" in explained, explained
    assert "Seq Scan on place" not in explained


def test_name_search_uses_the_trigram_index(api_env: ApiEnv) -> None:
    add_bulk_places(api_env)
    # The name predicate of the place search, on its own: with the sequential scan ruled out the
    # planner must be able to answer it from the trigram index. In the full query the planner may
    # prefer another index at this size (cheap on 20,000 rows); whether it picks the trigram index
    # at the size of a real country (100,000+ places) must be measured on a real import.
    explained = explain_search(
        api_env,
        "SELECT id FROM geo.place WHERE name_norm LIKE '%' || :q || '%' OR name_norm % :q",
        {"q": "museum"},
        force_indexes=True,
    )
    assert "place_name_trgm" in explained, explained
    assert "Seq Scan on place" not in explained


def test_destination_search_uses_the_trigram_indexes(api_env: ApiEnv) -> None:
    with psycopg.connect(api_env.database_url, autocommit=True) as conn:
        conn.execute(
            """
            INSERT INTO geo.city (id, name, ascii_name, name_norm, alt_names_norm, country_iso2,
                                  geom)
            SELECT 1000000 + n, 'City ' || n, 'City ' || n, 'city ' || md5(n::text),
                   'alt ' || md5((n + 1)::text), 'AT',
                   ST_SetSRID(ST_MakePoint(10 + mod(n, 100) / 10.0, 46 + (n / 100) / 100.0), 4326)
            FROM generate_series(1, 20000) n
            """
        )
        conn.execute("ANALYZE geo.city")
    # A gazetteer of this size (cities above 1,000 inhabitants: ten thousand rows or so per
    # country) is cheap to scan, so the planner may legitimately choose a sequential scan.
    # What matters is that the trigram indexes can serve the query when it pays off.
    city = explain_search(
        api_env, geo._DESTINATION_SQL, {"q": "testburg", "limit": 10}, force_indexes=True
    )
    assert "city_name_trgm" in city and "city_alt_trgm" in city, city
    assert "Seq Scan on city" not in city


@pytest.mark.parametrize(
    ("sql", "index"),
    [
        (
            "SELECT id FROM geo.city ORDER BY geom <-> ST_SetSRID(ST_MakePoint(16.37, 48.2), 4326) LIMIT 5",
            "city_geom_gix",
        ),
        (
            "SELECT id FROM geo.admin_area WHERE ST_Intersects(geom, ST_SetSRID(ST_MakePoint(16.37, 48.2), 4326))",
            "admin_area_geom_gix",
        ),
        (
            "SELECT id FROM geo.place WHERE geom && ST_MakeEnvelope(16, 48, 17, 49, 4326)",
            "place_geom_gix",
        ),
        ("SELECT id FROM geo.city WHERE ascii_name %% 'testburg'", "city_ascii_trgm"),
        ("SELECT id FROM geo.city WHERE alt_names_norm LIKE '%%testenburg%%'", "city_alt_trgm"),
    ],
)
def test_spatial_and_trigram_queries_use_indexes(api_env: ApiEnv, sql: str, index: str) -> None:
    explained = plan(api_env, sql)
    assert index in explained, explained


def test_the_city_assignment_query_uses_the_knn_index(api_env: ApiEnv) -> None:
    explained = plan(
        api_env,
        "SELECT c.id FROM geo.city c WHERE c.country_iso2 = ANY ('{AT}')"
        " ORDER BY c.geom <-> ST_SetSRID(ST_MakePoint(16.37, 48.2), 4326) LIMIT 5",
    )
    assert "city_geom_gix" in explained, explained
