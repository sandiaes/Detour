"""The past-trips archive (ADR 006): what archiving keeps and deletes, a past trip without any
routing data, a re-import of the geo data, the size report, and archiving after the last day.

Plans come from the planner on its synthetic sights (Testburg); the routing provider is off in
tests, so every transfer is a labelled estimate.
"""

from datetime import date
from pathlib import Path
from typing import Any

import pytest

from detour_api.models.trips import TripVisit
from detour_api.repo import trips as trips_repo
from tests.conftest import ApiEnv
from tests.import_helpers import import_fixture_region
from tests.test_api_changes import _apply, _preview, _unplanned_sight
from tests.test_api_planning import add_synthetic_sights, generate, make_trip, sql
from tests.test_api_trips import CITY as CITY_BODY
from tests.test_api_trips import add_item, make_itinerary

pytestmark = pytest.mark.db

# Everything below an itinerary: archiving must delete all of it.
PLAN_TABLES = (
    "itinerary",
    "itinerary_day",
    "itinerary_item",
    "transfer",
    "itinerary_version",
    "change_set",
)


def _archive(env: ApiEnv, trip: dict[str, Any]) -> Any:
    r = env.client.post(f"/v1/trips/{trip['id']}/archive", headers=env.headers)
    assert r.status_code == 200, r.text
    return r.json()


def _visits(env: ApiEnv, trip: dict[str, Any]) -> list[dict[str, Any]]:
    r = env.client.get(f"/v1/trips/{trip['id']}/visits", headers=env.headers)
    assert r.status_code == 200, r.text
    visits: list[dict[str, Any]] = r.json()
    return visits


def _count(env: ApiEnv, table: str) -> int:
    return int(sql(env, f"SELECT count(*) FROM app.{table}")[0][0])  # noqa: S608


def _planned_trip(env: ApiEnv, days: int = 3) -> tuple[dict[str, Any], dict[str, Any]]:
    """A trip with two proposals, the Essentials one selected and changed once (so versions and a
    change set exist). Returns the trip and the selected plan as it was just before archiving."""
    add_synthetic_sights(env)
    trip = make_trip(env, duration_days=days, start_date="2027-05-01")
    r = generate(env, trip)
    assert r.status_code == 201, r.text
    plan = next(i for i in r.json()["itineraries"] if i["profile"] == "essentials")
    sel = env.client.patch(
        f"/v1/trips/{trip['id']}",
        json={"selected_itinerary_id": plan["id"]},
        headers=env.headers,
    )
    assert sel.status_code == 200, sel.text
    change = _preview(env, plan["id"], action="add_place", place_id=_unplanned_sight(env, plan))
    assert change.status_code == 201, change.text
    assert _apply(env, change.json()["id"]).status_code == 200
    current = env.client.get(f"/v1/itineraries/{plan['id']}", headers=env.headers).json()
    return trip, current


# -- what is kept and what is deleted ----------------------------------------------------------


