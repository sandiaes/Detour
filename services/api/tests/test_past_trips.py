"""Past trips (ADR 006, amendments of 2026-11-16 and 2026-11-17): a past trip keeps its plan, is
read-only (409 ``trip_past`` on every change) until the user reopens it, and its undo history is cut
to five versions; becoming past after the last day; and the archive rows of trips that became past
before the amendment.

Plans come from the planner on its synthetic sights (Testburg); the routing provider is off in
tests, so every transfer is a labelled estimate.
"""

from datetime import date
from typing import Any

import pytest

from detour_api.repo import trips as trips_repo
from tests.conftest import ApiEnv
from tests.test_api_changes import _apply, _preview, _unplanned_sight
from tests.test_api_planning import add_synthetic_sights, generate, make_trip, sql
from tests.test_api_trips import CITY as CITY_BODY
from tests.test_api_trips import add_item, make_itinerary

pytestmark = pytest.mark.db

# Everything below an itinerary: archiving must keep all of it.
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


# -- what is kept ------------------------------------------------------------------------------


def test_a_past_trip_keeps_its_plan_and_only_its_old_undo_history_goes(api_env: ApiEnv) -> None:
    trip, plan = _planned_trip(api_env)
    sql(
        api_env,
        "UPDATE app.transfer SET geometry = ST_GeomFromText('LINESTRING(16.37 48.20, 16.38 48.21)', 4326)"
        " WHERE from_item_id = (SELECT from_item_id FROM app.transfer ORDER BY id LIMIT 1)",
    )
    # An undo history of 20 versions on the selected plan.
    sql(api_env, "DELETE FROM app.itinerary_version")
    for v in range(1, 21):
        sql(
            api_env,
            "INSERT INTO app.itinerary_version (itinerary_id, version, state)"
            " VALUES (%s, %s, '{}'::jsonb)",
            plan["id"],
            v,
        )
    sql(api_env, "UPDATE app.itinerary SET version = 21 WHERE id = %s", plan["id"])
    before = {t: _count(api_env, t) for t in PLAN_TABLES if t != "itinerary_version"}

    past = _archive(api_env, trip)
    assert past["status"] == "past" and past["archived_at"]
    assert past["selected_itinerary_id"] == plan["id"]
    # Nothing but versions is deleted, and no archive rows are written.
    assert {t: _count(api_env, t) for t in before} == before
    assert sql(api_env, "SELECT count(*) FROM app.transfer WHERE geometry IS NOT NULL") == [(1,)]
    assert _count(api_env, "trip_visit") == 0
    kept = sql(api_env, "SELECT version FROM app.itinerary_version ORDER BY version")
    assert kept == [(v,) for v in range(16, 21)]
    # The plan reads as before.
    again = api_env.client.get(f"/v1/itineraries/{plan['id']}", headers=api_env.headers).json()
    assert again["days"] == plan["days"]


def test_a_past_trip_is_read_only_and_keeps_five_versions(api_env: ApiEnv) -> None:
    """ADR 006, amendment of 2026-11-17: nothing of a past trip's plan, stays, cities, dates or
    name changes until it is reopened. Reading, export and delete still work."""
    trip, plan = _planned_trip(api_env)
    change = _preview(
        api_env, plan["id"], action="add_place", place_id=_unplanned_sight(api_env, plan)
    )
    assert change.status_code == 201, change.text  # a change previewed before the trip became past
    _archive(api_env, trip)
    c, h = api_env.client, api_env.headers
    item = next(i for d in plan["days"] for i in d["items"])

    def refused(response: Any) -> None:
        assert response.status_code == 409, response.text
        assert response.json()["code"] == "trip_past"

    # No change set can be previewed or applied.
    refused(_apply(api_env, change.json()["id"]))
    refused(
        _preview(api_env, plan["id"], action="add_place", place_id=_unplanned_sight(api_env, plan))
    )
    refused(
        c.post(f"/v1/itineraries/{plan['id']}/optimize", json={"scope": "within_days"}, headers=h)
    )
    # No stop is added, moved, changed or removed.
    refused(
        c.post(
            f"/v1/itineraries/{plan['id']}/days/1/items",
            json={"type": "free_time", "duration_minutes": 30},
            headers=h,
        )
    )
    refused(c.patch(f"/v1/items/{item['id']}", json={"duration_minutes": 20}, headers=h))
    refused(c.delete(f"/v1/items/{item['id']}", headers=h))
    # No stay, no new plan, no new proposals, no other settings.
    refused(
        c.post(
            f"/v1/trips/{trip['id']}/stays",
            json={"name": "Hotel", "lat": 50.0, "lon": 10.0, "first_day": 1, "last_day": 1},
            headers=h,
        )
    )
    refused(c.post(f"/v1/trips/{trip['id']}/itineraries", headers=h))
    refused(generate(api_env, trip))
    refused(c.patch(f"/v1/trips/{trip['id']}", json={"title": "Back then"}, headers=h))
    refused(c.patch(f"/v1/trips/{trip['id']}", json={"start_date": "2027-06-01"}, headers=h))
    refused(c.delete(f"/v1/itineraries/{plan['id']}", headers=h))
    # Nothing changed, and it can still be read and exported.
    assert c.get(f"/v1/itineraries/{plan['id']}", headers=h).json()["days"] == plan["days"]
    assert c.get(f"/v1/trips/{trip['id']}", headers=h).json()["title"] == trip["title"]
    assert c.get(f"/v1/trips/{trip['id']}/export", headers=h).status_code == 200
    stored = sql(
        api_env, "SELECT count(*) FROM app.itinerary_version WHERE itinerary_id = %s", plan["id"]
    )
    assert int(stored[0][0]) <= 5


