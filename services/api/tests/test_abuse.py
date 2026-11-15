"""Request limits on the public API (Phase 9, docs/security.md). No database needed."""

from fastapi.testclient import TestClient

from detour_api.abuse import ANONYMOUS, RequestLimiter
from detour_api.main import create_app
from detour_api.settings import Settings
from detour_api.tokens import issue_token

SECRET = "test-secret-for-the-request-limits-000000"


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def _settings(**kw: object) -> Settings:
    return Settings(environment="test", token_secret=SECRET, **kw)  # type: ignore[arg-type]


def test_each_installation_has_its_own_bucket() -> None:
    clock = Clock()
    limiter = RequestLimiter(_settings(rate_limit_per_minute=60, rate_limit_burst=3), now=clock)
    _, a = issue_token(SECRET.encode())
    _, b = issue_token(SECRET.encode())
    for _ in range(3):
        assert limiter.check("GET", "/v1/trips", f"Bearer {a}") == 0.0
    wait = limiter.check("GET", "/v1/trips", f"Bearer {a}")
    assert 0 < wait <= 1.0  # one token a second
    assert limiter.check("GET", "/v1/trips", f"Bearer {b}") == 0.0  # another phone is not held up
    clock.t += 1.0
    assert limiter.check("GET", "/v1/trips", f"Bearer {a}") == 0.0


def test_a_forged_token_shares_the_anonymous_bucket() -> None:
    limiter = RequestLimiter(_settings())
    _, forged = issue_token(b"another-secret-entirely-0000000000000")
    assert limiter.caller_key(f"Bearer {forged}") == ANONYMOUS
    assert limiter.caller_key("Bearer nonsense") == ANONYMOUS
    assert limiter.caller_key(None) == ANONYMOUS
    installation, genuine = issue_token(SECRET.encode())
    assert limiter.caller_key(f"bearer {genuine}") == installation.hex


def test_health_and_config_are_never_limited() -> None:
    limiter = RequestLimiter(_settings(rate_limit_burst=1, registrations_burst=1))
    for _ in range(20):
        assert limiter.check("GET", "/v1/health", None) == 0.0
        assert limiter.check("GET", "/v1/health/ready", None) == 0.0
        assert limiter.check("GET", "/v1/config", None) == 0.0


def test_registrations_are_limited_for_the_whole_service() -> None:
    with TestClient(create_app(_settings(registrations_burst=2))) as client:
        assert client.post("/v1/installations").status_code == 201
        assert client.post("/v1/installations").status_code == 201
        refused = client.post("/v1/installations")
    assert refused.status_code == 429
    assert refused.json()["code"] == "rate_limited"
    assert int(refused.headers["Retry-After"]) >= 1


def test_an_installation_over_its_limit_gets_429_and_others_do_not() -> None:
    with TestClient(create_app(_settings(rate_limit_burst=2, rate_limit_per_minute=1))) as client:
        token = client.post("/v1/installations").json()["token"]
        other = client.post("/v1/installations").json()["token"]
        auth = {"Authorization": f"Bearer {token}"}
        assert client.get("/v1/installations/me", headers=auth).status_code == 200
        assert client.get("/v1/installations/me", headers=auth).status_code == 200
        refused = client.get("/v1/installations/me", headers=auth)
        assert refused.status_code == 429
        assert int(refused.headers["Retry-After"]) >= 1
        ok = client.get("/v1/installations/me", headers={"Authorization": f"Bearer {other}"})
        assert ok.status_code == 200


def test_photos_have_their_own_bucket() -> None:
    limiter = RequestLimiter(_settings(rate_limit_burst=1, image_requests_burst=5))
    assert limiter.check("GET", "/v1/trips", None) == 0.0
    assert limiter.check("GET", "/v1/trips", None) > 0  # the anonymous bucket is empty
    assert all(limiter.check("GET", f"/v1/images/{n}", None) == 0.0 for n in range(5))
    assert limiter.check("GET", "/v1/images/x", None) > 0


def test_limits_can_be_switched_off() -> None:
    with TestClient(create_app(_settings(rate_limit_enabled=False, registrations_burst=1))) as c:
        assert all(c.post("/v1/installations").status_code == 201 for _ in range(5))
