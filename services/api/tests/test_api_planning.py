"""Plan generation through the API, on the imported fixture region (Testburg, Austria).

The routing adapter is off in the test environment, so transfers are labelled estimates, except
in the test that injects the Valhalla stub (no test reaches the network).
"""

import itertools
import time
import uuid
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from detour_api.main import create_app
from detour_api.planner.config import CONFIG_VERSION, ENGINE_VERSION
from detour_api.settings import Settings
from tests.conftest import TEST_SECRET, ApiEnv
from tests.planner_helpers import insert_synthetic_sights
from tests.valhalla_stub import ValhallaStub

pytestmark = pytest.mark.db

CITY = {"destination_kind": "city", "destination_ref": "900101"}  # Testburg


def sql(env: ApiEnv, query: str, *params: Any) -> list[tuple[Any, ...]]:
    with psycopg.connect(env.database_url, autocommit=True) as conn:
        cur = conn.execute(query, params)
        return cur.fetchall() if cur.description else []


def make_trip(env: ApiEnv, client: TestClient | None = None, **over: Any) -> dict[str, Any]:
    body = {"title": "Plan me", **CITY, "duration_days": 2, **over}
    r = (client or env.client).post("/v1/trips", json=body, headers=env.headers)
    assert r.status_code == 201, r.text
    trip: dict[str, Any] = r.json()
    return trip


def add_synthetic_sights(env: ApiEnv) -> int:
    """The planner's synthetic city fixture (invented places centred on Testburg) in this test's
    scratch database, so the region is big enough for two plans."""
    return insert_synthetic_sights(env.database_url)


def generate(env: ApiEnv, trip: dict[str, Any], client: TestClient | None = None) -> Any:
    return (client or env.client).post(
        f"/v1/trips/{trip['id']}/itineraries/generate", headers=env.headers
    )


def items_of(itinerary: dict[str, Any]) -> list[dict[str, Any]]:
    return [i for d in itinerary["days"] for i in d["items"]]


def test_generation_stores_versioned_valid_itineraries(api_env: ApiEnv) -> None:
    trip = make_trip(api_env, start_date="2027-05-01")
    r = generate(api_env, trip)
    assert r.status_code == 201, r.text
    body = r.json()
    plans = body["itineraries"]
    assert len(plans) == (2 if body["distinct"] else 1)
    assert body["max_jaccard_permille"] == 600
    codes = [n["code"] for n in body["notes"]]
    assert ("DISTINCT_PLANS" in codes) == body["distinct"] and "NO_OPENING_HOURS" in codes
    run_id = sql(api_env, "SELECT current_import_run_id FROM geo.region WHERE id = 'test-region'")
    for plan in plans:
        assert plan["profile"] in ("essentials", "wider") and plan["status"] == "proposed"
        assert (plan["engine_version"], plan["config_version"]) == (ENGINE_VERSION, CONFIG_VERSION)
        assert plan["import_run_id"] == str(run_id[0][0]) and plan["seed"] == 0
        assert plan["generation_id"] == body["generation_id"]
        assert [d["date"] for d in plan["days"]] == ["2027-05-01", "2027-05-02"]
        assert all(d["base_city_id"] == 900101 for d in plan["days"])
        assert all(d["base_city_name"] == "Testburg" and d["arrival"] is None for d in plan["days"])
        visits = [i for i in items_of(plan) if i["type"] == "visit"]
        assert plan["stats"]["visits"] == len(visits) > 0
        # ADR 026: a generated plan holds sights only, even where the data has places to eat.
        assert plan["stats"]["meals"] == 0 == len(items_of(plan)) - len(visits)
        assert all(n["text"] for n in plan["notes"])
        for day in plan["days"]:
            items = day["items"]
            for item, nxt in itertools.pairwise(items):
                assert item["end_time"] <= nxt["start_time"]
                assert item["transfer"]["to_item_id"] == nxt["id"]
                assert item["transfer"]["confidence"] == "estimated"  # adapter off in tests
            if items:
                assert items[0]["start_time"] == "09:00:00" and items[-1]["transfer"] is None
            for item in items:
                assert (item["origin"], item["duration_source"]) == ("engine", "category_default")
                assert item["reasons"] and len(item["reason_texts"]) == len(item["reasons"])
                assert item["type"] == "visit" and item["restaurant"] is None
    # The stored plan reads back exactly as it was returned.
    again = api_env.client.get(f"/v1/itineraries/{plans[0]['id']}", headers=api_env.headers)
    assert again.json() == plans[0]
    listed = api_env.client.get(f"/v1/trips/{trip['id']}/itineraries", headers=api_env.headers)
    assert {p["id"] for p in listed.json()} == {p["id"] for p in plans}