def test_a_reopened_trip_can_be_changed_and_is_not_made_past_again(
    api_env: ApiEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    trip, plan = _planned_trip(api_env)
    c, h = api_env.client, api_env.headers
    # Only a past trip can be reopened.
    again = c.post(f"/v1/trips/{trip['id']}/reopen", headers=h)
    assert again.status_code == 409 and again.json()["code"] == "not_archived"
    _archive(api_env, trip)
    reopened = c.post(f"/v1/trips/{trip['id']}/reopen", headers=h)
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["status"] == "active" and reopened.json()["archived_at"] is None
    assert reopened.json()["selected_itinerary_id"] == plan["id"]
    # It is an ordinary trip again.
    change = _preview(
        api_env, plan["id"], action="add_place", place_id=_unplanned_sight(api_env, plan)
    )
    assert change.status_code == 201, change.text
    assert _apply(api_env, change.json()["id"]).status_code == 200
    assert (
        c.patch(f"/v1/trips/{trip['id']}", json={"title": "Back now"}, headers=h).status_code == 200
    )
    # Its last day is long gone, yet reading the trips does not make it past again.
    monkeypatch.setattr(trips_repo, "today_utc", lambda: date(2030, 1, 1))
    assert c.get("/v1/trips", headers=h).json()[0]["status"] == "active"
    # The user can mark it past a second time.
    assert _archive(api_env, trip)["status"] == "past"
    # Another installation cannot reopen it.
    other = api_env.other_installation()
    assert c.post(f"/v1/trips/{trip['id']}/reopen", headers=other).status_code == 404


# -- the archive rows of trips that became past before the amendment -------------------------


def test_the_archive_rows_of_an_older_past_trip_are_still_readable(api_env: ApiEnv) -> None:
    c, h = api_env.client, api_env.headers
    trip = make_trip(api_env, duration_days=2, start_date="2027-05-01")
    not_yet = c.get(f"/v1/trips/{trip['id']}/archive", headers=h)
    assert not_yet.status_code == 409 and not_yet.json()["code"] == "not_archived"
    _archive(api_env, trip)
    sql(
        api_env,
        "INSERT INTO app.trip_visit (id, trip_id, kind, name, point, day_number)"
        " VALUES (gen_random_uuid(), %s, 'attraction', 'Old museum',"
        " ST_SetSRID(ST_MakePoint(16.37, 48.2), 4326), 1)",
        trip["id"],
    )
    visits = _visits(api_env, trip)
    assert [(v["kind"], v["name"]) for v in visits] == [("attraction", "Old museum")]
    info = c.get(f"/v1/trips/{trip['id']}/archive", headers=h).json()
    assert info["attractions"] == 1 and info["size_bytes"] > 0
    cleared = c.patch(
        f"/v1/trips/{trip['id']}/visits/{visits[0]['id']}", json={"confirmed": False}, headers=h
    )
    assert cleared.status_code == 200
    other = api_env.other_installation()
    assert c.get(f"/v1/trips/{trip['id']}/archive", headers=other).status_code == 404


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
    assert status_of(due) == "active"

    today(date(2027, 5, 4))
    by_title = {t["title"]: t for t in c.get("/v1/trips", headers=h).json()}
    assert by_title["Due"]["status"] == "past" and by_title["Due"]["archived_at"]
    assert by_title["Undated"]["status"] == "active"  # no last day
    assert by_title["Seed"]["status"] == "active"  # the seed trip is illustrative
    # The plan is kept, as when the user marks the trip.
    assert by_title["Due"]["selected_itinerary_id"] == plan["id"]
    assert _count(api_env, "itinerary") == 1 and _count(api_env, "trip_visit") == 0

    # Reading again changes nothing.
    c.get("/v1/trips", headers=h)
    assert _count(api_env, "itinerary") == 1
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
    assert got["status"] == "past"


def test_a_trip_made_after_its_last_day_is_not_archived_by_itself(
    api_env: ApiEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR 026 decision 23: a journey already taken is created, filled, then marked past."""
    c, h = api_env.client, api_env.headers
    taken = make_trip(api_env, title="Taken", duration_days=2, start_date="2020-05-01")
    assert taken["status"] == "active"
    plan = make_itinerary(api_env, taken)
    museum = c.get("/v1/places/search", params={"q": "testburg museum"}, headers=h).json()[
        "results"
    ][0]
    add_item(api_env, plan, 1, type="visit", place_id=museum["id"], duration_minutes=60)
    c.patch(f"/v1/trips/{taken['id']}", json={"selected_itinerary_id": plan["id"]}, headers=h)
    assert {t["status"] for t in c.get("/v1/trips", headers=h).json()} == {"active"}
    past = _archive(api_env, taken)
    assert past["status"] == "past" and past["selected_itinerary_id"] == plan["id"]
