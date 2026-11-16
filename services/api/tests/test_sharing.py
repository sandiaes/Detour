"""Sharing trips with a linked person (ADR 034, step 3): your name, invite codes, Who's going,
Share, Leave and Stop sharing."""

from typing import Any

import pytest

from tests.conftest import ApiEnv
from tests.test_api_trips import code, make_trip, sql, trip_body

pytestmark = pytest.mark.db


def _me(env: ApiEnv, headers: dict[str, str]) -> dict[str, Any]:
    body: dict[str, Any] = env.client.get("/v1/me", headers=headers).json()
    return body


def _link(env: ApiEnv, inviter: dict[str, str], invitee: dict[str, str]) -> None:
    made = env.client.post("/v1/me/invite-codes", headers=inviter)
    assert made.status_code == 201, made.text
    linked = env.client.post("/v1/people/link", json={"code": made.json()["code"]}, headers=invitee)
    assert linked.status_code == 200, linked.text


def test_a_name_can_be_set_and_cleared(api_env: ApiEnv) -> None:
    c, h = api_env.client, api_env.headers
    assert _me(api_env, h)["display_name"] is None
    named = c.patch("/v1/me", json={"display_name": "  Jose   M  "}, headers=h)
    assert named.status_code == 200 and named.json()["display_name"] == "Jose M"
    assert c.patch("/v1/me", json={"display_name": "x" * 41}, headers=h).status_code == 422
    assert c.patch("/v1/me", json={"display_name": " "}, headers=h).json()["display_name"] is None


def test_an_invite_code_links_two_people_once(api_env: ApiEnv) -> None:
    c, me = api_env.client, api_env.headers
    partner = api_env.other_installation()
    c.patch("/v1/me", json={"display_name": "Ana"}, headers=partner)
    _link(api_env, me, partner)
    mine = _me(api_env, me)["people"]
    assert [(p["name"], p["person_id"]) for p in mine] == [
        ("Ana", _me(api_env, partner)["person_id"])
    ]
    assert [p["person_id"] for p in _me(api_env, partner)["people"]] == [
        str(api_env.installation_id)
    ]

    again = c.post("/v1/me/invite-codes", headers=me).json()["code"]
    refused = c.post("/v1/people/link", json={"code": again}, headers=partner)
    assert refused.status_code == 409 and code(refused) == "already_linked"
    own = c.post("/v1/me/invite-codes", headers=me).json()["code"]
    refused = c.post("/v1/people/link", json={"code": own}, headers=me)
    assert refused.status_code == 409 and code(refused) == "own_invite"
    # An invite code cannot add a phone, and a phone code cannot link a person.
    invite = c.post("/v1/me/invite-codes", headers=me).json()["code"]
    stranger = api_env.other_installation()
    assert code(c.post("/v1/installations/join", json={"code": invite}, headers=stranger)) == (
        "code_invalid"
    )
    device = c.post("/v1/me/link-codes", headers=me).json()["code"]
    assert code(c.post("/v1/people/link", json={"code": device}, headers=stranger)) == (
        "code_invalid"
    )


def test_whos_going_shares_a_new_trip_and_both_edit_it(api_env: ApiEnv) -> None:
    c, me = api_env.client, api_env.headers
    partner = api_env.other_installation()
    c.patch("/v1/me", json={"display_name": "Ana"}, headers=partner)
    c.patch("/v1/me", json={"display_name": "Jose"}, headers=me)
    _link(api_env, partner, me)
    ana = _me(api_env, partner)["person_id"]

    created = c.post("/v1/trips", json=trip_body(title="Lisbon", share_with=[ana]), headers=me)
    assert created.status_code == 201, created.text
    trip = created.json()
    assert trip["role"] == "owner"
    assert [(m["name"], m["role"], m["you"]) for m in trip["members"]] == [
        ("Jose", "owner", True),
        ("Ana", "editor", False),
    ]
    theirs = c.get(f"/v1/trips/{trip['id']}", headers=partner).json()
    assert theirs["role"] == "editor" and [m["you"] for m in theirs["members"]] == [False, True]
    assert (
        c.patch(f"/v1/trips/{trip['id']}", json={"title": "Porto"}, headers=partner).json()["title"]
        == "Porto"
    )

    # Only someone linked can be chosen.
    stranger = _me(api_env, api_env.other_installation())["person_id"]
    refused = c.post("/v1/trips", json=trip_body(share_with=[stranger]), headers=me)
    assert refused.status_code == 409 and code(refused) == "not_linked"
    assert sql(api_env, "SELECT count(*) FROM app.trip") == [(1,)]  # nothing was created


