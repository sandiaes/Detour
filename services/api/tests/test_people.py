"""People and their devices (ADR 034, step 1): a second phone joins with a one-time code and sees
the same trips; the recovery code signs out every other phone; a removed phone is refused."""

import uuid
from typing import Any

import pytest

from detour_api.repo import people
from tests.conftest import ApiEnv
from tests.test_api_trips import code, make_trip, sql, trip_body


def _trip_as(env: ApiEnv, headers: dict[str, str], title: str) -> None:
    response = env.client.post("/v1/trips", json=trip_body(title=title), headers=headers)
    assert response.status_code == 201, response.text


pytestmark = pytest.mark.db


def _trip_titles(env: ApiEnv, headers: dict[str, str]) -> list[str]:
    response = env.client.get("/v1/trips", headers=headers)
    assert response.status_code == 200, response.text
    return sorted(t["title"] for t in response.json())


def _link_code(env: ApiEnv, headers: dict[str, str]) -> str:
    response = env.client.post("/v1/me/link-codes", headers=headers)
    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store"
    value: str = response.json()["code"]
    return value


def _join(env: ApiEnv, headers: dict[str, str], value: str) -> Any:
    return env.client.post("/v1/installations/join", json={"code": value}, headers=headers)


def test_a_new_phone_is_its_own_person_with_one_device(api_env: ApiEnv) -> None:
    me = api_env.client.get("/v1/me", headers=api_env.headers)
    assert me.status_code == 200, me.text
    body = me.json()
    # The first phone's id is the person's id: existing trips need no rewrite.
    assert body["person_id"] == str(api_env.installation_id)
    assert body["device_id"] == str(api_env.installation_id)
    assert [d["this_device"] for d in body["devices"]] == [True]
    assert body["recovery_code_created_at"] is None
    check = api_env.client.get("/v1/installations/me", headers=api_env.headers).json()
    assert check == {
        "installation_id": str(api_env.installation_id),
        "person_id": str(api_env.installation_id),
    }


def test_a_link_code_adds_a_phone_that_then_sees_the_same_trips(api_env: ApiEnv) -> None:
    make_trip(api_env, title="Vienna")
    phone_b = api_env.other_installation()
    _trip_as(api_env, phone_b, "Own trip of B")

    value = _link_code(api_env, api_env.headers)
    assert len(value) == 9 and value[4] == "-"
    joined = _join(api_env, phone_b, value.lower().replace("-", " "))
    assert joined.status_code == 200, joined.text
    body = joined.json()
    assert body["recovered"] is False
    assert body["moved_trips"] == 1
    assert body["person"]["person_id"] == str(api_env.installation_id)
    assert len(body["person"]["devices"]) == 2

    # Both phones see both trips, and B's trip moved with it.
    assert _trip_titles(api_env, api_env.headers) == ["Own trip of B", "Vienna"]
    assert _trip_titles(api_env, phone_b) == ["Own trip of B", "Vienna"]
    check = api_env.client.get("/v1/installations/me", headers=phone_b).json()
    assert check["person_id"] == str(api_env.installation_id)
    # B's old person is gone; only a hash of the code was stored, and it is used up.
    assert sql(api_env, "SELECT count(*) FROM app.person") == [(1,)]
    stored = sql(api_env, "SELECT code_hash, used_at IS NOT NULL FROM app.link_code")
    assert len(stored) == 1 and stored[0][1] is True
    assert value.replace("-", "").encode() not in bytes(stored[0][0])

    again = _join(api_env, api_env.other_installation(), value)
    assert again.status_code == 400 and code(again) == "code_invalid"


