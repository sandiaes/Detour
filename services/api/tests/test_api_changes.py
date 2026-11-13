"""Adding and removing places through change sets (Phase 7, ADR 018), on the imported fixture
region with the planner's synthetic sights (Testburg). The routing provider is off in tests, so
every new travel time is a labelled estimate.
"""

import math
import uuid
from typing import Any

import psycopg
import pytest
from sqlalchemy import create_engine

from detour_api.planner import diff
from detour_api.repo import changes
from detour_api.repo.plan_state import read_state, to_rplan
from tests.conftest import ApiEnv
from tests.test_api_planning import add_synthetic_sights, generate, make_trip, sql

pytestmark = pytest.mark.db


def _plan(env: ApiEnv, days: int = 3) -> dict[str, Any]:
    add_synthetic_sights(env)
    trip = make_trip(env, duration_days=days, start_date="2027-05-01")
    r = generate(env, trip)
    assert r.status_code == 201, r.text
    plan: dict[str, Any] = next(i for i in r.json()["itineraries"] if i["profile"] == "essentials")
    return plan


def _unplanned_sight(env: ApiEnv, plan: dict[str, Any]) -> str:
    used = {i["place_id"] for d in plan["days"] for i in d["items"]}
    rows = sql(
        env,
        "SELECT id FROM geo.place WHERE kind = 'attraction' AND name LIKE %s ORDER BY id",
        "Synthetic sight%",
    )
    return next(str(r[0]) for r in rows if str(r[0]) not in used)


def _preview(env: ApiEnv, itinerary_id: str, **body: Any) -> Any:
    return env.client.post(
        f"/v1/itineraries/{itinerary_id}/change-sets", json=body, headers=env.headers
    )


def _apply(env: ApiEnv, change_id: str) -> Any:
    return env.client.post(f"/v1/change-sets/{change_id}/apply", headers=env.headers)


def _state(env: ApiEnv, itinerary_id: str) -> dict[str, Any]:
    engine = create_engine(env.database_url.replace("postgresql://", "postgresql+psycopg://", 1))
    try:
        with engine.connect() as conn:
            return read_state(conn, uuid.UUID(itinerary_id))
    finally:
        engine.dispose()


def _get(env: ApiEnv, itinerary_id: str) -> dict[str, Any]:
    r = env.client.get(f"/v1/itineraries/{itinerary_id}", headers=env.headers)
    assert r.status_code == 200
    result: dict[str, Any] = r.json()
    return result


def _pin(env: ApiEnv, name: str, lat: float, lon: float, kind: str = "location") -> str:
    r = env.client.post(
        "/v1/user-places",
        json={"kind": kind, "name": name, "lat": lat, "lon": lon, "source": "manual_pin"},
        headers=env.headers,
    )
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


def test_a_preview_changes_nothing_until_it_is_applied(api_env: ApiEnv) -> None:
    plan = _plan(api_env)
    before = _get(api_env, plan["id"])
    r = _preview(api_env, plan["id"], action="add_place", place_id=_unplanned_sight(api_env, plan))
    assert r.status_code == 201, r.text
    change = r.json()
    assert change["status"] == "pending" and change["base_version"] == 1
    assert change["notes"][0]["code"] == "PLACE_ADDED"
    added = [a for a in change["diff"]["added"] if a["kind"] == "visit"]
    assert len(added) == 1 and added[0]["added_by_you"] is True
    assert _get(api_env, plan["id"]) == before
    assert (
        api_env.client.get(f"/v1/change-sets/{change['id']}", headers=api_env.headers).json()
        == change
    )


