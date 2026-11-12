import json

import pytest
from fastapi.testclient import TestClient

from detour_api.logging import REDACTED, configure_logging, get_logger, redact, scrub_text
from detour_api.main import create_app
from detour_api.settings import Settings


def test_sensitive_keys_are_redacted_at_any_depth() -> None:
    cleaned = redact(
        {
            "event": "x",
            "Authorization": "Bearer abc",
            "nested": {"password": "p", "token_secret": "s", "ok": 1},
            "list": [{"api_key": "k"}],
            "database_url": "postgresql://u:p@h/db",
            "installation_id": "keep-me",
        }
    )
    assert cleaned["Authorization"] == REDACTED
    assert cleaned["nested"] == {"password": REDACTED, "token_secret": REDACTED, "ok": 1}
    assert cleaned["list"] == [{"api_key": REDACTED}]
    assert cleaned["database_url"] == REDACTED
    assert cleaned["installation_id"] == "keep-me"


def test_secrets_inside_text_are_scrubbed() -> None:
    assert "abc.def" not in scrub_text("header was Bearer abc.def and more")
    assert "hunter2" not in scrub_text(
        "could not connect to postgresql://user:hunter2@db.example.org/x"
    )
    token = "dt1." + "a" * 32 + "." + "B" * 43
    assert token not in scrub_text(f"token={token}")
    assert scrub_text("plain text stays") == "plain text stays"


def test_log_lines_are_json_and_redacted(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO")
    get_logger("test").info(
        "connect", url="postgresql://u:secretpw@h/db", password="pw", note="fine"
    )
    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line["event"] == "connect"
    assert line["level"] == "info"
    assert line["note"] == "fine"
    assert line["password"] == REDACTED
    assert "secretpw" not in json.dumps(line)


def test_exception_text_is_scrubbed(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO")
    try:
        raise RuntimeError("failed for postgresql://user:topsecret@host/db")
    except RuntimeError:
        get_logger("test").exception("boom")
    assert "topsecret" not in capsys.readouterr().out


def test_request_logs_carry_no_token_or_query_string(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    with TestClient(create_app(settings)) as client:
        token = client.post("/v1/installations").json()["token"]
        client.get(
            "/v1/installations/me?secret=hunter2", headers={"Authorization": f"Bearer {token}"}
        )
    out = capsys.readouterr().out
    assert token not in out
    assert "hunter2" not in out
    requests = [json.loads(x) for x in out.splitlines() if '"event": "request"' in x]
    assert [(r["method"], r["path"], r["status"]) for r in requests] == [
        ("POST", "/v1/installations", 201),
        ("GET", "/v1/installations/me", 200),
    ]
    assert all(r["request_id"] and r["duration_ms"] >= 0 for r in requests)