def test_share_leave_and_stop_sharing(api_env: ApiEnv) -> None:
    c, me = api_env.client, api_env.headers
    partner = api_env.other_installation()
    _link(api_env, me, partner)
    ana = _me(api_env, partner)["person_id"]
    trip = make_trip(api_env, title="Solo first")
    url = f"/v1/trips/{trip['id']}/members"
    assert c.get("/v1/trips", headers=partner).json() == []  # solo trips stay private

    shared = c.post(url, json={"person_id": ana}, headers=me)
    assert shared.status_code == 200 and len(shared.json()["members"]) == 2
    assert code(c.post(url, json={"person_id": ana}, headers=me)) == "already_member"
    # A member cannot change who is on the trip or delete it.
    assert code(c.delete(f"{url}/{api_env.installation_id}", headers=partner)) == "not_trip_owner"
    assert code(c.delete(f"/v1/trips/{trip['id']}", headers=partner)) == "not_trip_owner"

    # Leave.
    assert c.delete(f"{url}/{ana}", headers=partner).status_code == 204
    assert c.get("/v1/trips", headers=partner).json() == []
    # The owner cannot leave.
    left = c.delete(f"{url}/{api_env.installation_id}", headers=me)
    assert left.status_code == 409 and code(left) == "owner_cannot_leave"

    # Share again, then stop sharing.
    c.post(url, json={"person_id": ana}, headers=me)
    assert c.delete(f"{url}/{ana}", headers=me).status_code == 204
    assert c.get(f"/v1/trips/{trip['id']}", headers=partner).status_code == 404


def test_unlinking_keeps_shared_trips_but_stops_new_sharing(api_env: ApiEnv) -> None:
    c, me = api_env.client, api_env.headers
    partner = api_env.other_installation()
    _link(api_env, me, partner)
    ana = _me(api_env, partner)["person_id"]
    trip = c.post("/v1/trips", json=trip_body(share_with=[ana]), headers=me).json()
    assert c.delete(f"/v1/people/{ana}", headers=me).status_code == 204
    assert _me(api_env, me)["people"] == []
    assert c.get(f"/v1/trips/{trip['id']}", headers=partner).status_code == 200
    other = make_trip(api_env)
    refused = c.post(f"/v1/trips/{other['id']}/members", json={"person_id": ana}, headers=me)
    assert code(refused) == "not_linked"
    assert c.delete(f"/v1/people/{ana}", headers=me).status_code == 404


def test_a_joining_phone_brings_its_links(api_env: ApiEnv) -> None:
    c, me = api_env.client, api_env.headers
    phone_b, partner = api_env.other_installation(), api_env.other_installation()
    _link(api_env, partner, phone_b)  # B linked to the partner before it became one of mine
    value = c.post("/v1/me/link-codes", headers=me).json()["code"]
    assert (
        c.post("/v1/installations/join", json={"code": value}, headers=phone_b).status_code == 200
    )
    partner_id = _me(api_env, partner)["person_id"]
    assert [p["person_id"] for p in _me(api_env, me)["people"]] == [partner_id]
    assert [p["person_id"] for p in _me(api_env, partner)["people"]] == [
        str(api_env.installation_id)
    ]
