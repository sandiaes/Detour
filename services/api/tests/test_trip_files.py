"""Album links and the cover from a phone on the server (ADR 034, step 5): shared by everyone on
the trip, the cover re-encoded without metadata and kept in the private bucket."""

import base64
import io
from typing import Any

import pytest
from PIL import Image

from detour_api.images.store import MemoryImageStore
from detour_api.repo import trip_files
from tests.conftest import ApiEnv
from tests.test_api_trips import code, make_trip, sql
from tests.test_sharing import _link, _me

pytestmark = pytest.mark.db

GOOGLE = "https://photos.app.goo.gl/AbCdEf123"


def _picture(width: int = 3000, height: int = 2000, fmt: str = "PNG") -> str:
    image = Image.new("RGB", (width, height), (200, 120, 40))
    out = io.BytesIO()
    image.save(out, format=fmt)
    return base64.b64encode(out.getvalue()).decode()


def _store(env: ApiEnv) -> MemoryImageStore:
    app: Any = env.client.app
    store: MemoryImageStore = app.state.file_store
    return store


def _shared_trip(env: ApiEnv) -> tuple[dict[str, Any], dict[str, str]]:
    partner = env.other_installation()
    env.client.patch("/v1/me", json={"display_name": "Ana"}, headers=partner)
    _link(env, env.headers, partner)
    trip = make_trip(env)
    env.client.post(
        f"/v1/trips/{trip['id']}/members",
        json={"person_id": _me(env, partner)["person_id"]},
        headers=env.headers,
    )
    return trip, partner


def test_album_links_are_shared_by_the_trip(api_env: ApiEnv) -> None:
    c, me = api_env.client, api_env.headers
    trip, partner = _shared_trip(api_env)
    url = f"/v1/trips/{trip['id']}/albums"
    added = c.post(url, json={"url": f"Look at our photos! {GOOGLE}", "name": ""}, headers=partner)
    assert added.status_code == 201, added.text
    assert added.json()["url"] == GOOGLE and added.json()["name"] == "Trip album"
    seen = c.get(url, headers=me).json()
    assert [(a["url"], a["added_by"]) for a in seen] == [(GOOGLE, "Ana")]
    assert code(c.post(url, json={"url": GOOGLE}, headers=me)) == "album_exists"
    assert c.post(url, json={"url": "http://insecure.example"}, headers=me).status_code == 422
    album = seen[0]["id"]
    renamed = c.patch(f"{url}/{album}", json={"name": "Lisbon by Ana"}, headers=me)
    assert renamed.json()["name"] == "Lisbon by Ana"
    assert c.delete(f"{url}/{album}", headers=partner).status_code == 204
    assert c.get(url, headers=me).json() == []
    stranger = api_env.other_installation()
    assert c.get(url, headers=stranger).status_code == 404


def test_a_cover_from_a_phone_is_stored_once_for_everyone(api_env: ApiEnv) -> None:
    c, me = api_env.client, api_env.headers
    trip, partner = _shared_trip(api_env)
    url = f"/v1/trips/{trip['id']}/own-cover"
    put = c.put(url, json={"content_type": "image/png", "data": _picture()}, headers=partner)
    assert put.status_code == 200, put.text
    cover = put.json()
    listed = c.get(f"/v1/trips/{trip['id']}", headers=me).json()["own_cover"]
    assert listed["id"] == cover["id"]

    got = c.get(url, headers=me)
    assert got.status_code == 200 and got.headers["cache-control"] == "private, no-store"
    with Image.open(io.BytesIO(base64.b64decode(got.json()["data"]))) as image:
        assert image.format == "JPEG" and max(image.size) == 1600
        assert not image.getexif()  # no location or camera data is kept
    assert c.get(url, headers=api_env.other_installation()).status_code == 404

    # Replacing it removes the old object from the bucket after the response.
    first_key = next(iter(_store(api_env).objects))
    c.put(url, json={"content_type": "image/jpeg", "data": _picture(800, 600, "JPEG")}, headers=me)
    assert first_key not in _store(api_env).objects and len(_store(api_env).objects) == 1

    assert c.delete(url, headers=me).status_code == 204
    assert c.get(f"/v1/trips/{trip['id']}", headers=partner).json()["own_cover"] is None
    assert _store(api_env).objects == {}


def test_bad_pictures_and_a_full_budget_are_refused(api_env: ApiEnv) -> None:
    c, me = api_env.client, api_env.headers
    trip = make_trip(api_env)
    url = f"/v1/trips/{trip['id']}/own-cover"
    nonsense = base64.b64encode(b"not a picture").decode()
    bad = c.put(url, json={"content_type": "image/jpeg", "data": nonsense}, headers=me)
    assert bad.status_code == 422 and code(bad) == "not_a_picture"
    app: Any = c.app
    app.state.settings.trip_files_budget_bytes = 10
    full = c.put(url, json={"content_type": "image/png", "data": _picture(50, 50)}, headers=me)
    assert full.status_code == 409 and code(full) == "storage_full"
    assert sql(api_env, "SELECT count(*) FROM app.trip_file") == [(0,)]


def test_deleting_a_trip_removes_its_stored_cover(api_env: ApiEnv) -> None:
    c, me = api_env.client, api_env.headers
    trip = make_trip(api_env)
    c.put(
        f"/v1/trips/{trip['id']}/own-cover",
        json={"content_type": "image/png", "data": _picture(100, 100)},
        headers=me,
    )
    assert len(_store(api_env).objects) == 1
    assert c.delete(f"/v1/trips/{trip['id']}", headers=me).status_code == 204
    assert _store(api_env).objects == {}
    assert sql(api_env, "SELECT count(*) FROM app.trip_file_orphan") == [(0,)]


def test_reencoding_keeps_a_small_picture_small_and_upright() -> None:
    out = trip_files.reencode_cover(base64.b64decode(_picture(300, 200)), 1600)
    with Image.open(io.BytesIO(out)) as image:
        assert image.size == (300, 200)
