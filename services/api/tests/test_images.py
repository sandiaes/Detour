"""The photo resolver, the image tables and ``GET /v1/images/{id}`` (ADR 022).

The Wikimedia answers are the recorded fixtures of ``test_wikimedia.py``; downloads return a
synthetic JPEG. Nothing here reaches the network.
"""

import copy
import io
import json
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, text

from detour_api.adapters.wikimedia import WikimediaClient
from detour_api.images import resolver
from detour_api.images.store import MemoryImageStore, StoreError, SupabaseImageStore
from detour_api.main import create_app
from detour_api.settings import Settings
from tests.conftest import TEST_SECRET, ApiEnv
from tests.import_helpers import TEST_REGION

FIXTURES = Path(__file__).parent / "fixtures"
ENTITIES = json.loads((FIXTURES / "wikidata-wbgetentities-3.json").read_text())
IMAGEINFO = json.loads((FIXTURES / "commons-imageinfo-3.json").read_text())
QIDS = sorted(ENTITIES["entities"])


def _jpeg() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (2000, 1300), (30, 120, 90)).save(out, format="JPEG")
    return out.getvalue()


class _Wikimedia:
    """A stand-in for Wikidata, Commons and the image host, recording what was asked."""

    def __init__(self) -> None:
        self.imageinfo = copy.deepcopy(IMAGEINFO)
        self.entities = copy.deepcopy(ENTITIES)
        self.search_hits: list[str] = ["Q101514119"]
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        host = request.url.host
        if host == "thumb.wikimedia.org":
            return httpx.Response(200, content=_jpeg(), headers={"content-type": "image/jpeg"})
        if request.url.params.get("action") == "wbgetentities":
            wanted = request.url.params["ids"].split("|")
            entities = {q: e for q, e in self.entities["entities"].items() if q in wanted}
            return httpx.Response(200, json={"entities": entities})
        if request.url.params.get("list") == "search":
            return httpx.Response(
                200, json={"query": {"search": [{"title": t} for t in self.search_hits]}}
            )
        return httpx.Response(200, json=self.imageinfo)


class _Fixture:
    def __init__(self, env: ApiEnv, wiki: _Wikimedia, store: MemoryImageStore) -> None:
        self.env = env
        self.wiki = wiki
        self.store = store
        self.settings = Settings(
            environment="test",
            token_secret=TEST_SECRET,
            database_url=env.database_url,
            wikimedia_min_interval_seconds=0.5,
        )
        self.engine = create_engine(self.settings.sqlalchemy_url or "")

    def client(self, **settings: Any) -> WikimediaClient:
        merged = self.settings.model_copy(update=settings)
        return WikimediaClient(
            merged, self.engine, httpx.MockTransport(self.wiki), sleep=lambda s: None
        )

    def resolve(self, candidates: list[resolver.Candidate], **settings: Any) -> resolver.Report:
        merged = self.settings.model_copy(update=settings)
        return resolver.resolve(
            self.engine, self.client(**settings), self.store, merged, candidates
        )

    def query(self, sql: str, **params: Any) -> list[Any]:
        with self.engine.begin() as conn:
            return list(conn.execute(text(sql), params).all())

    def app(self, store: MemoryImageStore | None) -> TestClient:
        return TestClient(create_app(self.settings, image_store=store))


@pytest.fixture
def fx(api_env: ApiEnv) -> Iterator[_Fixture]:
    fixture = _Fixture(api_env, _Wikimedia(), MemoryImageStore())
    with psycopg.connect(api_env.database_url, autocommit=True) as conn:
        # the fixture region's own Wikidata tags are not the recorded ones: start from none
        conn.execute("UPDATE geo.place_signal SET wikidata_id = NULL")
        places = conn.execute(
            "SELECT id FROM geo.place WHERE kind = 'attraction' AND region_id = %s"
            " ORDER BY id LIMIT 3",
            (TEST_REGION.id,),
        ).fetchall()
        assert len(places) == 3, "the fixture region needs three attractions"
        for (place_id,), qid in zip(places, QIDS, strict=True):
            conn.execute(
                "INSERT INTO geo.place_signal (place_id, wikidata_id, osm_signals, score)"
                " VALUES (%s, %s, '{}'::jsonb, 5) ON CONFLICT (place_id) DO UPDATE SET"
                " wikidata_id = EXCLUDED.wikidata_id, score = EXCLUDED.score",
                (place_id, qid),
            )
    yield fixture
    fixture.engine.dispose()


