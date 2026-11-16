"""Two people changing the same trip (ADR 034, step 4): a change made on an older version is
refused with 409 instead of silently overwriting, and the plan says who changed it last."""

from typing import Any

import pytest

from tests.conftest import ApiEnv
from tests.test_api_trips import code, make_itinerary, make_trip
from tests.test_sharing import _link, _me

pytestmark = pytest.mark.db

VISIT = {"type": "free_time", "duration_minutes": 30}


def _plan(env: ApiEnv, plan_id: str, headers: dict[str, str]) -> dict[str, Any]:
    body: dict[str, Any] = env.client.get(f"/v1/itineraries/{plan_id}", headers=headers).json()
    return body


def _shared_plan(env: ApiEnv) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    partner = env.other_installation()
    env.client.patch("/v1/me", json={"display_name": "Ana"}, headers=partner)
    _link(env, env.headers, partner)
    trip = make_trip(env)
    env.client.post(
        f"/v1/trips/{trip['id']}/members",
        json={"person_id": _me(env, partner)["person_id"]},
        headers=env.headers,
    )
    return trip, make_itinerary(env, trip), partner


def test_a_change_on_an_older_version_is_refused(api_env: ApiEnv) -> None:
    c, me = api_env.client, api_env.headers
    _trip, plan, partner = _shared_plan(api_env)
    url = f"/v1/itineraries/{plan['id']}/days/1/items"
    seen = _plan(api_env, plan["id"], me)["version"]

    # The partner adds a stop first, from the same version.
    first = c.post(url, json=VISIT, headers={**partner, "If-Match": f'"{seen}"'})
    assert first.status_code == 201, first.text
    late = c.post(url, json=VISIT, headers={**me, "If-Match": f'"{seen}"'})
    assert late.status_code == 409 and code(late) == "plan_changed"
    assert late.json()["current_version"] == seen + 1

    # Read again, then it works; editing and removing are checked the same way.
    now = _plan(api_env, plan["id"], me)["version"]
    item = first.json()["id"]
    stale = {**me, "If-Match": f'"{seen}"'}
    assert code(c.patch(f"/v1/items/{item}", json={"locked": True}, headers=stale)) == (
        "plan_changed"
    )
    assert code(c.delete(f"/v1/items/{item}", headers=stale)) == "plan_changed"
    fresh = {**me, "If-Match": f'"{now}"'}
    assert c.patch(f"/v1/items/{item}", json={"locked": True}, headers=fresh).status_code == 200
    # Without the header nothing is checked (older apps, scripts).
    assert c.post(url, json=VISIT, headers=me).status_code == 201
    assert c.post(url, json=VISIT, headers={**me, "If-Match": "soon"}).status_code == 422


def test_the_plan_says_who_changed_it_last(api_env: ApiEnv) -> None:
    c, me = api_env.client, api_env.headers
    _trip, plan, partner = _shared_plan(api_env)
    mine = _plan(api_env, plan["id"], me)["last_change"]
    assert mine["you"] is True and mine["person_id"] == str(api_env.installation_id)

    c.post(f"/v1/itineraries/{plan['id']}/days/1/items", json=VISIT, headers=partner)
    theirs = _plan(api_env, plan["id"], me)["last_change"]
    assert theirs["you"] is False and theirs["name"] == "Ana"
    assert _plan(api_env, plan["id"], partner)["last_change"]["you"] is True


def test_a_trip_changed_by_someone_else_is_not_overwritten(api_env: ApiEnv) -> None:
    c, me = api_env.client, api_env.headers
    trip, _plan_body, partner = _shared_plan(api_env)
    seen = c.get(f"/v1/trips/{trip['id']}", headers=me).json()["updated_at"]
    renamed = c.patch(
        f"/v1/trips/{trip['id']}", json={"title": "Porto"}, headers={**partner, "If-Match": seen}
    )
    assert renamed.status_code == 200, renamed.text
    late = c.patch(
        f"/v1/trips/{trip['id']}", json={"title": "Lisbon"}, headers={**me, "If-Match": seen}
    )
    assert late.status_code == 409 and code(late) == "trip_changed"
    now = c.get(f"/v1/trips/{trip['id']}", headers=me).json()["updated_at"]
    ok = c.patch(
        f"/v1/trips/{trip['id']}", json={"title": "Lisbon"}, headers={**me, "If-Match": now}
    )
    assert ok.status_code == 200 and ok.json()["title"] == "Lisbon"
