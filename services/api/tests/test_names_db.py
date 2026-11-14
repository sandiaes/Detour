"""Multilingual place names in the database and the API (ADR 025): the migration's search
aliases, Wikidata enrichment with negative caching, cached fallback when Wikidata is down, search
by any name, user overrides, item names, retention and the backfill command.

Wikidata is a mock transport answering in the documented ``wbgetentities`` and search shapes."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from detour_api.adapters.wikimedia import WikimediaClient
from detour_api.importer.cli import main as importer_main
from detour_api.main import create_app
from detour_api.names import enrich
from detour_api.names.store import prune
from detour_api.settings import Settings
from tests.conftest import TEST_SECRET, ApiEnv
from tests.import_helpers import TEST_REGION

pytestmark = pytest.mark.db

CITY = {"destination_kind": "city", "destination_ref": "900101"}  # Testburg, AT

ITEMS: dict[str, dict[str, Any]] = {
    "Q233413": {
        "labels": {"en": "Himeji Castle", "ja": "姫路城"},
        "aliases": {"en": ["White Heron Castle"]},
        "enwiki": "Himeji Castle",
    },
    "Q7001": {"labels": {"ja": "名もなき祠"}, "aliases": {}, "enwiki": None},  # no English
    "Q1001": {"labels": {"en": "Testburg Museum of Art"}, "aliases": {}, "enwiki": None},
    "Q1002": {
        "labels": {"en": "Testburg Fortress"},
        "aliases": {},
        "enwiki": "Testburg Castle (Austria)",
    },
    "Q1003": {"labels": {"en": "Mühlbach Lookout"}, "aliases": {}, "enwiki": None},
    "Q9001": {
        "labels": {"en": "Testburg", "de": "Testenburg"},
        "aliases": {},
        "enwiki": "Testburg",
    },
}


class Wikidata:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.down = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.down:
            return httpx.Response(503, headers={"Retry-After": "1"})
        params = request.url.params
        if params.get("list") == "search":  # the city's item by its GeoNames id
            hits = [{"title": "Q9001"}] if "P1566=900101" in params["srsearch"] else []
            return httpx.Response(200, json={"query": {"search": hits}})
        if params.get("action") == "wbgetentities" and "sites" in params:  # by a wikipedia tag
            known = {"Mühlbach": "Q1003"}
            found = {
                known[t]: {"id": known[t], "sitelinks": {params["sites"]: {"title": t}}}
                for t in params["titles"].split("|")
                if t in known
            }
            return httpx.Response(200, json={"entities": found})
        if params.get("action") == "wbgetentities":
            langs = set(params["languages"].split("|"))
            entities: dict[str, Any] = {}
            for qid in params["ids"].split("|"):
                item = ITEMS.get(qid)
                if item is None:
                    entities[qid] = {"id": qid, "missing": ""}
                    continue
                entities[qid] = {
                    "id": qid,
                    "labels": {
                        k: {"language": k, "value": v}
                        for k, v in item["labels"].items()
                        if k in langs
                    },
                    "aliases": {
                        k: [{"language": k, "value": v} for v in vs]
                        for k, vs in item["aliases"].items()
                        if k in langs
                    },
                    "sitelinks": {"enwiki": {"site": "enwiki", "title": item["enwiki"]}}
                    if item["enwiki"]
                    else {},
                }
            return httpx.Response(200, json={"entities": entities})
        return httpx.Response(400, json={"error": {"code": "unexpected"}})


class Fx:
    def __init__(self, env: ApiEnv) -> None:
        self.env = env
        self.wiki = Wikidata()
        self.settings = Settings(
            environment="test",
            token_secret=TEST_SECRET,
            database_url=env.database_url,
            wikimedia_min_interval_seconds=0.5,
        )
        self.engine = create_engine(self.settings.sqlalchemy_url or "")

    def client(self) -> WikimediaClient:
        return WikimediaClient(
            self.settings, self.engine, httpx.MockTransport(self.wiki), sleep=lambda s: None
        )

    def run(self, entities: list[enrich.Entity], **kw: Any) -> enrich.Report:
        return enrich.enrich(self.engine, self.client(), entities, **kw)

    def sql(self, query: str, **params: Any) -> list[Any]:
        with self.engine.begin() as conn:
            result = conn.execute(text(query), params)
            return list(result.all()) if result.returns_rows else []

    def add_place(
        self,
        name: str,
        i18n: dict[str, str] | None,
        qid: str | None,
        lat: float = 48.2085,
        lon: float = 16.3721,
    ) -> uuid.UUID:
        place_id = uuid.uuid4()
        with psycopg.connect(self.env.database_url, autocommit=True) as conn:
            conn.execute(
                "INSERT INTO geo.place (id, region_id, kind, category, name, name_norm, names_i18n,"
                " geom, city_id, first_import_run_id, last_changed_import_run_id)"
                " SELECT %s, r.id, 'attraction', 'castle', %s, lower(%s), %s::jsonb,"
                " ST_SetSRID(ST_MakePoint(%s, %s), 4326), 900101,"
                " r.current_import_run_id, r.current_import_run_id FROM geo.region r WHERE r.id = %s",
                (
                    place_id,
                    name,
                    name,
                    psycopg.types.json.Json(i18n) if i18n else None,
                    lon,
                    lat,
                    TEST_REGION.id,
                ),
            )
            conn.execute(
                "INSERT INTO geo.place_signal (place_id, wikidata_id, osm_signals, score)"
                " VALUES (%s, %s, '{}'::jsonb, 9)",
                (place_id, qid),
            )
        return place_id

    def place_entities(self, *ids: uuid.UUID) -> list[enrich.Entity]:
        return [
            e
            for e in enrich.region_entities(self.engine, TEST_REGION.id, 500)
            if uuid.UUID(e.ref) in ids
        ]

    def get_place(
        self, place_id: uuid.UUID, headers: dict[str, str] | None = None
    ) -> dict[str, Any]:
        r = self.env.client.get(f"/v1/places/{place_id}", headers=headers or self.env.headers)
        assert r.status_code == 200, r.text
        body: dict[str, Any] = r.json()
        return body


@pytest.fixture
def fx(api_env: ApiEnv) -> Iterator[Fx]:
    fixture = Fx(api_env)
    yield fixture
    fixture.engine.dispose()


def _search(fx: Fx, q: str) -> list[dict[str, Any]]:
    r = fx.env.client.get("/v1/places/search", params={"q": q}, headers=fx.env.headers)
    assert r.status_code == 200, r.text
    results: list[dict[str, Any]] = r.json()["results"]
    return results


# -- the migration and the import ------------------------------------------------------------------


def test_the_import_keeps_search_aliases_and_search_finds_them(fx: Fx) -> None:
    [(aliases,)] = fx.sql("SELECT alias_norm FROM geo.place WHERE name = 'Östertal Heimatmuseum'")
    assert "oestertal heimatmuseum" in aliases.split("|")
    # An accented name is found by its German ASCII spelling.
    assert any(r["name"] == "Östertal Heimatmuseum" for r in _search(fx, "Oestertal"))
    museum = [r for r in _search(fx, "Testburger Museum") if r["name"] == "Testburg Museum"]
    assert museum, "name:de is a search alias"
    # Restaurants are not imported (ADR 026), so nothing of them is searchable here.
    assert not _search(fx, "Tokyo Ramen")


# -- enrichment ---------------------------------------------------------------------------------------


def test_a_japanese_place_gets_its_english_name_and_keeps_the_original(fx: Fx) -> None:
    place = fx.add_place("姫路城", {"ja": "姫路城"}, "Q233413")
    before = fx.get_place(place)["names"]
    assert (before["display"], before["type"]) == ("姫路城", "original")  # kanji: never guessed

    report = fx.run(fx.place_entities(place))
    assert (report.found, report.no_item, report.stopped) == (1, 0, None)
    names = fx.get_place(place)["names"]
    assert names == {
        "display": "Himeji Castle",
        "local": "姫路城",
        "local_lang": "ja",
        "type": "established_english",
        "source": "wikidata",
        "confidence": 0.98,
        "auto_generated": False,
        "user_override": False,
    }
    # Only names and identifiers are stored, each with its licence; one row is preferred.
    rows = fx.sql(
        "SELECT name, lang, source, name_type, licence_code, is_preferred, expires_at IS NOT NULL"
        " FROM geo.place_name WHERE entity_ref = :r ORDER BY source, lang, name",
        r=str(place),
    )
    assert {(r.name, r.source, r.name_type) for r in rows} == {
        ("Himeji Castle", "enwiki", "established_english"),
        ("Himeji Castle", "wikidata", "established_english"),
        ("White Heron Castle", "wikidata", "search_alias"),
        ("姫路城", "wikidata", "search_alias"),
    }
    assert {r.licence_code for r in rows} == {"CC0-1.0"} and all(r[6] for r in rows)
    assert [r.name for r in rows if r.is_preferred] == ["Himeji Castle"]
    assert [r.source for r in rows if r.is_preferred] == ["wikidata"]
    # Search finds it by the English name and by a Wikidata alias.
    assert any(r["id"] == str(place) for r in _search(fx, "Himeji Castle"))
    assert any(r["id"] == str(place) for r in _search(fx, "White Heron"))


def test_no_english_name_is_cached_and_not_asked_again(fx: Fx) -> None:
    place = fx.add_place("名もなき祠", {"ja": "名もなき祠"}, "Q7001")
    report = fx.run(fx.place_entities(place))
    assert (report.found, report.no_english) == (0, 1)
    assert report.unresolved == [
        {
            "kind": "place",
            "ref": str(place),
            "name": "名もなき祠",
            "reason": "no_english_label_or_article",
        }
    ]
    [(status, retry)] = fx.sql(
        "SELECT status, retry_after FROM geo.place_name_lookup WHERE entity_ref = :r", r=str(place)
    )
    assert status == "no_english" and retry > datetime.now(UTC) + timedelta(days=89)
    asked = len(fx.wiki.requests)
    assert fx.place_entities(place) == []  # not due: nothing is asked again
    assert len(fx.wiki.requests) == asked
    assert fx.get_place(place)["names"]["display"] == "名もなき祠"


def test_an_unknown_item_is_recorded_as_no_item(fx: Fx) -> None:
    place = fx.add_place("Nowhere Tower", None, "Q404404")
    report = fx.run(fx.place_entities(place))
    assert report.no_item == 1 and report.by_reason == {"item_missing": 1}


def test_cached_names_are_used_while_wikidata_is_down_and_planning_is_not_blocked(fx: Fx) -> None:
    place = fx.add_place("姫路城", {"ja": "姫路城"}, "Q233413")
    fx.run(fx.place_entities(place))
    # Due again (the 90 days have passed), but Wikidata is unavailable.
    fx.sql("UPDATE geo.place_name_lookup SET retry_after = now() - interval '1 day'")
    fx.sql("UPDATE geo.place_name SET expires_at = now() - interval '1 day'")
    fx.wiki.down = True
    report = fx.run(fx.place_entities(place))
    assert report.stopped is not None and report.found == 0
    assert fx.get_place(place)["names"]["display"] == "Himeji Castle"  # the cached name
    # Generation never waits for or calls Wikidata.
    with TestClient(
        create_app(fx.settings, wikimedia_transport=httpx.MockTransport(fx.wiki))
    ) as client:
        trip = client.post(
            "/v1/trips", json={"title": "T", **CITY, "duration_days": 1}, headers=fx.env.headers
        )
        assert trip.status_code == 201, trip.text
        r = client.post(
            f"/v1/trips/{trip.json()['id']}/itineraries/generate", headers=fx.env.headers
        )
        assert r.status_code == 201, r.text


def test_a_city_is_matched_by_its_geonames_id_and_gets_its_local_name(fx: Fx) -> None:
    with fx.engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE geo.place SET names_i18n = jsonb_build_object('de', name) WHERE city_id = 900101 AND name IS NOT NULL"
            )
        )
    report = fx.run([enrich.Entity("city", "900101", None, lang_hint="de")])
    assert report.found == 1
    [(qid, status, reason)] = fx.sql(
        "SELECT qid, status, reason FROM geo.place_name_lookup WHERE entity_kind = 'city'"
    )
    assert (qid, status, reason) == ("Q9001", "found", "geonames_id")
    with fx.engine.begin() as conn:
        from detour_api.names.store import resolve_cities

        resolved = resolve_cities(conn, [900101])[900101]
    assert (resolved.display, resolved.local, resolved.local_lang) == (
        "Testburg",
        "Testenburg",
        "de",
    )


def test_background_enrichment_after_generation_names_the_plan(fx: Fx) -> None:
    # The fixture's museum and castle carry Q1001 and Q1002.
    with TestClient(
        create_app(fx.settings, wikimedia_transport=httpx.MockTransport(fx.wiki))
    ) as client:
        trip = client.post(
            "/v1/trips", json={"title": "T", **CITY, "duration_days": 2}, headers=fx.env.headers
        ).json()
        plans = client.post(
            f"/v1/trips/{trip['id']}/itineraries/generate", headers=fx.env.headers
        ).json()
        itinerary = client.get(
            f"/v1/itineraries/{plans['itineraries'][0]['id']}", headers=fx.env.headers
        ).json()
    items = {i["display_name"]: i for d in itinerary["days"] for i in d["items"]}
    museum = items["Testburg Museum"]  # the snapshot stays as generated
    assert museum["names"]["display"] == "Testburg Museum of Art"  # read through the resolver
    assert museum["names"]["source"] == "wikidata" and museum["names"]["local"] == "Testburg Museum"
    # Found through its wikipedia tag (de:Mühlbach), asked of Wikidata by sitelink.
    assert items["Mühlbach Aussicht"]["names"]["display"] == "Mühlbach Lookout"
    lookups = fx.sql("SELECT entity_kind, status, reason FROM geo.place_name_lookup ORDER BY 1, 2")
    assert ("city", "found", "geonames_id") in [tuple(r) for r in lookups]


# -- user overrides -------------------------------------------------------------------------------


def test_an_override_wins_is_reversible_and_applies_to_that_place_only(fx: Fx) -> None:
    first = fx.add_place("Schlossberg", {"de": "Schlossberg"}, None)
    twin = fx.add_place("Schlossberg", {"de": "Schlossberg"}, None, lat=48.30, lon=16.45)
    r = fx.env.client.put(
        f"/v1/places/{first}/display-name", json={"name": "Castle Hill"}, headers=fx.env.headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["display"] == "Castle Hill" and r.json()["user_override"] is True
    assert r.json()["local"] == "Schlossberg" and r.json()["confidence"] == 1.0
    assert r.json()["local_lang"] == "de"
    [(original, approved)] = fx.sql(
        "SELECT original_name, approved_at IS NOT NULL FROM app.place_name_override"
    )
    assert (original, approved) == ("Schlossberg", True)
    assert fx.get_place(first)["names"]["display"] == "Castle Hill"
    assert fx.get_place(twin)["names"]["display"] == "Schlossberg"  # same name, other place
    other = fx.env.other_installation()
    assert fx.get_place(first, other)["names"]["display"] == "Schlossberg"  # another user
    assert any(x["id"] == str(first) for x in _search(fx, "Schlossberg"))  # still found locally

    r = fx.env.client.delete(f"/v1/places/{first}/display-name", headers=fx.env.headers)
    assert r.status_code == 200 and r.json()["display"] == "Schlossberg"
    assert (
        fx.env.client.delete(f"/v1/places/{first}/display-name", headers=fx.env.headers).status_code
        == 404
    )
    assert fx.sql("SELECT count(*) FROM app.place_name_override")[0][0] == 0


def test_an_override_reaches_the_plans_snapshots(fx: Fx) -> None:
    trip = fx.env.client.post(
        "/v1/trips", json={"title": "T", **CITY, "duration_days": 2}, headers=fx.env.headers
    ).json()
    plans = fx.env.client.post(
        f"/v1/trips/{trip['id']}/itineraries/generate", headers=fx.env.headers
    ).json()
    plan_id = plans["itineraries"][0]["id"]
    castle = next(i for d in plans["itineraries"][0]["days"] for i in d["items"] if i["place_id"])
    original = castle["display_name"]
    fx.env.client.put(
        f"/v1/places/{castle['place_id']}/display-name",
        json={"name": "The Burg"},
        headers=fx.env.headers,
    )
    itinerary = fx.env.client.get(f"/v1/itineraries/{plan_id}", headers=fx.env.headers).json()
    [item] = [
        i for d in itinerary["days"] for i in d["items"] if i["place_id"] == castle["place_id"]
    ]
    assert item["display_name"] == "The Burg" and item["names"]["user_override"] is True
    # A new generation keeps it.
    again = fx.env.client.post(
        f"/v1/trips/{trip['id']}/itineraries/generate", headers=fx.env.headers
    ).json()
    plan_id = again["itineraries"][0]["id"]  # the regeneration replaced the unselected proposal
    names = {i["display_name"] for p in again["itineraries"] for d in p["days"] for i in d["items"]}
    assert "The Burg" in names and original not in names
    fx.env.client.delete(f"/v1/places/{castle['place_id']}/display-name", headers=fx.env.headers)
    itinerary = fx.env.client.get(f"/v1/itineraries/{plan_id}", headers=fx.env.headers).json()
    [item] = [
        i for d in itinerary["days"] for i in d["items"] if i["place_id"] == castle["place_id"]
    ]
    assert item["display_name"] == original


def test_an_override_needs_a_real_place_and_a_name(fx: Fx) -> None:
    r = fx.env.client.put(
        f"/v1/places/{uuid.uuid4()}/display-name", json={"name": "X"}, headers=fx.env.headers
    )
    assert r.status_code == 404
    place = fx.add_place("Schlossberg", None, None)
    r = fx.env.client.put(
        f"/v1/places/{place}/display-name", json={"name": ""}, headers=fx.env.headers
    )
    assert r.status_code == 422


# -- retention and the command ---------------------------------------------------------------------------


def test_prune_keeps_referenced_names_and_removes_expired_and_orphaned_ones(fx: Fx) -> None:
    kept = fx.add_place("姫路城", {"ja": "姫路城"}, "Q233413")
    dropped = fx.add_place("Himeji copy", None, "Q233413", lat=48.3)
    fx.run(fx.place_entities(kept, dropped))
    trip = fx.env.client.post(
        "/v1/trips", json={"title": "T", **CITY, "duration_days": 1}, headers=fx.env.headers
    ).json()
    itinerary = fx.env.client.post(
        f"/v1/trips/{trip['id']}/itineraries", headers=fx.env.headers
    ).json()
    r = fx.env.client.post(
        f"/v1/itineraries/{itinerary['id']}/days/1/items",
        json={"type": "visit", "place_id": str(kept), "duration_minutes": 60},
        headers=fx.env.headers,
    )
    assert r.status_code == 201, r.text
    fx.sql("UPDATE geo.place_name SET expires_at = now() - interval '1 day'")
    with fx.engine.begin() as conn:
        removed = prune(conn)
    assert removed["expired"] > 0
    refs = {r[0] for r in fx.sql("SELECT DISTINCT entity_ref FROM geo.place_name")}
    assert refs == {str(kept)}
    fx.sql("DELETE FROM geo.place_signal WHERE place_id = :p", p=kept)
    fx.sql("DELETE FROM app.itinerary_item WHERE place_id = :p", p=kept)
    fx.sql("DELETE FROM geo.place WHERE id = :p", p=kept)
    with fx.engine.begin() as conn:
        removed = prune(conn)
    # The names are gone (expired and no longer named), and so is the lookup of the gone place.
    assert removed["expired"] + removed["orphaned_names"] > 0 and removed["orphaned_lookups"] > 0
    assert fx.sql("SELECT count(*) FROM geo.place_name")[0][0] == 0


def test_the_backfill_command_rebuilds_aliases_without_network(
    fx: Fx, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fx.sql("UPDATE geo.place SET alias_norm = NULL")
    url = fx.env.database_url
    monkeypatch.setenv("DETOUR_IMPORT_DATABASE_URL", url)
    assert importer_main(["names", TEST_REGION.id, "--no-network"]) == 0
    out = capsys.readouterr().out
    assert '"updated": ' in out and '"wikidata": "skipped"' in out
    assert fx.sql("SELECT count(*) FROM geo.place WHERE alias_norm IS NOT NULL")[0][0] > 0