@pytest.mark.db
def test_places_with_a_photo_are_resolved_stored_and_recorded(fx: _Fixture) -> None:
    candidates = resolver.place_candidates(fx.engine, TEST_REGION.id, 10)
    assert len(candidates) == 3
    report = fx.resolve(candidates)

    assert (report.found, report.none, report.rejected, report.stopped) == (3, 0, 0, None)
    assert report.downloaded == 3 and report.stored_bytes > 0
    rows = fx.query(
        "SELECT commons_file, author, licence, width, height, bytes, color, storage_key, hidden"
        " FROM geo.image ORDER BY commons_file"
    )
    assert len(rows) == 3
    retz = next(r for r in rows if r[0] == "Retz - Stadtmauer.JPG")
    assert retz[1:4] == ("C.Stadler/Bwag", "CC BY-SA 4.0", 1080)
    assert retz[4] == 702 and retz[5] == len(fx.store.objects[retz[7]]) and retz[8] is False
    assert retz[6].startswith("#") and len(retz[6]) == 7
    assert retz[7] == f"{resolver.image_id_for('Retz - Stadtmauer.JPG')}.jpg"
    found = fx.query("SELECT count(*) FROM geo.image_lookup WHERE status = 'found'")
    assert found[0][0] == 3
    # three places, three batches of one request each: entities, file info, and three downloads
    assert [r.url.host for r in fx.wiki.requests].count("thumb.wikimedia.org") == 3

    # asked again: nothing is left to ask, so nothing is requested
    before = len(fx.wiki.requests)
    assert resolver.place_candidates(fx.engine, TEST_REGION.id, 10) == []
    assert len(fx.wiki.requests) == before


@pytest.mark.db
def test_the_same_file_is_stored_once_for_two_places(fx: _Fixture) -> None:
    fx.wiki.entities["entities"][QIDS[1]] = copy.deepcopy(fx.wiki.entities["entities"][QIDS[0]])
    fx.wiki.entities["entities"][QIDS[1]]["id"] = QIDS[1]
    report = fx.resolve(resolver.place_candidates(fx.engine, TEST_REGION.id, 10))
    assert report.found == 3 and report.downloaded == 2
    assert fx.query("SELECT count(*) FROM geo.image")[0][0] == 2


@pytest.mark.db
def test_a_licence_or_quality_failure_is_recorded_and_not_downloaded(fx: _Fixture) -> None:
    pages = fx.wiki.imageinfo["query"]["pages"].values()
    retz = next(p for p in pages if "Retz" in p["title"])
    retz["imageinfo"][0]["extmetadata"]["LicenseShortName"]["value"] = "CC BY-NC 4.0"
    small = next(p for p in pages if "Zwettl" in p["title"])
    small["imageinfo"][0]["width"], small["imageinfo"][0]["height"] = 800, 600
    report = fx.resolve(resolver.place_candidates(fx.engine, TEST_REGION.id, 10))
    assert (report.found, report.rejected) == (1, 2)
    assert report.reasons == {"licence_not_allowed": 1, "too_small": 1}
    assert [r.url.host for r in fx.wiki.requests].count("thumb.wikimedia.org") == 1
    rows = fx.query(
        "SELECT status, reason FROM geo.image_lookup WHERE status <> 'found' ORDER BY reason"
    )
    assert rows == [("rejected", "licence_not_allowed"), ("rejected", "too_small")]
    # a refusal is remembered: the next run does not ask again
    assert resolver.place_candidates(fx.engine, TEST_REGION.id, 10) == []


@pytest.mark.db
def test_no_item_or_no_image_is_recorded_as_none_and_retried_only_after_90_days(
    fx: _Fixture,
) -> None:
    del fx.wiki.entities["entities"][QIDS[0]]["claims"]["P18"]
    fx.wiki.entities["entities"][QIDS[1]] = {"id": QIDS[1], "missing": ""}
    report = fx.resolve(resolver.place_candidates(fx.engine, TEST_REGION.id, 10))
    assert (report.found, report.none) == (1, 2)
    assert report.reasons == {"no_image_property": 1, "no_wikidata_item": 1}
    assert resolver.place_candidates(fx.engine, TEST_REGION.id, 10) == []
    fx.query("SELECT 1")
    with fx.engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE geo.image_lookup SET checked_date = current_date - 91 WHERE status = 'none'"
            )
        )
    again = resolver.place_candidates(fx.engine, TEST_REGION.id, 10)
    assert len(again) == 2  # the two with no photo, not the one that has one


@pytest.mark.db
def test_the_image_cap_stops_the_run_and_records_nothing_more(fx: _Fixture) -> None:
    report = fx.resolve(
        resolver.place_candidates(fx.engine, TEST_REGION.id, 10), image_max_stored=1
    )
    assert report.found == 1 and report.stopped == "image cap reached"
    assert fx.query("SELECT count(*) FROM geo.image_lookup")[0][0] == 1
    assert len(resolver.place_candidates(fx.engine, TEST_REGION.id, 10)) == 2


