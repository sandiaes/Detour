"""Destination and place search against the imported fixture region and gazetteer."""

from typing import Any

import pytest

from tests.conftest import ApiEnv
from tests.test_api_planning import sql
from tests.test_api_trips import CITY

pytestmark = pytest.mark.db


def search(env: ApiEnv, path: str, **params: object) -> dict[str, Any]:
    response = env.client.get(path, params=params, headers=env.headers)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def names(body: dict[str, Any]) -> list[str]:
    return [r["name"] for r in body["results"]]


# query -> (names expected first, in order, whether nothing else may follow). Written from the
# fixture data, not from the output. Fuzzy (trigram) matching may add weaker hits after the
# expected ones, which is the intended typo tolerance.
DESTINATION_FIXTURES = [
    ("testburg", ["Testburg", "Testburg-Neustadt", "Bezirk Testburg"], True),
    ("TESTBURG", ["Testburg", "Testburg-Neustadt", "Bezirk Testburg"], True),  # case-insensitive
    ("muhlbach", ["Mühlbach"], True),  # accents ignored
    ("Mühlbach", ["Mühlbach"], True),
    ("mulbach", ["Mühlbach"], True),  # alternate name
    ("testenburg", ["Testburg"], False),  # alternate name, then fuzzy neighbours
    ("testland", ["Testland"], True),  # an area (OSM boundary, admin level 4)
    ("甲南", ["Kōnan"], True),  # alternate name in another script
    ("konan", ["Kōnan"], True),
    ("zzzz", [], True),
]


@pytest.mark.parametrize(("query", "expected", "strict"), DESTINATION_FIXTURES)
def test_destination_search_fixture_list(
    api_env: ApiEnv, query: str, expected: list[str], strict: bool
) -> None:
    got = names(search(api_env, "/v1/destinations/search", q=query))
    assert got == expected if strict else got[: len(expected)] == expected


def test_destination_result_shape_and_availability(api_env: ApiEnv) -> None:
    body = search(api_env, "/v1/destinations/search", q="testburg", limit=1)
    (city,) = body["results"]
    assert city["kind"] == "city" and city["ref"] == "900101"
    assert city["country_iso2"] == "AT" and city["country_name"] == "Testland"
    assert city["admin1_name"] == "Testland State"
    assert city["population"] == 120000 and city["match"] == "exact"
    assert (city["region_id"], city["planning_available"]) == ("test-region", True)
    assert city["lat"] == pytest.approx(48.2082) and city["lon"] == pytest.approx(16.3738)
    assert body["external"] == {"state": "not_requested", "provider": None, "results": []}


def test_unknown_population_is_null_and_areas_have_a_level(api_env: ApiEnv) -> None:
    (oester,) = search(api_env, "/v1/destinations/search", q="ostertal")["results"]
    assert oester["population"] is None  # GeoNames 0 = unknown, never shown as 0
    (area,) = search(api_env, "/v1/destinations/search", q="testland")["results"]
    assert area["kind"] == "area" and area["admin_level"] == 4 and area["population"] is None
    assert area["country_iso2"] == "AT" and area["planning_available"] is True


def test_destinations_outside_an_available_region_are_marked(api_env: ApiEnv) -> None:
    (konan,) = search(api_env, "/v1/destinations/search", q="konan")["results"]
    assert konan["country_iso2"] == "JP"
    assert konan["region_id"] is None and konan["planning_available"] is False


def test_a_region_that_is_not_available_is_not_plannable(api_env: ApiEnv) -> None:
    import psycopg

    with psycopg.connect(api_env.database_url, autocommit=True) as conn:
        conn.execute("UPDATE geo.region SET status = 'disabled'")
    (city,) = search(api_env, "/v1/destinations/search", q="testburg", limit=1)["results"]
    assert city["region_id"] == "test-region" and city["planning_available"] is False


