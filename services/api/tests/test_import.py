"""The region import end to end on the synthetic extract (needs PostGIS, osm2pgsql, osmium).

The fixture ``tests/fixtures/region-sample.osm`` is invented map data built to hit every case of
the selection rule; it says nothing about any real place.
"""

from pathlib import Path

import psycopg
import pytest

from tests.import_helpers import (
    FIXTURES,
    TEST_REGION,
    canonical_geo_dump,
    import_fixture_gazetteer,
    import_fixture_region,
    migrate,
    require_tools,
    strip_run_details,
)

pytestmark = pytest.mark.db


@pytest.fixture
def pipeline_dbs(
    scratch_database_url: str,
    second_scratch_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[str, str]:
    require_tools()
    migrate(scratch_database_url, monkeypatch)
    return scratch_database_url, second_scratch_database_url


def test_report_counts_match_the_database(pipeline_dbs: tuple[str, str], tmp_path: Path) -> None:
    target, staging = pipeline_dbs
    report = import_fixture_region(target, staging, tmp_path)

    with psycopg.connect(target) as conn:
        rows: dict[str, int] = dict(
            conn.execute(
                "SELECT kind, count(*) FROM geo.place WHERE region_id = %s AND is_active"
                " GROUP BY kind",
                (TEST_REGION.id,),
            ).fetchall()
        )
        named = conn.execute(
            "SELECT kind, count(name) FROM geo.place WHERE region_id = %s GROUP BY kind",
            (TEST_REGION.id,),
        ).fetchall()
        areas = conn.execute("SELECT count(*) FROM geo.admin_area").fetchone()
        run = conn.execute(
            "SELECT status, counts, report FROM geo.import_run WHERE region_id = %s",
            (TEST_REGION.id,),
        ).fetchone()
        sources = conn.execute("SELECT count(*) FROM geo.place_source").fetchone()
        signals = conn.execute("SELECT count(*) FROM geo.place_signal").fetchone()
        profiles = conn.execute("SELECT count(*) FROM geo.restaurant_profile").fetchone()

    assert rows == {"attraction": 10, "restaurant": 4}
    assert {k: v["total"] for k, v in report["kinds"].items()} == rows
    assert {k: v["named"] for k, v in report["kinds"].items()} == dict(named)
    assert areas is not None and areas[0] == report["admin_areas"] == 2
    assert sources is not None and sources[0] == sum(rows.values())
    assert signals is not None and signals[0] == sum(rows.values())
    assert profiles is not None and profiles[0] == rows["restaurant"]
    assert run is not None
    status, counts, stored_report = run
    assert status == "succeeded"
    assert counts["places_total"] == 14
    assert stored_report["excluded"]["total"] == report["excluded"]["total"] == 12
    # Excluded objects are counted per class, with a reason.
    by_class = {(r["class"], r["reason"]): r["count"] for r in report["excluded"]["by_class"]}
    assert by_class[("historic=wayside_shrine", "adr003_excluded_class")] == 1
    assert by_class[("historic=memorial", "memorial_without_wikidata")] == 1
    assert by_class[("historic=memorial", "memorial_without_name")] == 1
    assert by_class[("historic=memorial", "memorial_excluded_subtype")] == 1
    assert by_class[("historic=yes", "generic_class_without_name_and_notability")] == 2
    assert sum(by_class.values()) == 12


def test_importing_twice_gives_identical_results(
    pipeline_dbs: tuple[str, str], tmp_path: Path
) -> None:
    target, staging = pipeline_dbs
    first_report = import_fixture_region(target, staging, tmp_path / "a")
    first = canonical_geo_dump(target, TEST_REGION.id)
    second_report = import_fixture_region(target, staging, tmp_path / "b")
    second = canonical_geo_dump(target, TEST_REGION.id)

    assert first["place"], "the fixture must produce places"
    assert first == second
    assert strip_run_details(first_report) == strip_run_details(second_report)
    with psycopg.connect(target) as conn:
        runs = conn.execute(
            "SELECT count(*), count(*) FILTER (WHERE status = 'succeeded'),"
            " (SELECT count(*) FROM geo.place WHERE NOT is_active)"
            " FROM geo.import_run"
        ).fetchone()
    assert runs == (2, 2, 0)


def test_place_ids_are_stable_and_derived_from_the_source_reference(
    pipeline_dbs: tuple[str, str], tmp_path: Path
) -> None:
    from detour_api.textnorm import stable_uuid

    target, staging = pipeline_dbs
    import_fixture_region(target, staging, tmp_path)
    with psycopg.connect(target) as conn:
        row = conn.execute(
            "SELECT p.id, ps.source_ref FROM geo.place p JOIN geo.place_source ps"
            " ON ps.place_id = p.id WHERE p.name = 'Testburg Museum'"
        ).fetchone()
    assert row is not None
    place_id, ref = row
    assert ref == "node/1"
    assert str(place_id) == str(stable_uuid("place", "test-region/osm/node/1"))


def test_a_place_missing_from_a_later_extract_is_deactivated_not_deleted(
    pipeline_dbs: tuple[str, str], tmp_path: Path
) -> None:
    target, staging = pipeline_dbs
    import_fixture_region(target, staging, tmp_path / "a")
    original = (FIXTURES / "region-sample.osm").read_text(encoding="utf-8")
    lines = [line for line in original.splitlines() if 'id="12"' not in line]
    assert len(lines) == len(original.splitlines()) - 1
    smaller = tmp_path / "smaller.osm"
    smaller.write_text("\n".join(lines) + "\n", encoding="utf-8")

    second = import_fixture_region(target, staging, tmp_path / "b", pbf=smaller)

    with psycopg.connect(target) as conn:
        row = conn.execute(
            "SELECT is_active FROM geo.place WHERE name = 'Zur Alten Post'"
        ).fetchone()
        active = conn.execute("SELECT count(*) FROM geo.place WHERE is_active").fetchone()
    assert row == (False,)
    assert active == (13,)
    assert second["kinds"]["restaurant"]["total"] == 3
    with psycopg.connect(target) as conn:
        counts = conn.execute(
            "SELECT counts FROM geo.import_run ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
    assert counts is not None and counts[0]["places_deactivated"] == 1


def test_unknown_values_stay_unknown_and_opening_hours_are_never_stored(
    pipeline_dbs: tuple[str, str], tmp_path: Path
) -> None:
    target, staging = pipeline_dbs
    import_fixture_region(target, staging, tmp_path)
    with psycopg.connect(target) as conn:
        unnamed_cafe = conn.execute(
            "SELECT p.name, p.name_norm, rp.cuisines, rp.diet_flags, rp.provider_price_level,"
            " p.default_visit_minutes FROM geo.place p JOIN geo.restaurant_profile rp"
            " ON rp.place_id = p.id WHERE p.category = 'cafe' AND p.name IS NULL"
        ).fetchone()
        post = conn.execute(
            "SELECT rp.cuisines, rp.diet_flags, rp.meal_types FROM geo.place p"
            " JOIN geo.restaurant_profile rp ON rp.place_id = p.id WHERE p.name = 'Zur Alten Post'"
        ).fetchone()
        museum = conn.execute(
            "SELECT p.names_i18n, p.address, s.wikidata_id, s.sitelink_count, s.score"
            " FROM geo.place p JOIN geo.place_signal s ON s.place_id = p.id"
            " WHERE p.name = 'Testburg Museum'"
        ).fetchone()
        hours = conn.execute(
            "SELECT count(*) FROM geo.place_source WHERE tags ? 'opening_hours'"
        ).fetchone()
    assert unnamed_cafe == (None, None, None, None, None, None)
    assert post == (["austrian", "regional"], ["vegan_only", "vegetarian"], ["dinner", "lunch"])
    assert museum is not None
    names, address, wikidata, sitelinks, score = museum
    assert names == {"de": "Testburger Museum", "en": "Testburg Museum"}
    assert address == {"street": "Teststrasse", "housenumber": "1", "city": "Testburg"}
    assert wikidata == "Q1001"
    assert sitelinks is None  # Wikidata is not fetched in Phase 2: unknown, not zero
    assert float(score) == 4.0  # has_wikidata 3 + has_name 1 (derive.SCORE_WEIGHTS)
    assert hours == (0,)


def test_osm_data_is_stored_as_odbl_source_records(
    pipeline_dbs: tuple[str, str], tmp_path: Path
) -> None:
    target, staging = pipeline_dbs
    import_fixture_region(target, staging, tmp_path)
    with psycopg.connect(target) as conn:
        licences = conn.execute(
            "SELECT DISTINCT ps.source, ps.licence_code, l.share_alike FROM geo.place_source ps"
            " JOIN geo.licence l ON l.code = ps.licence_code"
        ).fetchall()
        area_licences = conn.execute("SELECT DISTINCT licence_code FROM geo.admin_area").fetchall()
    assert licences == [("osm", "ODbL-1.0", True)]
    assert area_licences == [("ODbL-1.0",)]


def test_a_small_region_fails_the_gates_and_stays_disabled(
    pipeline_dbs: tuple[str, str], tmp_path: Path
) -> None:
    target, staging = pipeline_dbs
    report = import_fixture_region(target, staging, tmp_path)
    assert report["all_gates_passed"] is False
    assert report["region_status"] == "disabled"
    failing = {g["gate"] for g in report["gates"] if not g["passed"]}
    assert failing == {1, 3, 4, 5}  # 3 of 4 restaurants named, 4 restaurants, 9 attractions...
    with psycopg.connect(target) as conn:
        row = conn.execute(
            "SELECT status, current_import_run_id IS NOT NULL FROM geo.region WHERE id = %s",
            (TEST_REGION.id,),
        ).fetchone()
    assert row == ("disabled", True)


def test_failed_import_is_recorded_and_changes_nothing(
    pipeline_dbs: tuple[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from detour_api.importer import loader

    target, staging = pipeline_dbs
    import_fixture_region(target, staging, tmp_path / "a")
    before = canonical_geo_dump(target, TEST_REGION.id)

    def boom(*_: object, **__: object) -> None:
        raise loader.ImportError_("simulated failure after the merge")

    monkeypatch.setattr(loader, "_verify_counts", boom)
    with pytest.raises(loader.ImportError_):
        import_fixture_region(target, staging, tmp_path / "b")

    assert canonical_geo_dump(target, TEST_REGION.id) == before
    with psycopg.connect(target) as conn:
        statuses = conn.execute(
            "SELECT status, error FROM geo.import_run ORDER BY started_at"
        ).fetchall()
    assert [s for s, _ in statuses] == ["succeeded", "failed"]
    assert "simulated failure" in statuses[1][1]


def test_gazetteer_import_loads_only_the_requested_countries(
    pipeline_dbs: tuple[str, str],
) -> None:
    target, _ = pipeline_dbs
    counts = import_fixture_gazetteer(target, ["AT"])
    assert counts["countries"] == 4 and counts["currencies"] == 3
    assert counts["cities"] == 5 and counts["admin_codes"] == 2
    with psycopg.connect(target) as conn:
        cities = conn.execute("SELECT name, population FROM geo.city ORDER BY id").fetchall()
        countries = conn.execute(
            "SELECT iso2, default_currency_code FROM geo.country ORDER BY iso2"
        ).fetchall()
        alt = conn.execute(
            "SELECT alt_names, alt_names_norm FROM geo.city WHERE id = 900101"
        ).fetchone()
        codes = conn.execute("SELECT code FROM geo.admin_code ORDER BY code").fetchall()
    assert [c[0] for c in cities] == [
        "Testburg",
        "Testburg-Neustadt",
        "Mühlbach",
        "Östertal",
        "Alpenau",
    ]
    populations: dict[str, int | None] = dict(cities)
    assert populations["Östertal"] is None  # population 0 means unknown in GeoNames
    assert ("AQ", None) in countries and ("AT", "EUR") in countries
    assert alt is not None
    assert alt[0] == ["Testburgo", "Testenburg", "Testburg City"]
    assert alt[1] == "testburgo|testenburg|testburg city"
    assert codes == [("AT.09",), ("AT.09.901",)]


def test_gazetteer_import_twice_is_identical(pipeline_dbs: tuple[str, str]) -> None:
    target, _ = pipeline_dbs
    import_fixture_gazetteer(target, ["AT", "JP"])
    with psycopg.connect(target) as conn:
        first = conn.execute("SELECT * FROM geo.city ORDER BY id").fetchall()
    import_fixture_gazetteer(target, ["AT", "JP"])
    with psycopg.connect(target) as conn:
        second = conn.execute("SELECT * FROM geo.city ORDER BY id").fetchall()
    assert first == second and len(first) == 6


@pytest.mark.parametrize("gazetteer_first", [True, False])
def test_places_get_their_nearest_city_in_either_import_order(
    pipeline_dbs: tuple[str, str], tmp_path: Path, gazetteer_first: bool
) -> None:
    target, staging = pipeline_dbs
    if gazetteer_first:
        import_fixture_gazetteer(target, ["AT"])
        report = import_fixture_region(target, staging, tmp_path)
        assert not any("No gazetteer" in w for w in report["warnings"])
    else:
        report = import_fixture_region(target, staging, tmp_path)
        assert any("No gazetteer" in w for w in report["warnings"])
        import_fixture_gazetteer(target, ["AT"])
    with psycopg.connect(target) as conn:
        rows: dict[str, str | None] = dict(
            conn.execute(
                "SELECT COALESCE(p.name, p.category), c.name FROM geo.place p"
                " LEFT JOIN geo.city c ON c.id = p.city_id"
                " WHERE p.name IN ('Testburg Museum', 'Mühlbach Aussicht', 'Café Östertal')"
            ).fetchall()
        )
        areas = conn.execute("SELECT DISTINCT country_iso2 FROM geo.admin_area").fetchall()
    assert rows == {
        "Testburg Museum": "Testburg",
        "Mühlbach Aussicht": "Mühlbach",
        "Café Östertal": "Östertal",
    }
    assert areas == [("AT",)]  # single-country region: areas belong to that country


def test_review_sample_is_deterministic_and_limited(
    pipeline_dbs: tuple[str, str], tmp_path: Path
) -> None:
    from detour_api.importer.cli import run_region_import

    target, staging = pipeline_dbs
    out_a, out_b = tmp_path / "a", tmp_path / "b"
    for out in (out_a, out_b):
        run_region_import(
            TEST_REGION,
            target_url=target,
            staging_url=staging,
            work_dir=tmp_path / "w",
            out_dir=out,
            pbf=FIXTURES / "region-sample.osm",
        )
    assert (out_a / "report.md").read_text().startswith("# Region import report")
    sample_a = (out_a / "review-sample.json").read_text()
    assert sample_a == (out_b / "review-sample.json").read_text()
    assert "historic=memorial / kept" in sample_a
    assert "historic=memorial / excluded:memorial_without_wikidata" in sample_a
