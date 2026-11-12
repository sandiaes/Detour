import uuid

from fastapi.testclient import TestClient

from detour_api.main import create_app
from detour_api.settings import Settings
from detour_api.tokens import issue_token, verify_token

SECRET = b"unit-test-secret-with-more-than-32-chars"


def register(client: TestClient) -> dict[str, str]:
    response = client.post("/v1/installations")
    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    body: dict[str, str] = response.json()
    return body


def test_register_then_token_check_succeeds(client: TestClient) -> None:
    registration = register(client)
    me = client.get(
        "/v1/installations/me", headers={"Authorization": f"Bearer {registration['token']}"}
    )
    assert me.status_code == 200
    assert me.json() == {"installation_id": registration["installation_id"]}


def test_every_registration_is_a_new_installation(client: TestClient) -> None:
    assert register(client)["installation_id"] != register(client)["installation_id"]


def test_missing_token_is_401_with_challenge(client: TestClient) -> None:
    response = client.get("/v1/installations/me")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_garbage_and_tampered_tokens_are_401(client: TestClient) -> None:
    token = register(client)["token"]
    prefix, _id_hex, signature = token.split(".")
    other_id = uuid.uuid4().hex
    for bad in [
        "garbage",
        "",
        f"{prefix}.{other_id}.{signature}",
        token[:-1] + ("A" if token[-1] != "A" else "B"),
    ]:
        response = client.get("/v1/installations/me", headers={"Authorization": f"Bearer {bad}"})
        assert response.status_code == 401, bad


def test_wrong_scheme_is_401(client: TestClient) -> None:
    token = register(client)["token"]
    response = client.get("/v1/installations/me", headers={"Authorization": f"Basic {token}"})
    assert response.status_code == 401


def test_token_from_another_secret_is_rejected() -> None:
    first = Settings(environment="test", token_secret="a" * 40)
    second = Settings(environment="test", token_secret="b" * 40)
    with TestClient(create_app(first)) as c1, TestClient(create_app(second)) as c2:
        token = register(c1)["token"]
        assert (
            c2.get("/v1/installations/me", headers={"Authorization": f"Bearer {token}"}).status_code
            == 401
        )


def test_token_round_trip_and_format() -> None:
    installation_id, token = issue_token(SECRET)
    assert token.startswith("dt1.")
    assert verify_token(SECRET, token) == installation_id
    assert verify_token(b"another-secret-another-secret-123456", token) is None
    assert verify_token(SECRET, token.upper()) is None