@pytest.mark.parametrize("path", ["/v1/destinations/search", "/v1/places/search"])
def test_search_needs_a_token_and_a_sensible_query(api_env: ApiEnv, path: str) -> None:
    assert api_env.client.get(path, params={"q": "testburg"}).status_code == 401
    assert api_env.client.get(path, params={"q": "a"}, headers=api_env.headers).status_code == 422
    assert (
        api_env.client.get(path, params={"q": "x" * 101}, headers=api_env.headers).status_code
        == 422
    )


def test_search_text_is_bound_not_interpolated(api_env: ApiEnv) -> None:
    hostile = "x'; DROP TABLE geo.city; --"
    for path in ("/v1/destinations/search", "/v1/places/search"):
        assert search(api_env, path, q=hostile)["results"] == []
    assert search(api_env, "/v1/destinations/search", q="testburg")["results"]
    for q in ("100%", "a_b", "\\\\", "%%"):
        search(api_env, "/v1/places/search", q=q)


# (parameters, names that must be among the results, names that must NOT be). Fuzzy matching may
# add weaker hits, so absence is asserted only for the objects the selection rule excludes.
PLACE_FIXTURES = [
    ({"q": "museum"}, ["Testburg Museum"], []),
    (
        {"q": "testburg", "kind": "attraction"},
        ["Testburg Museum", "Testburg Castle", "Testburg Zoo"],
        [],
    ),
    ({"q": "heimatmuseum ostertal"}, ["Östertal Heimatmuseum"], []),  # accents ignored
    ({"q": "heimatmuseum östertal"}, ["Östertal Heimatmuseum"], []),
    # ADR 026: restaurants and cafes are not imported, so none can be found
    ({"q": "post"}, [], ["Zur Alten Post"]),
    ({"q": "東京"}, [], ["東京ラーメン"]),
    ({"q": "notable"}, ["Notable memorial", "Notable yes"], []),
    ({"q": "plaque"}, [], ["Plaque"]),  # memorial subtype excluded by the selection rule
    ({"q": "plain memorial"}, [], ["Plain memorial"]),  # memorial without wikidata
    ({"q": "old house"}, [], ["Old house"]),  # historic=building without notability
    ({"q": "old rails"}, [], ["Old rails"]),  # historic=railway without notability
    ({"q": "named but ordinary"}, [], ["Named but ordinary"]),  # historic=yes, no notability
    ({"q": "heritage house"}, ["Heritage house"], []),
    ({"q": "ignored bakery"}, [], ["Ignored bakery"]),  # not a candidate class
    ({"q": "old milestone"}, [], ["Old milestone"]),  # not a tourist class
    ({"q": "old line"}, [], ["Old line"]),  # railway
    ({"q": "tree shrine"}, [], ["Tree shrine"]),
    ({"q": "heritage thing"}, [], ["Heritage thing"]),
    ({"q": "city wall"}, ["Old city wall"], ["City wall bit"]),
    ({"q": "remote gasthaus"}, [], ["Remote Gasthaus"]),
    ({"q": "remote cafe"}, [], ["Remote Cafe"]),
    ({"q": "neustadt gasthaus"}, [], ["Neustadt Gasthaus"]),
    ({"q": "cafe ostertal"}, [], ["Café Östertal"]),
]


@pytest.mark.parametrize(("params", "present", "absent"), PLACE_FIXTURES)
def test_place_search_fixture_list(
    api_env: ApiEnv, params: dict[str, str], present: list[str], absent: list[str]
) -> None:
    got = names(search(api_env, "/v1/places/search", **params))
    for name in present:
        assert name in got
    for name in absent:
        assert name not in got


def test_exact_matches_rank_first_and_ties_break_by_id(api_env: ApiEnv) -> None:
    body = search(api_env, "/v1/places/search", q="testburg zoo")
    assert names(body)[0] == "Testburg Zoo"
    assert body["results"][0]["match"] == "exact"


