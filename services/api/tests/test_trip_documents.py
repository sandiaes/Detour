"""Documents shared with everyone on a trip (ADR 034, step 6): stored as they are in the private
bucket, checked by their first bytes, read and changed by every member, deleted for everyone."""

import base64
import uuid
from typing import Any

import pytest

from tests.conftest import ApiEnv
from tests.test_api_trips import code, make_trip, sql
from tests.test_trip_files import _shared_trip, _store

pytestmark = pytest.mark.db

PDF = b"%PDF-1.7\n1 0 obj << >> endobj\n%%EOF\n"


def _upload(**over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "title": "Train to Porto",
        "category": "transport",
        "link": {"kind": "day", "day": 2},
        "date": "2027-05-02",
        "notes": "Coach 5",
        "file_name": "cp-ticket.pdf",
        "content_type": "application/pdf",
        "data": base64.b64encode(PDF).decode(),
    }
    body.update(over)
    return body


def test_a_shared_document_is_seen_opened_changed_and_deleted_by_both(api_env: ApiEnv) -> None:
    c, me = api_env.client, api_env.headers
    trip, partner = _shared_trip(api_env)
    url = f"/v1/trips/{trip['id']}/documents"
    body = _upload()
    added = c.post(url, json=body, headers=partner)
    assert added.status_code == 201, added.text
    doc = added.json()
    assert doc["id"] == body["id"] and doc["bytes"] == len(PDF) and doc["added_by"] == "Ana"
    # Sent again (a retry): stored once.
    assert c.post(url, json=body, headers=partner).json()["id"] == body["id"]
    assert sql(api_env, "SELECT count(*) FROM app.trip_file") == [(1,)]

    listed = c.get(url, headers=me).json()
    assert [(d["title"], d["link"], d["date"]) for d in listed] == [
        ("Train to Porto", {"kind": "day", "day": 2}, "2027-05-02")
    ]
    got = c.get(f"{url}/{doc['id']}/file", headers=me)
    assert got.status_code == 200 and got.headers["cache-control"] == "private, no-store"
    assert base64.b64decode(got.json()["data"]) == PDF

    place = {"kind": "place", "key": "user:abc", "name": "Ribeira", "day": None}
    changed = c.patch(
        f"{url}/{doc['id']}",
        json={"title": "CP train", "category": "ticket", "link": place},
        headers=me,
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["link"] == place and changed.json()["date"] is None

    stranger = api_env.other_installation()
    assert c.get(url, headers=stranger).status_code == 404
    assert c.get(f"{url}/{doc['id']}/file", headers=stranger).status_code == 404

    assert c.delete(f"{url}/{doc['id']}", headers=me).status_code == 204
    assert c.get(url, headers=partner).json() == []
    assert _store(api_env).objects == {}


def test_files_that_are_not_what_they_say_are_refused(api_env: ApiEnv) -> None:
    c, me = api_env.client, api_env.headers
    trip = make_trip(api_env)
    url = f"/v1/trips/{trip['id']}/documents"
    fake_pdf = _upload(data=base64.b64encode(b"<html>not a pdf</html>").decode())
    assert code(c.post(url, json=fake_pdf, headers=me)) == "not_a_document"
    exe = _upload(content_type="application/x-msdownload")
    assert c.post(url, json=exe, headers=me).status_code == 422
    png = _upload(content_type="image/png", data=base64.b64encode(b"\x89PNG\r\n\x1a\nxx").decode())
    assert c.post(url, json=png, headers=me).status_code == 201
    app: Any = c.app
    app.state.settings.document_upload_max_bytes = 10
    assert code(c.post(url, json=_upload(), headers=me)) == "document_too_large"
    app.state.settings.document_upload_max_bytes = 10_000_000
    app.state.settings.trip_files_budget_bytes = 20
    assert code(c.post(url, json=_upload(), headers=me)) == "storage_full"


def test_documents_go_with_their_trip(api_env: ApiEnv) -> None:
    c, me = api_env.client, api_env.headers
    trip = make_trip(api_env)
    c.post(f"/v1/trips/{trip['id']}/documents", json=_upload(), headers=me)
    assert len(_store(api_env).objects) == 1
    assert c.delete(f"/v1/trips/{trip['id']}", headers=me).status_code == 204
    assert _store(api_env).objects == {}
    assert sql(api_env, "SELECT count(*) FROM app.trip_document") == [(0,)]


def test_a_document_id_cannot_be_reused_on_another_trip(api_env: ApiEnv) -> None:
    c, me = api_env.client, api_env.headers
    first, second = make_trip(api_env), make_trip(api_env)
    body = _upload()
    c.post(f"/v1/trips/{first['id']}/documents", json=body, headers=me)
    again = c.post(f"/v1/trips/{second['id']}/documents", json=body, headers=me)
    assert again.status_code == 409 and code(again) == "document_exists"