def test_the_applied_result_matches_the_previewed_diff(api_env: ApiEnv) -> None:
    plan = _plan(api_env)
    old = _state(api_env, plan["id"])
    change = _preview(
        api_env, plan["id"], action="add_place", place_id=_unplanned_sight(api_env, plan)
    ).json()
    r = _apply(api_env, change["id"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["change_set"]["status"] == "applied" and body["change_set"]["result_version"] == 2
    itinerary = body["itinerary"]
    assert itinerary["version"] == 2
    assert itinerary["engine_version"].endswith("+recalc-1.0.0")
    new = _state(api_env, plan["id"])
    applied = changes.diff_model(
        diff.compare(to_rplan(old, "essentials"), to_rplan(new, "essentials"))
    )
    assert applied.model_dump(mode="json") == change["diff"]
    # The added place is a mandatory visit with its reason, and the day is consistent.
    item = next(i for d in itinerary["days"] for i in d["items"] if "ADDED_BY_YOU" in i["reasons"])
    assert item["origin"] == "user" and item["type"] == "visit"
    for d in itinerary["days"]:
        for a, b in zip(d["items"], d["items"][1:], strict=False):
            assert a["transfer"] is not None and a["transfer"]["to_item_id"] == b["id"]
    versions = api_env.client.get(
        f"/v1/itineraries/{plan['id']}/versions", headers=api_env.headers
    ).json()
    assert [(v["version"], v["action"]) for v in versions] == [(1, "add_place")]


def test_adding_then_removing_a_place_restores_the_previous_plan(api_env: ApiEnv) -> None:
    plan = _plan(api_env)
    original = _state(api_env, plan["id"])
    original_read = _get(api_env, plan["id"])
    sight = _unplanned_sight(api_env, plan)
    added = _apply(
        api_env, _preview(api_env, plan["id"], action="add_place", place_id=sight).json()["id"]
    )
    item = next(
        i for d in added.json()["itinerary"]["days"] for i in d["items"] if i["place_id"] == sight
    )
    r = _preview(api_env, plan["id"], action="remove_place", item_id=item["id"])
    assert r.status_code == 201, r.text
    removal = r.json()
    assert removal["restores_version"] == 1
    assert [n["code"] for n in removal["notes"]] == ["PLAN_RESTORED"]
    assert _apply(api_env, removal["id"]).status_code == 200
    restored = _state(api_env, plan["id"])
    assert restored == original  # days, items (ids too), transfers, summary and versions
    after = _get(api_env, plan["id"])
    assert after["version"] == 3
    assert {k: v for k, v in after.items() if k != "version"} == {
        k: v for k, v in original_read.items() if k != "version"
    }


def test_locked_items_never_move(api_env: ApiEnv) -> None:
    plan = _plan(api_env, days=2)
    locked = [d["items"][0] for d in plan["days"]] + [d["items"][-1] for d in plan["days"]]
    for item in locked:
        r = api_env.client.patch(
            f"/v1/items/{item['id']}", json={"locked": True}, headers=api_env.headers
        )
        assert r.status_code == 200
    current = _get(api_env, plan["id"])
    for _ in range(3):
        sight = _unplanned_sight(api_env, current)
        r = _preview(api_env, plan["id"], action="add_place", place_id=sight)
        if r.status_code == 422:
            assert r.json()["code"] == "recalculation_impossible" and r.json()["issues"]
            continue
        assert r.status_code == 201, r.text
        current = _apply(api_env, r.json()["id"]).json()["itinerary"]
        where = {
            i["id"]: (d["day_index"], i["start_time"], i["end_time"])
            for d in current["days"]
            for i in d["items"]
        }
        for item in locked:
            day = next(d["day_index"] for d in plan["days"] if item in d["items"])
            assert where[item["id"]] == (day, item["start_time"], item["end_time"])
    # A locked visit cannot be removed.
    visit = next(i for i in locked if i["type"] == "visit")
    r = _preview(api_env, plan["id"], action="remove_place", item_id=visit["id"])
    assert r.status_code == 422 and r.json()["issues"][0]["code"] == "ITEM_LOCKED"


def test_discarding_leaves_the_plan_as_it_was(api_env: ApiEnv) -> None:
    plan = _plan(api_env)
    before = _get(api_env, plan["id"])
    change = _preview(
        api_env, plan["id"], action="add_place", place_id=_unplanned_sight(api_env, plan)
    ).json()
    r = api_env.client.post(f"/v1/change-sets/{change['id']}/discard", headers=api_env.headers)
    assert r.status_code == 200 and r.json()["status"] == "discarded"
    assert _get(api_env, plan["id"]) == before
    assert _apply(api_env, change["id"]).json()["code"] == "change_set_closed"
    assert sql(api_env, "SELECT proposal FROM app.change_set") == [(None,)]


def test_a_preview_expires_when_the_plan_changes(api_env: ApiEnv) -> None:
    plan = _plan(api_env)
    change = _preview(
        api_env, plan["id"], action="add_place", place_id=_unplanned_sight(api_env, plan)
    ).json()
    first = plan["days"][0]["items"][0]
    api_env.client.patch(f"/v1/items/{first['id']}", json={"locked": True}, headers=api_env.headers)
    r = _apply(api_env, change["id"])
    assert r.status_code == 409 and r.json()["code"] == "change_set_stale"
    status = api_env.client.get(f"/v1/change-sets/{change['id']}", headers=api_env.headers)
    assert status.json()["status"] == "expired"
    # The hand edit kept the version it replaced.
    versions = api_env.client.get(
        f"/v1/itineraries/{plan['id']}/versions", headers=api_env.headers
    ).json()
    assert [(v["version"], v["change_set_id"]) for v in versions] == [(1, None)]


def test_a_new_preview_expires_the_open_one(api_env: ApiEnv) -> None:
    plan = _plan(api_env)
    first = _preview(
        api_env, plan["id"], action="add_place", place_id=_unplanned_sight(api_env, plan)
    ).json()
    item = plan["days"][0]["items"][0]
    second = _preview(api_env, plan["id"], action="remove_place", item_id=item["id"])
    assert second.status_code == 201
    assert _apply(api_env, first["id"]).json()["code"] == "change_set_closed"


def test_a_pinned_place_is_added_with_the_users_duration(api_env: ApiEnv) -> None:
    plan = _plan(api_env)
    [(lat, lon)] = sql(api_env, "SELECT ST_Y(geom), ST_X(geom) FROM geo.city WHERE id = 900101")
    place = _pin(api_env, "Friend's flat", lat + 0.002, lon + 0.002)
    r = _preview(api_env, plan["id"], action="add_place", user_place_id=place)
    assert r.status_code == 422 and r.json()["code"] == "duration_required"
    r = _preview(api_env, plan["id"], action="add_place", user_place_id=place, duration_minutes=45)
    assert r.status_code == 201, r.text
    itinerary = _apply(api_env, r.json()["id"]).json()["itinerary"]
    item = next(i for d in itinerary["days"] for i in d["items"] if i["user_place_id"] == place)
    assert (item["duration_minutes"], item["duration_source"], item["origin"]) == (
        45,
        "user",
        "user",
    )
    assert item["reason_texts"][0].startswith("You added this place")
    # The place is in use: it cannot be deleted while the plan has it.
    r = api_env.client.delete(f"/v1/user-places/{place}", headers=api_env.headers)
    assert r.status_code == 409


def test_a_distant_place_gets_a_day_at_a_new_base(api_env: ApiEnv) -> None:
    plan = _plan(api_env)
    [(lat, lon)] = sql(api_env, "SELECT ST_Y(geom), ST_X(geom) FROM geo.city WHERE id = 900101")
    east = lon + 60_000 / (111_320 * math.cos(math.radians(lat)))
    with psycopg.connect(api_env.database_url, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO geo.city (id, name, ascii_name, name_norm, country_iso2, population,"
            " timezone, feature_code, geom, licence_code)"
            " VALUES (900199, 'Fernstadt', 'Fernstadt', 'fernstadt', 'AT', 20000,"
            " 'Europe/Vienna', 'PPL', ST_SetSRID(ST_MakePoint(%s, %s), 4326), 'CC-BY-4.0')",
            (east, lat),
        )
    place = _pin(api_env, "Lake view", lat + 0.01, east + 0.01)
    r = _preview(api_env, plan["id"], action="add_place", user_place_id=place, duration_minutes=90)
    assert r.status_code == 201, r.text
    change = r.json()
    assert change["diff"]["base_changes"] == [
        {"day": 3, "old_base_name": "Testburg", "new_base_name": "Fernstadt"}
    ]
    diff_ = change["diff"]
    assert (
        diff_["travel_minutes_added"]
        == diff_["travel_minutes_after"] - diff_["travel_minutes_before"]
    )
    assert any(leg["to_name"] == "Fernstadt" for leg in change["diff"]["estimated_legs"])
    assert "NEW_BASE_DAY" in [n["code"] for n in change["notes"]]
    itinerary = _apply(api_env, change["id"]).json()["itinerary"]
    day3 = itinerary["days"][2]
    assert day3["base_city_name"] == "Fernstadt"
    assert day3["arrival"]["from_base_city_name"] == "Testburg"
    assert day3["arrival"]["confidence"] == "estimated"
    assert [i["user_place_id"] for i in day3["items"] if i["type"] == "visit"] == [place]


def test_infeasible_additions_say_which_constraint_conflicts(api_env: ApiEnv) -> None:
    plan = _plan(api_env, days=1)
    [(lat, lon)] = sql(api_env, "SELECT ST_Y(geom), ST_X(geom) FROM geo.city WHERE id = 900101")
    place = _pin(api_env, "All-day hike", lat, lon + 0.01)
    r = _preview(api_env, plan["id"], action="add_place", user_place_id=place, duration_minutes=700)
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "recalculation_impossible"
    assert [i["code"] for i in body["issues"]] == ["ADDITION_LONGER_THAN_DAY"]
    assert "700 min" in body["issues"][0]["text"]
    assert sql(api_env, "SELECT count(*) FROM app.change_set") == [(0,)]


def test_what_cannot_be_added_or_recalculated(api_env: ApiEnv) -> None:
    plan = _plan(api_env)
    restaurant = sql(api_env, "SELECT id FROM geo.place WHERE kind = 'restaurant' LIMIT 1")[0][0]
    r = _preview(api_env, plan["id"], action="add_place", place_id=str(restaurant))
    assert r.status_code == 422 and r.json()["code"] == "wrong_place_kind"
    sight_in_plan = plan["days"][0]["items"][0]["place_id"]
    r = _preview(api_env, plan["id"], action="add_place", place_id=sight_in_plan)
    assert r.status_code == 422 and r.json()["issues"][0]["code"] == "ALREADY_IN_PLAN"
    r = _preview(api_env, plan["id"], action="remove_place", item_id=str(uuid.uuid4()))
    assert r.status_code == 404
    manual = api_env.client.post(
        f"/v1/trips/{plan['trip_id']}/itineraries", headers=api_env.headers
    ).json()
    r = _preview(
        api_env, manual["id"], action="add_place", place_id=_unplanned_sight(api_env, plan)
    )
    assert r.status_code == 409 and r.json()["code"] == "not_recalculable"
    other = api_env.other_installation()
    r = api_env.client.post(
        f"/v1/itineraries/{plan['id']}/change-sets",
        json={"action": "add_place", "place_id": sight_in_plan},
        headers=other,
    )
    assert r.status_code == 404
    r = _preview(api_env, plan["id"], action="remove_place")
    assert r.status_code == 422