def test_archiving_deletes_exactly_the_listed_data_and_keeps_the_rest(api_env: ApiEnv) -> None:
    trip, plan = _planned_trip(api_env)
    pin = api_env.client.post(
        "/v1/user-places",
        json={
            "kind": "location",
            "name": "My pin",
            "lat": 48.21,
            "lon": 16.37,
            "source": "manual_pin",
        },
        headers=api_env.headers,
    )
    assert pin.status_code == 201
    # A route line, so there is geometry to delete.
    sql(
        api_env,
        "UPDATE app.transfer SET geometry = ST_GeomFromText('LINESTRING(16.37 48.20, 16.38 48.21)', 4326)"
        " WHERE from_item_id = (SELECT from_item_id FROM app.transfer ORDER BY id LIMIT 1)",
    )

    before = {t: _count(api_env, t) for t in PLAN_TABLES}
    assert before["itinerary"] >= 2  # the selected plan and the unselected proposal
    assert before["transfer"] > 0 and before["itinerary_version"] >= 1 and before["change_set"] >= 1
    assert sql(api_env, "SELECT count(*) FROM app.transfer WHERE geometry IS NOT NULL") == [(1,)]
    trip_row = sql(
        api_env,
        "SELECT title, destination_kind, destination_ref, destination_name, ST_AsText(destination_point),"
        " duration_days, start_date, installation_id FROM app.trip",
    )
    places_before = sql(api_env, "SELECT id, name FROM app.user_place ORDER BY id")

    day_of_city: dict[str, int] = {}
    for d in plan["days"]:
        day_of_city.setdefault(d["base_city_name"], d["day_index"])
    expected = {("city", name, day) for name, day in day_of_city.items()}
    meal_names = set()
    for d in plan["days"]:
        for item in d["items"]:
            if item["type"] == "visit":
                expected.add(("attraction", item["display_name"], d["day_index"]))
            elif item["type"] == "meal":
                meal_names.add(item["display_name"])
    assert any(k == "attraction" for k, _, _ in expected)

    past = _archive(api_env, trip)
    assert past["status"] == "past" and past["selected_itinerary_id"] is None

    # Deleted: every itinerary and everything that hangs from one.
    assert {t: _count(api_env, t) for t in PLAN_TABLES} == dict.fromkeys(PLAN_TABLES, 0)
    assert sql(api_env, "SELECT count(*) FROM app.transfer WHERE geometry IS NOT NULL") == [(0,)]

    # Kept: the trip as it was, the user's places, one row per city and attraction, nothing else.
    assert (
        sql(
            api_env,
            "SELECT title, destination_kind, destination_ref, destination_name,"
            " ST_AsText(destination_point), duration_days, start_date, installation_id FROM app.trip",
        )
        == trip_row
    )
    assert sql(api_env, "SELECT id, name FROM app.user_place ORDER BY id") == places_before
    assert _count(api_env, "installation") == 1
    visits = _visits(api_env, trip)
    assert {(v["kind"], v["name"], v["day_number"]) for v in visits} == expected
    assert len(visits) == len(expected)  # no row twice
    assert not meal_names & {v["name"] for v in visits}  # meals and restaurants are not archived
    assert _count(api_env, "trip_visit") == len(expected)
    assert all(v["confirmed"] for v in visits)


# -- no routing data ---------------------------------------------------------------------------


def test_a_past_trip_renders_without_any_routing_data(api_env: ApiEnv) -> None:
    trip, _ = _planned_trip(api_env)
    _archive(api_env, trip)
    # Take every table that holds routing away: the transfers (and their route geometry) and the
    # travel-time cache. A past trip must not need either.
    sql(api_env, "ALTER TABLE app.transfer RENAME TO transfer_gone")
    sql(api_env, "ALTER TABLE geo.travel_time RENAME TO travel_time_gone")

    c, h = api_env.client, api_env.headers
    listed = c.get("/v1/trips?status=past", headers=h)
    assert listed.status_code == 200 and [t["id"] for t in listed.json()] == [trip["id"]]
    assert c.get(f"/v1/trips/{trip['id']}", headers=h).status_code == 200
    visits = _visits(api_env, trip)
    assert visits
    # Exactly the snapshot fields: no route, travel time, mode, time of day or duration.
    assert all(set(v) == set(TripVisit.model_fields) for v in visits)
    assert c.get(f"/v1/trips/{trip['id']}/archive", headers=h).status_code == 200
    assert c.get(f"/v1/trips/{trip['id']}/itineraries", headers=h).json() == []


# -- a re-import of the geo data ---------------------------------------------------------------


def test_reimporting_geo_data_does_not_break_an_archived_trip(
    api_env: ApiEnv, second_scratch_database_url: str, tmp_path: Path
) -> None:
    trip, _ = _planned_trip(api_env)
    _archive(api_env, trip)
    before = _visits(api_env, trip)
    assert any(v["geo_place_ref"] for v in before if v["kind"] == "attraction")

    # The synthetic sights are not in the region's extract, so the re-import deletes them: the
    # archived rows now name places that no longer exist.
    assert sql(
        api_env, "SELECT count(*) FROM geo.place WHERE name LIKE %s", "Synthetic sight%"
    ) != [(0,)]
    import_fixture_region(api_env.database_url, second_scratch_database_url, tmp_path)
    gone = sql(api_env, "SELECT count(*) FROM geo.place WHERE name LIKE %s", "Synthetic sight%")
    assert gone == [(0,)]
    assert _visits(api_env, trip) == before

    # The same when the gazetteer and every place are gone altogether.
    sql(api_env, "DELETE FROM geo.place")
    sql(api_env, "UPDATE geo.region SET current_import_run_id = NULL")
    sql(api_env, "DELETE FROM geo.city")
    assert _visits(api_env, trip) == before
    assert (
        api_env.client.get(f"/v1/trips/{trip['id']}/archive", headers=api_env.headers).status_code
        == 200
    )
    assert api_env.client.get("/v1/trips?status=past", headers=api_env.headers).status_code == 200


