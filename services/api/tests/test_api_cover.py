"""Photos that load themselves and "Change photo" (ADR 022 amendment, decisions g, h, k and l).

Wikimedia is the recorded stand-in of ``test_images.py``; storage is in memory. The test client runs
a request's background tasks before it returns, so what the background resolve wrote can be read
right after the request.
"""

import uuid
from collections.abc import Iterator
from typing import Any

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from detour_api.images import background
from detour_api.images.candidates import MAX_CANDIDATES, clean_previews, preview_id_for
from detour_api.images.store import MemoryImageStore
from detour_api.main import create_app
from detour_api.settings import Settings
from tests.conftest import TEST_SECRET, ApiEnv
from tests.test_api_trips import add_item, find_place, make_itinerary, make_trip
from tests.test_images import QIDS, _commons_page, _Wikimedia

pytestmark = pytest.mark.db

CITY_REF = "900101"


class _Env:
    def __init__(self, api_env: ApiEnv) -> None:
        self.api = api_env
        self.wiki = _Wikimedia()
        self.store = MemoryImageStore()
        self.settings = Settings(
            environment="test",
            token_secret=TEST_SECRET,
            database_url=api_env.database_url,
            wikimedia_min_interval_seconds=0.5,
        )
        self.app = create_app(
            self.settings,
            image_store=self.store,
            wikimedia_transport=httpx.MockTransport(self.wiki),
        )
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.headers = api_env.headers

    def sql(self, query: str, *params: Any) -> list[tuple[Any, ...]]:
        with psycopg.connect(self.api.database_url, autocommit=True) as conn:
            cur = conn.execute(query, params)
            return cur.fetchall() if cur.description else []


@pytest.fixture
def env(api_env: ApiEnv) -> Iterator[_Env]:
    e = _Env(api_env)
    e.sql("UPDATE geo.place_signal SET wikidata_id = NULL")
    yield e
    e.client.__exit__(None, None, None)