def test_near_search_orders_by_distance_and_honours_the_radius(api_env: ApiEnv) -> None:
    museum = (48.2082, 16.3738)
    wide = search(api_env, "/v1/places/search", lat=museum[0], lon=museum[1], radius_m=500)
    got = wide["results"]
    assert [r["name"] for r in got][:2] == ["Testburg Museum", "Mühlbach Aussicht"]
    distances = [r["distance_m"] for r in got]
    assert distances == sorted(distances) and distances[0] == pytest.approx(0, abs=1)
    assert 250 < distances[1] < 400  # Mühlbach Aussicht, about 325 m away
    narrow = search(api_env, "/v1/places/search", lat=museum[0], lon=museum[1], radius_m=100)
    assert names(narrow) == ["Testburg Museum"]


def test_near_search_can_combine_text_and_kind(api_env: ApiEnv) -> None:
    body = search(
        api_env,
        "/v1/places/search",
        q="heimatmuseum",
        lat=48.2215,
        lon=16.3815,
        radius_m=200,
        kind="attraction",
    )
    assert names(body) == ["Östertal Heimatmuseum"]


def test_the_restaurant_kind_is_no_longer_searchable(api_env: ApiEnv) -> None:
    r = api_env.client.get(
        "/v1/places/search", params={"q": "post", "kind": "restaurant"}, headers=api_env.headers
    )
    assert r.status_code == 422


def test_search_results_carry_no_cuisine_or_meal_fields(api_env: ApiEnv) -> None:
    museum = search(api_env, "/v1/places/search", q="testburg museum")["results"][0]
    assert "cuisines" not in museum and "venue_type" not in museum
    assert museum["city_name"] is not None


@pytest.mark.parametrize(
    ("params", "status", "code"),
    [
        ({}, 422, "query_required"),
        ({"lat": 48.2}, 422, "lat_lon_together"),
        ({"q": "museum", "radius_m": 100}, 422, "radius_needs_point"),
        ({"q": "museum", "region": "nowhere"}, 404, "not_found"),
        ({"q": "museum", "kind": "hotel"}, 422, None),
        ({"lat": 91, "lon": 0}, 422, None),
    ],
)
def test_place_search_validation(
    api_env: ApiEnv, params: dict[str, object], status: int, code: str | None
) -> None:
    response = api_env.client.get("/v1/places/search", params=params, headers=api_env.headers)
    assert response.status_code == status
    if code:
        assert response.json()["code"] == code


def test_place_detail_shows_provenance_and_unknowns(api_env: ApiEnv) -> None:
    (hit,) = search(api_env, "/v1/places/search", q="testburg museum")["results"][:1]
    response = api_env.client.get(f"/v1/places/{hit['id']}", headers=api_env.headers)
    assert response.status_code == 200
    place = response.json()
    assert place["wikidata_id"] == "Q1001" and place["is_active"] is True
    assert place["default_visit_minutes"] is None  # no rule table yet: unknown, not guessed
    assert place["address"] == {"street": "Teststrasse", "housenumber": "1", "city": "Testburg"}
    assert place["names_i18n"]["de"] == "Testburger Museum"
    assert place["sources"] == [
        {
            "source": "osm",
            "source_ref": "node/1",
            "licence": "ODbL-1.0",
            "attribution": "© OpenStreetMap contributors",
        }
    ]
    assert "opening_hours" not in response.text
    missing = api_env.client.get(
        "/v1/places/00000000-0000-0000-0000-000000000000", headers=api_env.headers
    )
    assert missing.status_code == 404 and missing.json()["code"] == "not_found"


def test_regions_and_attributions(api_env: ApiEnv) -> None:
    regions = api_env.client.get("/v1/regions").json()
    (region,) = regions
    assert region["id"] == "test-region" and region["status"] == "available"
    assert region["counts"] == {"attraction": 11}
    assert region["data_version"]["import_run_id"]
    credits = api_env.client.get("/v1/attributions").json()
    by_name = {c["name"]: c for c in credits}
    assert by_name["OpenStreetMap"]["text"] == "© OpenStreetMap contributors"
    assert by_name["OpenStreetMap"]["licence"] == "ODbL-1.0"
    assert by_name["GeoNames"]["licence"] == "CC-BY-4.0"
    assert any(c["applies_to"] == "The map" for c in credits)


