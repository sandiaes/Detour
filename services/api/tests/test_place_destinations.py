"""Trips to places outside the imported regions (ADR 027): a snapshot destination, an empty trip by
nature, no suggestions, history and photos that need no ``geo`` row."""

from typing import Any

import pytest

from tests.conftest import ApiEnv
from tests.test_api_planning import generate, sql
from tests.test_api_trips import add_item, make_itinerary
from tests.test_past_trips import _archive, _visits

pytestmark = pytest.mark.db

PHOTON = {
    "destination_kind": "place",
    "destination_ref": "photon:N4242",
    "destination_name": "Hallstatt",
    "destination_lat": 47.5622,
    "destination_lon": 13.6493,
    "destination_country": "at",
}


def _create(env: ApiEnv, **over: Any) -> Any:
    body = {"title": "Hallstatt", "duration_days": 2, **PHOTON, **over}
    return env.client.post("/v1/trips", json=body, headers=env.headers)


def test_a_place_trip_is_a_snapshot_that_needs_no_geo_row(api_env: ApiEnv) -> None:
    r = _create(api_env)
    assert r.status_code == 201, r.text
    trip = r.json()
    assert trip["destination"] == {
        "kind": "place",
        "ref": "photon:N4242",
        "name": "Hallstatt",
        "lat": 47.5622,
        "lon": 13.6493,
        "country_iso2": "AT",
    }
    assert trip["stops"] == [] and trip["cover_image"] is None
    again = api_env.client.get(f"/v1/trips/{trip['id']}", headers=api_env.headers).json()
    assert again["destination"]["name"] == "Hallstatt"


@pytest.mark.parametrize(
    "ref",
    ["photon:N4242", "geonames:2761369", f"area:{'0' * 8}-0000-4000-8000-{'0' * 12}", "manual"],
)
def test_every_provider_reference_is_accepted(api_env: ApiEnv, ref: str) -> None:
    assert _create(api_env, destination_ref=ref).status_code == 201


@pytest.mark.parametrize(
    "over",
    [
        {"destination_ref": "photon:xyz"},
        {"destination_ref": "nominatim:1"},
        {"destination_ref": None},
        {"destination_name": None},
        {"destination_lat": None},
        {"destination_lat": 91},
        {"destination_country": "AUT"},
        {"stops": [{"city_id": 1, "days": 1}]},
    ],
)
def test_a_malformed_place_is_refused(api_env: ApiEnv, over: dict[str, Any]) -> None:
    assert _create(api_env, **over).status_code == 422


def test_only_a_place_carries_a_name_and_point(api_env: ApiEnv) -> None:
    r = api_env.client.post(
        "/v1/trips",
        json={
            "title": "x",
            "destination_kind": "city",
            "destination_ref": "900101",
            "destination_name": "Sneaky",
            "duration_days": 1,
        },
        headers=api_env.headers,
    )
    assert r.status_code == 422


def test_an_empty_plan_can_be_filled_by_hand_and_nothing_is_suggested(api_env: ApiEnv) -> None:
    trip = _create(api_env).json()
    plan = make_itinerary(api_env, trip)
    assert plan["profile"] == "manual"
    pin = api_env.client.post(
        "/v1/user-places",
        json={
            "kind": "location",
            "name": "Seeplatz",
            "lat": 47.56,
            "lon": 13.65,
            "source": "manual_pin",
        },
        headers=api_env.headers,
    ).json()
    added = add_item(api_env, plan, 1, type="visit", user_place_id=pin["id"], duration_minutes=60)
    assert added.status_code == 201, added.text

    r = generate(api_env, trip)
    assert r.status_code == 409 and r.json()["code"] == "destination_not_plannable"
    preview = api_env.client.post(
        f"/v1/itineraries/{plan['id']}/place-suggestions",
        json={"user_place_id": pin["id"], "duration_minutes": 60},
        headers=api_env.headers,
    )
    assert preview.status_code in (404, 409, 422)


def test_a_past_place_trip_keeps_its_days_and_a_city_row_from_the_snapshot(
    api_env: ApiEnv,
) -> None:
    trip = _create(api_env).json()
    plan = make_itinerary(api_env, trip)
    pin = api_env.client.post(
        "/v1/user-places",
        json={
            "kind": "location",
            "name": "Seeplatz",
            "lat": 47.56,
            "lon": 13.65,
            "source": "manual_pin",
        },
        headers=api_env.headers,
    ).json()
    add_item(
        api_env,
        plan,
        1,
        type="visit",
        user_place_id=pin["id"],
        duration_minutes=60,
        start_time="10:00",
    )
    api_env.client.patch(
        f"/v1/trips/{trip['id']}",
        json={"selected_itinerary_id": plan["id"]},
        headers=api_env.headers,
    )
    past = _archive(api_env, trip)
    assert past["status"] == "past" and past["destination"]["kind"] == "place"
    rows = [
        (v["kind"], v["name"], v["geo_place_ref"], v["start_time"]) for v in _visits(api_env, trip)
    ]
    assert rows == [("city", "Hallstatt", None, None), ("attraction", "Seeplatz", None, "10:00")]


def test_a_gazetteer_place_borrows_its_citys_photo_and_photon_places_have_none(
    api_env: ApiEnv,
) -> None:
    from sqlalchemy import create_engine

    from detour_api.repo import trips as trips_repo

    gaz = _create(api_env, destination_ref="geonames:900101").json()
    photon = _create(api_env).json()
    manual = _create(api_env, destination_ref="manual").json()
    engine = create_engine(api_env.database_url.replace("postgresql://", "postgresql+psycopg://"))
    with engine.connect() as conn:
        assert trips_repo.cover_destinations(conn, gaz["id"]) == [("city", "900101")]
        assert trips_repo.cover_destinations(conn, photon["id"]) == []
        assert trips_repo.cover_destinations(conn, manual["id"]) == []
    engine.dispose()
    assert sql(api_env, "SELECT count(*) FROM app.trip WHERE destination_kind = 'place'") == [(3,)]


def test_the_wider_search_asks_photon_even_when_the_gazetteer_answers(api_env: ApiEnv) -> None:
    c, h = api_env.client, api_env.headers
    plain = c.get(
        "/v1/destinations/search", params={"q": "testburg", "include_external": "true"}, headers=h
    ).json()
    assert plain["results"] and plain["external"]["state"] == "not_needed"
    assert api_env.photon_requests == []
    wide = c.get(
        "/v1/destinations/search",
        params={"q": "testburg", "include_external": "true", "also_if_found": "true"},
        headers=h,
    ).json()
    assert wide["results"] and wide["external"]["state"] == "ok"
    assert len(api_env.photon_requests) == 1