@pytest.mark.db
def test_an_outage_ends_the_run_and_the_next_run_reuses_what_was_stored(fx: _Fixture) -> None:
    ok = fx.wiki
    downloads: list[int] = []

    def flaky(request: httpx.Request) -> httpx.Response:
        if request.url.host == "thumb.wikimedia.org":
            downloads.append(1)
            if len(downloads) == 2:  # the first photo arrives, the second download fails
                raise httpx.ConnectTimeout("down", request=request)
        return ok(request)

    client = WikimediaClient(
        fx.settings, fx.engine, httpx.MockTransport(flaky), sleep=lambda s: None
    )
    candidates = resolver.place_candidates(fx.engine, TEST_REGION.id, 10)
    report = resolver.resolve(fx.engine, client, fx.store, fx.settings, candidates)
    assert report.stopped and report.stopped.startswith("wikimedia:")
    assert report.found == 0  # a batch's answers are written together, after its downloads
    assert fx.query("SELECT count(*) FROM geo.image_lookup")[0][0] == 0
    assert fx.query("SELECT count(*) FROM geo.image")[0][0] == 1  # the one that did arrive
    assert len(fx.store.objects) == 1

    # the next run asks again, reuses the stored file and downloads only the other two
    again = fx.resolve(resolver.place_candidates(fx.engine, TEST_REGION.id, 10))
    assert (again.found, again.downloaded, again.stopped) == (3, 2, None)


@pytest.mark.db
def test_cities_are_matched_through_their_geonames_id(fx: _Fixture) -> None:
    candidates = resolver.city_candidates(fx.engine, ["AT"], 1)
    assert len(candidates) == 1 and candidates[0].qid is None
    report = fx.resolve(candidates)
    assert report.found == 1
    search = [r for r in fx.wiki.requests if r.url.params.get("list") == "search"]
    assert search[0].url.params["srsearch"] == f"haswbstatement:P1566={candidates[0].ref_id}"
    assert fx.query("SELECT kind FROM geo.image_lookup") == [("city",)]


@pytest.mark.db
def test_a_city_with_two_matching_items_is_not_guessed(fx: _Fixture) -> None:
    fx.wiki.search_hits = ["Q1", "Q2"]
    report = fx.resolve(resolver.city_candidates(fx.engine, ["AT"], 1))
    assert (report.found, report.none, report.reasons) == (0, 1, {"no_wikidata_item": 1})


@pytest.mark.db
def test_the_image_endpoint_serves_the_stored_file_and_hides_hidden_ones(fx: _Fixture) -> None:
    fx.resolve(resolver.place_candidates(fx.engine, TEST_REGION.id, 10))
    image_id = resolver.image_id_for("Retz - Stadtmauer.JPG")
    with fx.app(fx.store) as client:
        response = client.get(f"/v1/images/{image_id}")  # public: no token needed
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"
        assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
        with Image.open(io.BytesIO(response.content)) as shown:
            assert shown.format == "JPEG" and max(shown.size) == 1080
        assert client.get(f"/v1/images/{uuid.uuid4()}").status_code == 404
        assert client.get("/v1/images/not-a-uuid").status_code == 422
        with fx.engine.begin() as conn:
            conn.execute(
                text("UPDATE geo.image SET hidden = true WHERE id = :id"), {"id": image_id}
            )
        assert client.get(f"/v1/images/{image_id}").status_code == 404
    with fx.app(None) as client:  # storage not configured
        visible = resolver.image_id_for("Stadtmauer bei der Uferpromenade in Zwettl.jpg")
        assert client.get(f"/v1/images/{visible}").status_code == 503
    gone = MemoryImageStore()
    with fx.app(gone) as client:  # row present, file missing from storage
        visible = resolver.image_id_for("Stadtmauer bei der Uferpromenade in Zwettl.jpg")
        assert client.get(f"/v1/images/{visible}").status_code == 404

    class Broken(MemoryImageStore):
        def get(self, key: str) -> bytes | None:
            raise StoreError("down")

    with fx.app(Broken()) as client:
        visible = resolver.image_id_for("Stadtmauer bei der Uferpromenade in Zwettl.jpg")
        assert client.get(f"/v1/images/{visible}").status_code == 503