def test_a_larger_city_gets_two_distinct_itineraries(api_env: ApiEnv) -> None:
    add_synthetic_sights(api_env)
    r = generate(api_env, make_trip(api_env, duration_days=3))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["distinct"] and [p["profile"] for p in body["itineraries"]] == [
        "essentials",
        "wider",
    ]
    a, b = (
        {i["place_id"] for i in items_of(p) if i["type"] == "visit"} for p in body["itineraries"]
    )
    assert body["jaccard_permille"] == len(a & b) * 1000 // len(a | b) <= 600
    for plan in body["itineraries"]:
        assert plan["diversity_score"] == pytest.approx(body["jaccard_permille"] / 1000)
        assert all(d["items"] for d in plan["days"])
        # Planned time (visits and travel; the midday gap is not planned) over the 09:00-20:00 day.
        assert 550 <= plan["stats"]["day_utilisation_permille"] <= 900
        for day in plan["days"]:
            assert all(i["type"] == "visit" for i in day["items"])
            assert day["items"][-1]["end_time"] <= "20:00:00"


def test_a_small_town_gets_one_plan_and_the_reason(api_env: ApiEnv) -> None:
    body = generate(api_env, make_trip(api_env, duration_days=2)).json()
    assert not body["distinct"] and len(body["itineraries"]) == 1
    [note] = [n for n in body["notes"] if n["code"] == "SINGLE_PLAN"]
    assert note["text"].startswith("Only one plan is shown: ")
    assert body["jaccard_permille"] is None and body["itineraries"][0]["diversity_score"] is None


def test_every_item_is_an_imported_place_with_its_snapshot(api_env: ApiEnv) -> None:
    plans = generate(api_env, make_trip(api_env)).json()["itineraries"]
    for item in (i for p in plans for i in items_of(p)):
        [(kind, name, active)] = sql(
            api_env,
            "SELECT kind, name, is_active FROM geo.place WHERE id = %s",
            uuid.UUID(item["place_id"]),
        )
        assert (kind, name, active) == ("attraction", item["display_name"], True)


def test_generating_again_replaces_unselected_proposals_only(api_env: ApiEnv) -> None:
    trip = make_trip(api_env)
    first = generate(api_env, trip).json()["itineraries"]
    chosen = first[0]["id"]
    r = api_env.client.patch(
        f"/v1/trips/{trip['id']}", json={"selected_itinerary_id": chosen}, headers=api_env.headers
    )
    assert r.status_code == 200, r.text
    second = generate(api_env, trip).json()["itineraries"]
    ids = {
        p["id"]
        for p in api_env.client.get(
            f"/v1/trips/{trip['id']}/itineraries", headers=api_env.headers
        ).json()
    }
    assert ids == {chosen} | {p["id"] for p in second}
    assert not ({p["id"] for p in first} - {chosen}) & ids


def _testland(env: ApiEnv) -> dict[str, Any]:
    found: dict[str, Any] = env.client.get(
        "/v1/destinations/search", params={"q": "testland"}, headers=env.headers
    ).json()["results"][0]
    assert found["kind"] == "area"
    return found


def test_an_area_destination_is_planned_from_its_towns(api_env: ApiEnv) -> None:
    add_synthetic_sights(api_env)
    area = _testland(api_env)
    assert area["unavailable_reason"] is None
    trip = make_trip(api_env, destination_kind="area", destination_ref=area["ref"], duration_days=3)
    r = generate(api_env, trip)
    assert r.status_code == 201, r.text
    for plan in r.json()["itineraries"]:
        bases = {d["base_city_name"] for d in plan["days"]}
        # The synthetic sights surround Testburg; Mühlbach, 300 m away, has the same sights but
        # far fewer people, so Testburg is the base.
        assert bases == {"Testburg"}
        assert any(n["code"] == "BASE_CITY" for n in plan["notes"])
        assert all(d["base_city_id"] is not None for d in plan["days"])
        # Each day carries its base city's position from the gazetteer (ADR 021: the map's
        # transport markers), read by identifier when the plan is read.
        ((lat, lon),) = sql(
            api_env,
            "SELECT ST_Y(geom), ST_X(geom) FROM geo.city WHERE id = %s",
            plan["days"][0]["base_city_id"],
        )
        for d in plan["days"]:
            assert (d["base_city_lat"], d["base_city_lon"]) == (lat, lon)
        fetched = api_env.client.get(f"/v1/itineraries/{plan['id']}", headers=api_env.headers)
        assert fetched.json()["days"][0]["base_city_lat"] == lat


def test_an_area_without_enough_sights_explains_why(api_env: ApiEnv) -> None:
    trip = make_trip(api_env, destination_kind="area", destination_ref=_testland(api_env)["ref"])
    sql(api_env, "UPDATE geo.place SET is_active = false WHERE kind = 'attraction'")
    r = generate(api_env, trip)
    assert r.status_code == 422 and r.json()["issues"][0]["code"] == "NO_BASE_CITIES"


def test_areas_in_japan_are_single_city_only(api_env: ApiEnv) -> None:
    area = _testland(api_env)
    trip = make_trip(api_env, destination_kind="area", destination_ref=area["ref"])
    sql(api_env, "UPDATE geo.admin_area SET country_iso2 = 'JP'")
    found = _testland(api_env)
    assert found["unavailable_reason"] in ("area_single_city_only", "region_not_available")
    r = api_env.client.post(
        "/v1/trips",
        json={"title": "x", "destination_kind": "area", "destination_ref": area["ref"],
              "duration_days": 2},
        headers=api_env.headers,
    )  # fmt: skip
    assert r.status_code == 422 and r.json()["code"] == "area_single_city_only"
    r = generate(api_env, trip)  # a trip made before the rule
    assert r.status_code == 422 and r.json()["code"] == "area_single_city_only"


