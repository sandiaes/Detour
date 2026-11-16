"""Trips belong to people, with members (ADR 034, step 2): every member reads and changes a trip,
only its owner deletes it, and someone who is not a member sees nothing. Sharing from the app is
step 3; here a member is added directly in the database."""

import uuid
from typing import Any

import pytest

from tests.conftest import ApiEnv
from tests.test_api_trips import code, make_itinerary, make_trip, sql, trip_body

pytestmark = pytest.mark.db


def _person_of(env: ApiEnv, headers: dict[str, str]) -> str:
    person: str = env.client.get("/v1/me", headers=headers).json()["person_id"]
    return person


def _share(env: ApiEnv, trip: dict[str, Any], headers: dict[str, str]) -> None:
    sql(
        env,
        "INSERT INTO app.trip_member (trip_id, person_id, role, added_by)"
        " VALUES (%s, %s, 'editor', %s)",
        trip["id"],
        _person_of(env, headers),
        str(env.installation_id),
    )


def test_a_new_trip_has_its_creator_as_owner(api_env: ApiEnv) -> None:
    trip = make_trip(api_env)
    rows = sql(
        api_env, "SELECT person_id, role FROM app.trip_member WHERE trip_id = %s", trip["id"]
    )
    assert rows == [(api_env.installation_id, "owner")]
    owner = sql(api_env, "SELECT owner_person_id FROM app.trip WHERE id = %s", trip["id"])
    assert owner == [(api_env.installation_id,)]


def test_a_member_reads_and_changes_the_trip_but_only_the_owner_deletes_it(
    api_env: ApiEnv,
) -> None:
    c = api_env.client
    trip = make_trip(api_env, title="Together")
    plan = make_itinerary(api_env, trip)
    partner = api_env.other_installation()
    stranger = api_env.other_installation()
    _share(api_env, trip, partner)

    assert [t["title"] for t in c.get("/v1/trips", headers=partner).json()] == ["Together"]
    assert c.get(f"/v1/trips/{trip['id']}", headers=partner).status_code == 200
    renamed = c.patch(f"/v1/trips/{trip['id']}", json={"title": "Ours"}, headers=partner)
    assert renamed.status_code == 200 and renamed.json()["title"] == "Ours"
    assert c.get(f"/v1/itineraries/{plan['id']}", headers=partner).status_code == 200

    # The partner adds a restaurant of their own; the owner sees it in the plan.
    place = c.post(
        "/v1/user-places",
        json={
            "kind": "restaurant",
            "name": "Ours to eat",
            "lat": 48.2,
            "lon": 16.37,
            "source": "manual_pin",
        },
        headers=partner,
    ).json()
    added = c.post(
        f"/v1/itineraries/{plan['id']}/days/1/items",
        json={"type": "meal", "user_place_id": place["id"]},
        headers=partner,
    )
    assert added.status_code == 201, added.text
    item = c.get(f"/v1/items/{added.json()['id']}", headers=api_env.headers)
    assert item.status_code == 200 and item.json()["display_name"] == "Ours to eat"
    # Places stay their creator's: the owner's list of own places does not show it.
    assert c.get("/v1/user-places", headers=api_env.headers).json() == []

    for headers in (stranger,):
        assert c.get(f"/v1/trips/{trip['id']}", headers=headers).status_code == 404
        assert c.get(f"/v1/itineraries/{plan['id']}", headers=headers).status_code == 404
        assert c.get("/v1/trips", headers=headers).json() == []

    refused = c.delete(f"/v1/trips/{trip['id']}", headers=partner)
    assert refused.status_code == 403 and code(refused) == "not_trip_owner"
    assert c.delete(f"/v1/trips/{trip['id']}", headers=api_env.headers).status_code == 204
    assert c.get("/v1/trips", headers=partner).json() == []


def test_the_trip_limit_counts_only_the_trips_you_own(api_env: ApiEnv) -> None:
    partner = api_env.other_installation()
    theirs = api_env.client.post("/v1/trips", json=trip_body(title="Theirs"), headers=partner)
    _share(api_env, {"id": theirs.json()["id"]}, api_env.headers)
    owned = sql(
        api_env,
        "SELECT count(*) FROM app.trip WHERE owner_person_id = %s",
        str(api_env.installation_id),
    )
    assert owned == [(0,)]
    assert len(api_env.client.get("/v1/trips", headers=api_env.headers).json()) == 1


def test_a_phone_joining_keeps_the_trips_it_is_a_member_of(api_env: ApiEnv) -> None:
    """Phone B was a member of A's trip as its own person; joining A turns that into A's own
    trip once (the owner role wins) instead of two rows."""
    trip = make_trip(api_env, title="Mine")
    phone_b = api_env.other_installation()
    _share(api_env, trip, phone_b)
    value = api_env.client.post("/v1/me/link-codes", headers=api_env.headers).json()["code"]
    joined = api_env.client.post("/v1/installations/join", json={"code": value}, headers=phone_b)
    assert joined.status_code == 200, joined.text
    rows = sql(
        api_env, "SELECT person_id, role FROM app.trip_member WHERE trip_id = %s", trip["id"]
    )
    assert rows == [(api_env.installation_id, "owner")]
    assert [t["title"] for t in api_env.client.get("/v1/trips", headers=phone_b).json()] == ["Mine"]


def test_one_owner_per_trip(api_env: ApiEnv) -> None:
    trip = make_trip(api_env)
    other = uuid.uuid4()
    sql(api_env, "INSERT INTO app.person (id) VALUES (%s)", other)
    with pytest.raises(Exception, match="trip_member_one_owner"):
        sql(
            api_env,
            "INSERT INTO app.trip_member (trip_id, person_id, role) VALUES (%s, %s, 'owner')",
            trip["id"],
            other,
        )
