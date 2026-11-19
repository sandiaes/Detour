"""Removing a region's imported data (ADR 033): owner only; a place a trip names is kept; the rest
goes; the region can be imported again.

Plans come from the planner on its synthetic sights (Testburg)."""

from typing import Any

import pytest

from tests.conftest import ApiEnv
from tests.test_api_planning import add_synthetic_sights, make_trip, sql
from tests.test_api_trips import CITY, add_item, make_itinerary

pytestmark = pytest.mark.db

REGION = "test-region"


def _owner(env: ApiEnv) -> None:
    app: Any = env.client.app
    app.state.settings.owner_installation_ids = str(env.installation_id)


def _city_trip() -> dict[str, Any]:
    return {**CITY, "title": "Again", "duration_days": 1}


def _places(env: ApiEnv) -> list[tuple[Any, ...]]:
    return sql(
        env, "SELECT id::text, is_active FROM geo.place WHERE region_id = %s ORDER BY id", REGION
    )


def _trip_with_one_sight(env: ApiEnv) -> tuple[dict[str, Any], str]:
    """A trip with one stop at a real imported place; returns the trip and the place id."""
    add_synthetic_sights(env)
    trip = make_trip(env, duration_days=2, start_date="2027-05-01")
    plan = make_itinerary(env, trip)
    museum = env.client.get(
        "/v1/places/search", params={"q": "testburg museum"}, headers=env.headers
    ).json()["results"][0]
    add_item(env, plan, 1, type="visit", place_id=museum["id"], duration_minutes=60)
    return trip, str(museum["id"])


def test_only_the_owner_may_preview_or_remove(api_env: ApiEnv) -> None:
    c, h = api_env.client, api_env.headers
    preview = c.get(f"/v1/regions/{REGION}/removal-preview", headers=h)
    removal = c.delete(f"/v1/regions/{REGION}", headers=h)
    for refused in (preview, removal):  # nobody is the owner until it is configured
        assert refused.status_code == 403 and refused.json()["code"] == "not_owner"
    _owner(api_env)
    assert c.get(f"/v1/regions/{REGION}/removal-preview", headers=h).status_code == 200
    other = c.get(f"/v1/regions/{REGION}/removal-preview", headers=api_env.other_installation())
    assert other.status_code == 403
    assert c.get("/v1/regions/nowhere/removal-preview", headers=h).status_code == 404


def test_the_preview_counts_what_goes_and_what_a_trip_keeps(api_env: ApiEnv) -> None:
    trip, _ = _trip_with_one_sight(api_env)
    _owner(api_env)
    before = _places(api_env)
    r = api_env.client.get(f"/v1/regions/{REGION}/removal-preview", headers=api_env.headers)
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["places_total"] == len(before) and p["places_kept"] == 1
    assert p["places_removed"] == len(before) - 1
    assert [t["id"] for t in p["trips"]] == [trip["id"]]
    assert p["bytes_freed_estimate"] > 0
    assert _places(api_env) == before  # a preview changes nothing