def test_wrong_expired_and_replaced_codes_are_refused(api_env: ApiEnv) -> None:
    phone_b = api_env.other_installation()
    for bad in ("", "nonsense", "ABCD-EFG1", "ABCD-EFGH"):
        response = _join(api_env, phone_b, bad)
        assert response.status_code in (400, 422), bad
        if response.status_code == 400:
            assert code(response) == "code_invalid"

    first = _link_code(api_env, api_env.headers)
    second = _link_code(api_env, api_env.headers)
    assert code(_join(api_env, phone_b, first)) == "code_invalid"  # replaced by the second

    sql(
        api_env,
        "UPDATE app.link_code SET created_at = now() - interval '1 hour', expires_at = now() - interval '50 minutes'",
    )
    assert code(_join(api_env, phone_b, second)) == "code_invalid"  # expired


def test_the_recovery_code_signs_out_every_other_phone(api_env: ApiEnv) -> None:
    make_trip(api_env, title="Lisbon")
    phone_b = api_env.other_installation()
    assert _join(api_env, phone_b, _link_code(api_env, api_env.headers)).status_code == 200

    made = api_env.client.post("/v1/me/recovery-code", headers=phone_b)
    assert made.status_code == 201, made.text
    recovery = made.json()["code"]
    assert len(recovery.replace("-", "")) == people.RECOVERY_CODE_LENGTH
    me = api_env.client.get("/v1/me", headers=api_env.headers).json()
    assert me["recovery_code_created_at"] is not None

    # Both phones are lost; a new one recovers with the code.
    phone_c = api_env.other_installation()
    recovered = _join(api_env, phone_c, recovery)
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["recovered"] is True
    assert [d["this_device"] for d in recovered.json()["person"]["devices"]] == [True]
    assert _trip_titles(api_env, phone_c) == ["Lisbon"]

    for lost in (api_env.headers, phone_b):
        refused = api_env.client.get("/v1/trips", headers=lost)
        assert refused.status_code == 401 and code(refused) == "device_removed"
        assert api_env.client.get("/v1/installations/me", headers=lost).status_code == 401

    # The code still works (it is replaced, not used up) until a new one is made.
    api_env.client.post("/v1/me/recovery-code", headers=phone_c)
    assert code(_join(api_env, api_env.other_installation(), recovery)) == "code_invalid"


def test_a_phone_can_remove_another_but_not_itself(api_env: ApiEnv) -> None:
    phone_b = api_env.other_installation()
    assert _join(api_env, phone_b, _link_code(api_env, api_env.headers)).status_code == 200
    me = api_env.client.get("/v1/me", headers=phone_b).json()
    b_id = me["device_id"]

    itself = api_env.client.delete(f"/v1/me/devices/{b_id}", headers=phone_b)
    assert itself.status_code == 409 and code(itself) == "this_device"
    stranger = api_env.client.delete(f"/v1/me/devices/{uuid.uuid4()}", headers=api_env.headers)
    assert stranger.status_code == 404

    removed = api_env.client.delete(f"/v1/me/devices/{b_id}", headers=api_env.headers)
    assert removed.status_code == 204
    assert code(api_env.client.get("/v1/trips", headers=phone_b)) == "device_removed"
    devices = api_env.client.get("/v1/me", headers=api_env.headers).json()["devices"]
    assert [d["this_device"] for d in devices] == [True]


def test_a_phone_with_other_phones_cannot_move_to_another_person(api_env: ApiEnv) -> None:
    phone_b, phone_c = api_env.other_installation(), api_env.other_installation()
    assert _join(api_env, phone_c, _link_code(api_env, phone_b)).status_code == 200
    refused = _join(api_env, phone_b, _link_code(api_env, api_env.headers))
    assert refused.status_code == 409 and code(refused) == "has_other_devices"


def test_joining_keeps_the_trip_limit(api_env: ApiEnv, monkeypatch: pytest.MonkeyPatch) -> None:
    phone_b = api_env.other_installation()
    make_trip(api_env, title="Mine")
    _trip_as(api_env, phone_b, "B's")
    monkeypatch.setattr(people, "MAX_TRIPS_PER_INSTALLATION", 1)
    refused = _join(api_env, phone_b, _link_code(api_env, api_env.headers))
    assert refused.status_code == 409 and code(refused) == "limit_reached"
    assert _trip_titles(api_env, phone_b) == ["B's"]  # nothing moved