def test_creating_a_trip_looks_up_its_city_photo_in_the_background(env: _Env) -> None:
    r = env.client.post(
        "/v1/trips",
        headers=env.headers,
        json={
            "title": "Testburg",
            "destination_kind": "city",
            "destination_ref": CITY_REF,
            "duration_days": 2,
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["cover_image"] is None  # the response did not wait
    assert env.sql("SELECT kind, ref_id, status FROM geo.image_lookup") == [
        ("city", CITY_REF, "found")
    ]
    trip = env.client.get(f"/v1/trips/{r.json()['id']}", headers=env.headers).json()
    assert trip["cover_image"] is not None


def test_planned_places_are_looked_up_after_generation_and_on_reading_the_trips(
    env: _Env,
) -> None:
    trip = make_trip(env.api)
    itinerary = make_itinerary(env.api, trip)
    place = find_place(env.api, "testburg museum")
    added = add_item(env.api, itinerary, 1, place_id=place["id"], type="visit")
    assert added.status_code == 201, added.text
    env.sql(
        "INSERT INTO geo.place_signal (place_id, wikidata_id, osm_signals, score)"
        " VALUES (%s, %s, '{}'::jsonb, 5) ON CONFLICT (place_id) DO UPDATE SET"
        " wikidata_id = EXCLUDED.wikidata_id",
        place["id"],
        QIDS[0],
    )
    env.client.get("/v1/trips", headers=env.headers)
    looked = {(k, r) for k, r, _ in env.sql("SELECT kind, ref_id, status FROM geo.image_lookup")}
    assert ("place", place["id"]) in looked and ("city", CITY_REF) in looked
    # nothing is due any more: the next read asks Wikimedia nothing
    before = len(env.wiki.requests)
    env.client.get("/v1/trips", headers=env.headers)
    assert len(env.wiki.requests) == before


def test_a_second_resolver_does_not_start_while_one_holds_the_lock(env: _Env) -> None:
    trip = make_trip(env.api)
    engine = create_engine(env.settings.sqlalchemy_url or "")
    try:
        with engine.connect() as holder:
            holder.execute(text("SELECT pg_advisory_lock(:k)"), {"k": background.LOCK_KEY})
            report = background.resolve_trips(
                engine,
                env.settings,
                env.store,
                [uuid.UUID(trip["id"])],
                httpx.MockTransport(env.wiki),
            )
            assert report is None and env.wiki.requests == []
            holder.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": background.LOCK_KEY})
            holder.commit()
        report = background.resolve_trips(
            engine, env.settings, env.store, [uuid.UUID(trip["id"])], httpx.MockTransport(env.wiki)
        )
        assert report is not None and report.found == 1
    finally:
        engine.dispose()


def _with_category(env: _Env) -> None:
    qid = "Q900"
    env.wiki.search_hits = [qid]
    env.wiki.entities["entities"][qid] = {
        "claims": {
            "P18": [{"rank": "normal", "mainsnak": {"datavalue": {"value": "Own.jpg"}}}],
            "P373": [{"rank": "normal", "mainsnak": {"datavalue": {"value": "Town"}}}],
        },
        "sitelinks": {"enwiki": {"site": "enwiki", "title": "Town"}},
    }
    env.wiki.lead_images = {"Town": "Lead.jpg"}
    files = [f"Cat {i}.jpg" for i in range(20)]
    env.wiki.categories = {"Town": ["Own.jpg", "Bad.jpg", *files]}
    pages = env.wiki.imageinfo["query"]["pages"]
    for i, name in enumerate(["Own.jpg", "Lead.jpg", *files]):
        pages[str(1000 + i)] = _commons_page(name, width=1600, height=2400 if i % 2 else 1200)
    pages["999"] = _commons_page("Bad.jpg", width=300, height=200)


def test_cover_candidates_follow_the_chain_and_are_served_as_previews(env: _Env) -> None:
    _with_category(env)
    r = env.client.get(f"/v1/destinations/city/{CITY_REF}/cover-candidates", headers=env.headers)
    assert r.status_code == 200, r.text
    found = r.json()
    names = [c["commons_file"] for c in found]
    assert len(found) == MAX_CANDIDATES
    assert names[:3] == ["Own.jpg", "Lead.jpg", "Cat 0.jpg"]  # the chain's order, no repeats
    assert "Bad.jpg" not in names  # too small: the same gate as automatic photos
    first = found[0]
    assert first["credit"]["author"] == "A. Photographer"
    assert first["preview_url"] == f"/v1/cover-previews/{preview_id_for('Own.jpg')}"
    preview = env.client.get(first["preview_url"])
    assert preview.status_code == 200 and preview.headers["content-type"] == "image/jpeg"
    # a second request is served from the week's cache, without asking Wikimedia
    before = len(env.wiki.requests)
    again = env.client.get(
        f"/v1/destinations/city/{CITY_REF}/cover-candidates", headers=env.headers
    )
    assert again.json() == found and len(env.wiki.requests) == before


def test_choosing_a_candidate_stores_it_and_sets_the_cover(env: _Env) -> None:
    _with_category(env)
    trip = make_trip(env.api)
    env.client.get(f"/v1/destinations/city/{CITY_REF}/cover-candidates", headers=env.headers)
    r = env.client.put(
        f"/v1/trips/{trip['id']}/cover", headers=env.headers, json={"commons_file": "Cat 1.jpg"}
    )
    assert r.status_code == 200, r.text
    cover = r.json()["cover_image"]
    assert cover is not None and cover["credit"]["source_url"].endswith("File:Cat 1.jpg")
    assert env.sql("SELECT commons_file FROM geo.image WHERE id = %s", cover["id"]) == [
        ("Cat 1.jpg",)
    ]
    # a file that was not offered cannot be chosen
    refused = env.client.put(
        f"/v1/trips/{trip['id']}/cover", headers=env.headers, json={"commons_file": "Other.jpg"}
    )
    assert refused.status_code == 422 and refused.json()["code"] == "cover_not_usable"
    # null goes back to the automatic photo
    back = env.client.put(
        f"/v1/trips/{trip['id']}/cover", headers=env.headers, json={"commons_file": None}
    )
    assert back.status_code == 200
    assert env.sql("SELECT cover_image_id FROM app.trip WHERE id = %s", trip["id"]) == [(None,)]


def test_previews_older_than_a_week_are_deleted(env: _Env) -> None:
    _with_category(env)
    env.client.get(f"/v1/destinations/city/{CITY_REF}/cover-candidates", headers=env.headers)
    assert env.sql("SELECT count(*) FROM geo.cover_preview") == [(MAX_CANDIDATES,)]
    env.sql("UPDATE geo.cover_preview SET created_date = current_date - 8")
    engine = create_engine(env.settings.sqlalchemy_url or "")
    try:
        assert clean_previews(engine, env.store) == MAX_CANDIDATES
    finally:
        engine.dispose()
    assert env.sql("SELECT count(*) FROM geo.cover_preview") == [(0,)]
    assert not [k for k in env.store.objects if k.startswith("previews/")]