def test_removal_keeps_what_a_trip_names_and_deletes_the_rest(api_env: ApiEnv) -> None:
    trip, place_id = _trip_with_one_sight(api_env)
    _owner(api_env)
    c, h = api_env.client, api_env.headers
    assert c.post(f"/v1/trips/{trip['id']}/archive", headers=h).status_code == 200
    plan_id = c.get(f"/v1/trips/{trip['id']}/itineraries", headers=h).json()[0]["id"]
    shown = c.get(f"/v1/itineraries/{plan_id}", headers=h).json()
    # Names stored for a place that goes and for the one that stays.
    others = [row[0] for row in _places(api_env) if row[0] != place_id]
    for ref in (place_id, others[0]):
        sql(
            api_env,
            "INSERT INTO geo.place_name (entity_kind, entity_ref, lang, name, name_norm, name_type,"
            " source, licence_code, confidence, retrieved_at, expires_at)"
            " VALUES ('place', %s, 'en', 'x', 'x', 'official_english', 'wikidata', 'CC0-1.0',"
            " 0.9, now(), now() + interval '1 day')",
            ref,
        )

    r = c.delete(f"/v1/regions/{REGION}", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["places_kept"] == 1
    # Only the named place is left, inactive; its name is kept and the other's is gone.
    assert _places(api_env) == [(place_id, False)]
    assert sql(api_env, "SELECT entity_ref FROM geo.place_name") == [(place_id,)]
    assert sql(api_env, "SELECT count(*) FROM geo.place_source") == [(1,)]
    # The region is disabled and has no data version; the gazetteer is untouched.
    region = next(x for x in c.get("/v1/regions", headers=h).json() if x["id"] == REGION)
    assert region["status"] == "disabled" and region["data_version"] is None
    assert int(sql(api_env, "SELECT count(*) FROM geo.city")[0][0]) > 0
    # The past trip reads exactly as before.
    after = c.get(f"/v1/itineraries/{plan_id}", headers=h).json()
    assert (
        after["days"][0]["items"][0]["display_name"] == shown["days"][0]["items"][0]["display_name"]
    )
    # The place is no longer found by search and the region is no longer planned for.
    found = c.get("/v1/places/search", params={"q": "testburg museum"}, headers=h)
    assert place_id not in [x["id"] for x in found.json()["results"]]
    again = c.post("/v1/trips", json=_city_trip(), headers=h)
    assert again.status_code == 409 and again.json()["code"] == "region_not_available"


def test_removal_waits_for_an_import_and_can_be_repeated(api_env: ApiEnv) -> None:
    _owner(api_env)
    c, h = api_env.client, api_env.headers
    sql(api_env, "UPDATE geo.region SET status = 'importing' WHERE id = %s", REGION)
    busy = c.delete(f"/v1/regions/{REGION}", headers=h)
    assert busy.status_code == 409 and busy.json()["code"] == "import_running"
    sql(api_env, "UPDATE geo.region SET status = 'disabled' WHERE id = %s", REGION)
    assert c.delete(f"/v1/regions/{REGION}", headers=h).status_code == 200
    second = c.delete(f"/v1/regions/{REGION}", headers=h)
    assert second.status_code == 200 and second.json()["places_total"] == 0


def _city_ids(env: ApiEnv) -> set[int]:
    return {int(r[0]) for r in sql(env, "SELECT id FROM geo.city WHERE country_iso2 = 'AT'")}


def test_removal_takes_the_countrys_cities_except_those_a_trip_names(api_env: ApiEnv) -> None:
    trip, _ = _trip_with_one_sight(api_env)  # a trip to Testburg (city 900101)
    _owner(api_env)
    c, h = api_env.client, api_env.headers
    for new_id in (990001, 990002):  # two more Austrian cities that no trip names
        sql(
            api_env,
            "INSERT INTO geo.city SELECT (json_populate_record(c, json_build_object("
            "'id', %s::bigint, 'name', 'Extra', 'ascii_name', 'Extra', 'name_norm', 'extra',"
            " 'alt_names', '{}'::text[], 'alt_names_norm', '{}'::text[]))).* FROM geo.city c"
            " WHERE c.id = 900101",
            new_id,
        )
    before = _city_ids(api_env)
    assert 900101 in before and len(before) > 1
    p = c.get(f"/v1/regions/{REGION}/removal-preview", headers=h).json()
    assert p["cities_kept"] >= 1 and p["cities_removed"] == len(before) - p["cities_kept"]
    assert _city_ids(api_env) == before  # a preview changes nothing

    assert c.delete(f"/v1/regions/{REGION}", headers=h).status_code == 200
    after = _city_ids(api_env)
    assert 900101 in after and len(after) == p["cities_kept"] < len(before)
    # The trip still opens on its city.
    assert c.get(f"/v1/trips/{trip['id']}", headers=h).status_code == 200


def test_removal_keeps_the_cities_while_another_region_with_data_covers_the_country(
    api_env: ApiEnv,
) -> None:
    _owner(api_env)
    sql(
        api_env,
        "INSERT INTO geo.region SELECT (r).* FROM (SELECT json_populate_record(r, "
        "json_build_object('id', 'other-at')) AS r FROM geo.region r WHERE r.id = %s) x",
        REGION,
    )
    sql(
        api_env,
        "UPDATE geo.place SET region_id = 'other-at' WHERE id = "
        "(SELECT id FROM geo.place WHERE region_id = %s AND is_active ORDER BY id LIMIT 1)",
        REGION,
    )
    before = _city_ids(api_env)
    p = api_env.client.get(f"/v1/regions/{REGION}/removal-preview", headers=api_env.headers).json()
    assert p["cities_removed"] == 0
    assert (
        api_env.client.delete(f"/v1/regions/{REGION}", headers=api_env.headers).status_code == 200
    )
    assert _city_ids(api_env) == before