# -- size --------------------------------------------------------------------------------------


def test_the_size_of_an_archived_trip_is_reported(api_env: ApiEnv) -> None:
    trip, _ = _planned_trip(api_env)
    c, h = api_env.client, api_env.headers
    not_yet = c.get(f"/v1/trips/{trip['id']}/archive", headers=h)
    assert not_yet.status_code == 409 and not_yet.json()["code"] == "not_archived"

    _archive(api_env, trip)
    visits = _visits(api_env, trip)
    info = c.get(f"/v1/trips/{trip['id']}/archive", headers=h).json()
    assert info["trip_id"] == trip["id"]
    assert info["cities"] == sum(v["kind"] == "city" for v in visits)
    assert info["attractions"] == sum(v["kind"] == "attraction" for v in visits)
    assert info["skipped"] == 0

    # The reported size is the stored row data of the trip and its visits.
    measured = sql(
        api_env,
        "SELECT (SELECT sum(pg_column_size(v.*)) FROM app.trip_visit v)"
        " + (SELECT pg_column_size(t.*) FROM app.trip t)",
    )[0][0]
    assert info["size_bytes"] == int(measured) > 0
    assert info["size_bytes"] < 10_000  # a few dozen small rows (ADR 006)

    # Clearing a visit is counted, and a trip with fewer visits is smaller.
    c.patch(
        f"/v1/trips/{trip['id']}/visits/{visits[-1]['id']}", json={"confirmed": False}, headers=h
    )
    assert c.get(f"/v1/trips/{trip['id']}/archive", headers=h).json()["skipped"] == 1
    small = make_trip(api_env, title="Small", duration_days=1)
    _archive(api_env, small)
    small_info = c.get(f"/v1/trips/{small['id']}/archive", headers=h).json()
    assert small_info["attractions"] == 0 and small_info["size_bytes"] < info["size_bytes"]

    other = api_env.other_installation()
    assert c.get(f"/v1/trips/{trip['id']}/archive", headers=other).status_code == 404


# -- an area trip ------------------------------------------------------------------------------


def test_an_area_trip_lists_each_base_city_once(api_env: ApiEnv) -> None:
    area = api_env.client.get(
        "/v1/destinations/search", params={"q": "testland"}, headers=api_env.headers
    ).json()["results"][0]
    trip = make_trip(
        api_env,
        destination_kind="area",
        destination_ref=area["ref"],
        duration_days=4,
        start_date=None,
    )
    plan = make_itinerary(api_env, trip)
    museum = api_env.client.get(
        "/v1/places/search", params={"q": "testburg museum"}, headers=api_env.headers
    ).json()["results"][0]
    # Testburg is the base on days 1, 2 and 4, Alpenau on day 3 (900101 and 900105 are gazetteer
    # towns of the fixture).
    for day, city in ((1, 900101), (2, 900101), (3, 900105), (4, 900101)):
        sql(
            api_env,
            "UPDATE app.itinerary_day SET base_city_id = %s WHERE itinerary_id = %s AND day_index = %s",
            city,
            plan["id"],
            day,
        )
    add_item(api_env, plan, 1, type="visit", place_id=museum["id"], duration_minutes=60)
    # The user added Testburg as a town on day 2, and "Pin Town" twice, on days 2 and 3.
    for day, name in ((2, "Testburg"), (2, "Pin Town"), (3, "Pin Town")):
        place = api_env.client.post(
            "/v1/user-places",
            json={"kind": "city", "name": name, "lat": 48.2, "lon": 16.4, "source": "manual_pin"},
            headers=api_env.headers,
        ).json()
        add_item(api_env, plan, day, type="visit", user_place_id=place["id"], duration_minutes=60)
    api_env.client.patch(
        f"/v1/trips/{trip['id']}",
        json={"selected_itinerary_id": plan["id"]},
        headers=api_env.headers,
    )

    _archive(api_env, trip)
    cities = [(v["name"], v["day_number"]) for v in _visits(api_env, trip) if v["kind"] == "city"]
    # Once each: the base cities Testburg (days 1, 2, 4; also added by hand) and Alpenau, and the
    # town added twice. Ordered by day, so Alpenau (day 3) follows Pin Town (day 2).
    assert cities == [("Testburg", 1), ("Pin Town", 2), ("Alpenau", 3)]


