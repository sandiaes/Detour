"""The commands the Import region workflow runs, driven through ``main()``."""

import json
import zipfile
from pathlib import Path

import psycopg
import pytest

from detour_api.importer import cli, pipeline
from detour_api.importer.regions import REGIONS
from tests.import_helpers import FIXTURES, migrate, require_tools

pytestmark = pytest.mark.db


def test_countries_command_and_unknown_regions(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["countries", "austria"]) == 0
    assert capsys.readouterr().out.strip() == "AT"
    with pytest.raises(SystemExit, match="unknown region"):
        cli.main(["countries", "atlantis"])
    with pytest.raises(SystemExit, match="unknown region"):
        cli.main(["region", "atlantis"])


def test_every_known_region_has_a_geofabrik_url_and_countries() -> None:
    assert set(REGIONS) == {
        "austria",
        "czech-republic",
        "greater-london",
        "hungary",
        "italy",
        "japan",
    }
    for region in REGIONS.values():
        assert region.extract_url.startswith("https://download.geofabrik.de/")
        assert region.extract_url.endswith("-latest.osm.pbf")
        assert region.poly_url.endswith(".poly") and region.countries


def test_the_target_and_staging_urls_are_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DETOUR_IMPORT_DATABASE_URL", raising=False)
    with pytest.raises(SystemExit, match="DETOUR_IMPORT_DATABASE_URL"):
        cli.main(["region", "austria"])


def test_region_command_imports_a_local_extract_and_writes_the_report(
    scratch_database_url: str,
    second_scratch_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    require_tools()
    migrate(scratch_database_url, monkeypatch)
    monkeypatch.setenv("DETOUR_IMPORT_DATABASE_URL", scratch_database_url)
    monkeypatch.setenv("DETOUR_STAGING_DATABASE_URL", second_scratch_database_url)
    out = tmp_path / "out"
    args = [
        "region",
        "austria",
        "--pbf",
        str(FIXTURES / "region-sample.osm"),
        "--out-dir",
        str(out),
    ]

    # The fixture is far too small to pass ADR 009: the command exits 3 unless told otherwise.
    assert cli.main(args) == 3
    assert "Region status after this import: **disabled**" in capsys.readouterr().out
    assert cli.main([*args, "--allow-failed-gates"]) == 0

    report = json.loads((out / "report.json").read_text())
    assert report["region"]["id"] == "austria" and report["all_gates_passed"] is False
    assert {"report.json", "report.md", "review-sample.json"} <= {p.name for p in out.iterdir()}
    with psycopg.connect(scratch_database_url) as conn:
        assert conn.execute("SELECT status FROM geo.region WHERE id = 'austria'").fetchone() == (
            "disabled",
        )


def test_gazetteer_command_downloads_the_four_files_with_an_identifying_agent(
    scratch_database_url: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    require_tools()
    migrate(scratch_database_url, monkeypatch)
    monkeypatch.setenv("DETOUR_IMPORT_DATABASE_URL", scratch_database_url)
    monkeypatch.setenv("DETOUR_IMPORT_USER_AGENT", "Detour-test/1 (+https://example.invalid)")
    cities_zip = tmp_path / "cities.zip"
    with zipfile.ZipFile(cities_zip, "w") as archive:
        archive.writestr("cities1000.txt", (FIXTURES / "cities-sample.txt").read_text())
    served = {
        "countryInfo.txt": FIXTURES / "countryInfo.txt",
        "admin1CodesASCII.txt": FIXTURES / "admin1CodesASCII.txt",
        "admin2Codes.txt": FIXTURES / "admin2Codes.txt",
        "cities1000.zip": cities_zip,
    }
    requested: list[tuple[str, str]] = []

    def fake_download(
        url: str, dest: Path, user_agent: str = "", **_: object
    ) -> pipeline.DownloadResult:
        requested.append((url, user_agent))
        source = served[url.rsplit("/", 1)[1]]
        dest.write_bytes(source.read_bytes())
        return pipeline.DownloadResult(dest, "0" * 64, dest.stat().st_size, url)

    monkeypatch.setattr(pipeline, "download", fake_download)
    assert cli.main(["gazetteer", "AT"]) == 0
    assert sorted(url.rsplit("/", 1)[1] for url, _ in requested) == sorted(served)
    assert all(url.startswith("https://download.geonames.org/export/dump/") for url, _ in requested)
    assert {ua for _, ua in requested} == {"Detour-test/1 (+https://example.invalid)"}
    with psycopg.connect(scratch_database_url) as conn:
        assert conn.execute("SELECT count(*) FROM geo.city").fetchone() == (5,)


def test_a_missing_gazetteer_country_stops_the_import(
    scratch_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from detour_api.importer.gazetteer import GazetteerError
    from tests.import_helpers import import_fixture_gazetteer

    migrate(scratch_database_url, monkeypatch)
    with pytest.raises(GazetteerError, match="not in countryInfo"):
        import_fixture_gazetteer(scratch_database_url, ["XX"])
    with psycopg.connect(scratch_database_url) as conn:
        assert conn.execute("SELECT count(*) FROM geo.country").fetchone() == (
            0,
        )  # nothing half-loaded