@pytest.mark.db
def test_the_schema_keeps_its_rules(fx: _Fixture) -> None:
    fx.resolve(resolver.place_candidates(fx.engine, TEST_REGION.id, 10))
    with psycopg.connect(fx.env.database_url, autocommit=True) as conn:
        with pytest.raises(psycopg.errors.CheckViolation):  # found needs an image, none must not
            conn.execute(
                "INSERT INTO geo.image_lookup (kind, ref_id, status, checked_date)"
                " VALUES ('place', 'x', 'found', current_date)"
            )
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute("UPDATE geo.image SET color = 'red'")
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute("UPDATE geo.image SET licence_url = 'ftp://x'")
        # the cover column exists and has no foreign key across the schemas
        assert conn.execute(
            "SELECT count(*) FROM information_schema.columns"
            " WHERE table_schema = 'app' AND table_name = 'trip' AND column_name = 'cover_image_id'"
        ).fetchone() == (1,)


@pytest.mark.db
def test_a_dry_run_can_be_taken_back_leaving_nothing_behind(fx: _Fixture) -> None:
    places = fx.resolve(resolver.place_candidates(fx.engine, TEST_REGION.id, 10))
    cities = fx.resolve(resolver.city_candidates(fx.engine, ["AT"], 1))
    # the same file served a place and a city: it was stored once, and a run can still undo it
    assert fx.query("SELECT count(*) FROM geo.image")[0][0] == 3
    resolver.discard_runs(fx.engine, [places, cities])
    assert fx.query("SELECT count(*) FROM geo.image")[0][0] == 0
    assert fx.query("SELECT count(*) FROM geo.image_lookup")[0][0] == 0
    assert len(resolver.place_candidates(fx.engine, TEST_REGION.id, 10)) == 3  # asked again later


@pytest.mark.db
def test_discarding_a_run_keeps_what_an_earlier_real_run_stored(fx: _Fixture) -> None:
    fx.resolve(resolver.place_candidates(fx.engine, TEST_REGION.id, 1))  # a real run: one place
    dry = fx.resolve(resolver.place_candidates(fx.engine, TEST_REGION.id, 10))
    resolver.discard_runs(fx.engine, [dry])
    assert fx.query("SELECT count(*) FROM geo.image")[0][0] == 1
    assert fx.query("SELECT count(*) FROM geo.image_lookup")[0][0] == 1


@pytest.mark.db
def test_images_missing_from_storage_are_fetched_again(fx: _Fixture) -> None:
    fx.resolve(resolver.place_candidates(fx.engine, TEST_REGION.id, 10))
    lost_key = f"{resolver.image_id_for('Retz - Stadtmauer.JPG')}.jpg"
    del fx.store.objects[lost_key]
    counts = resolver.repair_missing(fx.engine, fx.client(), fx.store, fx.settings)
    assert counts == {"checked": 3, "missing": 1, "repaired": 1, "unrepairable": 0}
    assert lost_key in fx.store.objects
    # nothing missing: nothing downloaded
    before = len(fx.wiki.requests)
    again = resolver.repair_missing(fx.engine, fx.client(), fx.store, fx.settings)
    assert again["missing"] == 0 and len(fx.wiki.requests) == before


@pytest.mark.db
def test_a_file_commons_no_longer_offers_is_counted_not_dropped(fx: _Fixture) -> None:
    fx.resolve(resolver.place_candidates(fx.engine, TEST_REGION.id, 10))
    fx.store.objects.clear()
    retz = next(p for p in fx.wiki.imageinfo["query"]["pages"].values() if "Retz" in p["title"])
    retz["imageinfo"][0]["extmetadata"]["LicenseShortName"]["value"] = "CC BY-NC 4.0"
    counts = resolver.repair_missing(fx.engine, fx.client(), fx.store, fx.settings)
    assert counts == {"checked": 3, "missing": 3, "repaired": 2, "unrepairable": 1}
    assert fx.query("SELECT count(*) FROM geo.image")[0][0] == 3  # the row stays for the owner


def test_the_supabase_store_uses_head_to_check_and_reports_refusals() -> None:
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        if request.url.path.endswith("/there.jpg"):
            return httpx.Response(200)
        if request.url.path.endswith("/denied.jpg"):
            return httpx.Response(403)
        return httpx.Response(404, json={"error": "not_found"})

    settings = Settings(
        environment="test",
        token_secret=TEST_SECRET,
        supabase_url="https://example.supabase.co/",
        supabase_service_key="service-key",
    )
    store = SupabaseImageStore(settings, httpx.MockTransport(handler))
    assert store.exists("there.jpg") is True
    assert store.exists("gone.jpg") is False
    with pytest.raises(StoreError):
        store.exists("denied.jpg")
    assert seen[0] == ("HEAD", "/storage/v1/object/public/photos/there.jpg")