# -- after the last day ------------------------------------------------------------------------


def test_a_trip_becomes_past_by_itself_after_its_last_day(
    api_env: ApiEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    c, h = api_env.client, api_env.headers
    due = make_trip(
        api_env, title="Due", duration_days=2, start_date="2027-05-01"
    )  # last day 2 May
    plan = make_itinerary(api_env, due)
    museum = c.get("/v1/places/search", params={"q": "testburg museum"}, headers=h).json()[
        "results"
    ][0]
    add_item(api_env, plan, 1, type="visit", place_id=museum["id"], duration_minutes=60)
    c.patch(f"/v1/trips/{due['id']}", json={"selected_itinerary_id": plan["id"]}, headers=h)
    make_trip(api_env, title="Undated", duration_days=2)
    seed = make_trip(api_env, title="Seed", duration_days=1, start_date="2027-05-01")
    sql(api_env, "UPDATE app.trip SET is_seed = true WHERE id = %s", seed["id"])
    other = api_env.other_installation()
    theirs = c.post(
        "/v1/trips",
        json={**CITY_BODY, "title": "Theirs", "duration_days": 1, "start_date": "2027-05-01"},
        headers=other,
    ).json()

    def status_of(trip: dict[str, Any]) -> str:
        return str(sql(api_env, "SELECT status FROM app.trip WHERE id = %s", trip["id"])[0][0])

    def today(d: date) -> None:
        monkeypatch.setattr(trips_repo, "today_utc", lambda: d)

    # The last day is not over everywhere until two days later: nothing happens before.
    for d in (date(2027, 5, 1), date(2027, 5, 2), date(2027, 5, 3)):
        today(d)
        assert {t["status"] for t in c.get("/v1/trips", headers=h).json()} == {"active"}
    assert status_of(due) == "active" and _count(api_env, "trip_visit") == 0

    today(date(2027, 5, 4))
    by_title = {t["title"]: t for t in c.get("/v1/trips", headers=h).json()}
    assert by_title["Due"]["status"] == "past" and by_title["Due"]["archived_at"]
    assert by_title["Undated"]["status"] == "active"  # no last day
    assert by_title["Seed"]["status"] == "active"  # the seed trip is illustrative
    # It is the same archive as when the user marks the trip: the snapshots, no plans.
    assert [(v["kind"], v["name"]) for v in _visits(api_env, due)] == [
        ("city", "Testburg"),
        ("attraction", "Testburg Museum"),
    ]
    assert _count(api_env, "itinerary") == 0 and _count(api_env, "itinerary_item") == 0

    # Reading again changes nothing (no visit twice).
    c.get("/v1/trips", headers=h)
    assert len(_visits(api_env, due)) == 2
    # Another installation's trip is archived when its owner reads, not when someone else does.
    assert status_of(theirs) == "active"
    assert [t["status"] for t in c.get("/v1/trips", headers=other).json()] == ["past"]
    assert status_of(theirs) == "past"


def test_a_trip_opened_by_id_after_its_last_day_is_past(
    api_env: ApiEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    trip = make_trip(api_env, duration_days=1, start_date="2027-05-01")
    monkeypatch.setattr(trips_repo, "today_utc", lambda: date(2027, 5, 3))
    got = api_env.client.get(f"/v1/trips/{trip['id']}", headers=api_env.headers).json()
    assert got["status"] == "past" and got["selected_itinerary_id"] is None
    assert [(v["kind"], v["name"]) for v in _visits(api_env, trip)] == [("city", "Testburg")]