def test_a_past_trip_can_get_proposals(api_env: ApiEnv) -> None:
    add_synthetic_sights(api_env)
    trip = make_trip(api_env)
    api_env.client.post(f"/v1/trips/{trip['id']}/archive", headers=api_env.headers)
    assert generate(api_env, trip).status_code == 201


def test_a_region_that_is_no_longer_available_is_refused(api_env: ApiEnv) -> None:
    trip = make_trip(api_env)
    sql(api_env, "UPDATE geo.region SET status = 'disabled' WHERE id = 'test-region'")
    r = generate(api_env, trip)
    assert r.status_code == 409 and r.json()["code"] == "region_not_available"


def test_no_attractions_is_explained_with_the_exact_constraint(api_env: ApiEnv) -> None:
    trip = make_trip(api_env)
    sql(api_env, "UPDATE geo.place SET is_active = false WHERE kind = 'attraction'")
    r = generate(api_env, trip)
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "planning_impossible"
    assert body["issues"] == [
        {
            "code": "NO_CANDIDATES",
            "text": "There are no named sights within 15 km of Testburg in the imported data.",
        }
    ]
    assert body["detail"] == body["issues"][0]["text"]


def test_another_installation_cannot_plan_the_trip(api_env: ApiEnv) -> None:
    trip = make_trip(api_env)
    r = api_env.client.post(
        f"/v1/trips/{trip['id']}/itineraries/generate", headers=api_env.other_installation()
    )
    assert r.status_code == 404


def test_hand_edits_drop_transfers_that_no_longer_join_neighbours(api_env: ApiEnv) -> None:
    plans = generate(api_env, make_trip(api_env, duration_days=1)).json()["itineraries"]
    plan = max(plans, key=lambda p: len(items_of(p)))
    items = items_of(plan)
    assert len(items) >= 3
    r = api_env.client.patch(
        f"/v1/items/{items[0]['id']}", json={"position": len(items)}, headers=api_env.headers
    )
    assert r.status_code == 200, r.text
    after = api_env.client.get(f"/v1/itineraries/{plan['id']}", headers=api_env.headers).json()
    day = after["days"][0]["items"]
    for item, nxt in itertools.pairwise(day):
        assert item["transfer"] is None or item["transfer"]["to_item_id"] == nxt["id"]
    assert day[-1]["transfer"] is None
    assert day[-2]["transfer"] is None  # the moved item's new neighbour: not recomputed
    assert day[0]["transfer"] is not None  # untouched pairs keep theirs


def test_routed_times_come_from_the_provider_and_are_cached(api_env: ApiEnv) -> None:
    stub = ValhallaStub()
    settings = Settings(
        environment="test",
        token_secret=TEST_SECRET,
        database_url=api_env.database_url,
        routing_rate_per_second=1.0,
        routing_burst=10,
    )
    with TestClient(create_app(settings, routing_transport=stub.transport)) as client:
        trip = make_trip(api_env, client, duration_days=1)
        r = generate(api_env, trip, client)
        assert r.status_code == 201, r.text
        plans = r.json()["itineraries"]
        legs = [i["transfer"] for p in plans for i in items_of(p) if i["transfer"]]
        # Routed, except that the provider rule (1 request a second, a 3 s budget per plan, ADR 013)
        # can leave a leg of a longer day as a labelled estimate: at least four in five are routed.
        routed = [x for x in legs if x["confidence"] == "routed"]
        assert legs and len(routed) * 5 >= len(legs) * 4
        assert all(x["confidence"] in ("routed", "estimated") for x in legs)
        assert all(len(b["sources"]) == 1 for b in stub.bodies)  # the matrix-v1 shape
        cached = sql(api_env, "SELECT count(*) FROM geo.travel_time WHERE confidence = 'routed'")
        assert cached[0][0] >= len(routed)
        # A second generation reads the cache first: with routed times in hand it may choose
        # other legs, but no cell is ever asked for twice.
        first_requests = len(stub.requests)
        again = generate(api_env, make_trip(api_env, client, duration_days=1), client)
        assert again.status_code == 201
        assert len(stub.requests) - first_requests < first_requests
        asked = [
            (b["costing"], b["sources"][0]["lat"], b["sources"][0]["lon"], t["lat"], t["lon"])
            for b in stub.bodies
            for t in b["targets"]
        ]
        assert len(asked) == len(set(asked))


def test_generation_latency_is_within_the_kpi(api_env: ApiEnv) -> None:
    add_synthetic_sights(api_env)
    trip = make_trip(api_env, duration_days=7)
    started = time.perf_counter()
    r = generate(api_env, trip)
    elapsed = time.perf_counter() - started
    assert r.status_code == 201
    assert elapsed < 5.0, f"plan generation took {elapsed:.2f} s"