def test_place_search_matches_the_english_name_and_the_original(api_env: ApiEnv) -> None:
    import json
    import uuid

    import psycopg

    pid = uuid.uuid4()
    with psycopg.connect(api_env.database_url, autocommit=True) as conn:
        [(run,)] = conn.execute(
            "SELECT current_import_run_id FROM geo.region WHERE id = 'test-region'"
        ).fetchall()
        conn.execute(
            "INSERT INTO geo.place (id, region_id, kind, category, name, name_norm, names_i18n,"
            " name_en_norm, geom, first_import_run_id, last_changed_import_run_id)"
            " VALUES (%s, 'test-region', 'attraction', 'castle', 'Festung Zwergenberg',"
            " 'festung zwergenberg', %s, 'dwarfberg fortress',"
            " ST_SetSRID(ST_MakePoint(16.37, 48.21), 4326), %s, %s)",
            (pid, json.dumps({"en": "Dwarfberg Fortress"}), run, run),
        )
    try:
        for q in ("zwergenberg", "dwarfberg fortress", "Dwarfberg"):
            hits = search(api_env, "/v1/places/search", q=q, region="test-region")["results"]
            hit = next(h for h in hits if h["id"] == str(pid))
            assert hit["name"] == "Festung Zwergenberg"
            assert hit["name_en"] == "Dwarfberg Fortress"
        detail = api_env.client.get(f"/v1/places/{pid}", headers=api_env.headers).json()
        assert detail["name_en"] == "Dwarfberg Fortress"
    finally:
        with psycopg.connect(api_env.database_url, autocommit=True) as conn:
            conn.execute("DELETE FROM geo.place WHERE id = %s", (pid,))


def _test_region_covers(api_env: ApiEnv, lon: float, lat: float, half: float = 0.1) -> None:
    """Give the fixture region a known coverage polygon: a box around a point."""
    sql(
        api_env,
        "UPDATE geo.region SET geom = ST_Multi(ST_MakeEnvelope(%s, %s, %s, %s, 4326))"
        " WHERE id = 'test-region'",
        lon - half,
        lat - half,
        lon + half,
        lat + half,
    )


def test_a_region_with_a_known_polygon_covers_only_the_places_inside_it(api_env: ApiEnv) -> None:
    """A city extract (Greater London, Paris) claims its whole country by code; a city outside its
    polygon is not in the region, so planning there says the region is not available."""
    # No polygon: the country code decides (the region of the fixture covers Testland).
    (city,) = search(api_env, "/v1/destinations/search", q="testburg", limit=1)["results"]
    assert (city["region_id"], city["planning_available"]) == ("test-region", True)
    # A polygon around Testburg: still covered, and so is Alpenau just outside it (slack).
    _test_region_covers(api_env, 16.3738, 48.2082)
    (city,) = search(api_env, "/v1/destinations/search", q="testburg", limit=1)["results"]
    assert (city["region_id"], city["planning_available"]) == ("test-region", True)
    # A polygon far away (another part of the country): Testburg is not in the region.
    _test_region_covers(api_env, 9.0, 47.0)
    (city,) = search(api_env, "/v1/destinations/search", q="testburg", limit=1)["results"]
    assert city["region_id"] is None and city["planning_available"] is False
    assert city["unavailable_reason"] == "region_not_available"
    # Creating a trip there and planning it is refused for the same reason.
    refused = api_env.client.post(
        "/v1/trips", json={**CITY, "title": "Outside", "duration_days": 1}, headers=api_env.headers
    )
    assert refused.status_code == 409 and refused.json()["code"] == "region_not_available"
