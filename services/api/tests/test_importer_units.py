"""Importer logic that needs no database: selection rule, derivation, gates, parsers."""

from pathlib import Path

import httpx
import pytest

from detour_api.importer import gazetteer, pipeline
from detour_api.importer.derive import build_place
from detour_api.importer.poly import poly_to_wkt
from detour_api.importer.report import (
    GEO_SIZE_LIMIT_BYTES,
    Counters,
    evaluate_gates,
    pct,
)
from detour_api.importer.selection import Decision, decide
from detour_api.textnorm import has_latin_letters, normalize_text, stable_uuid


@pytest.mark.parametrize(
    ("tags", "kept", "cls", "reason"),
    [
        ({"tourism": "museum", "name": "M"}, True, "tourism=museum", "tourism"),
        ({"tourism": "viewpoint", "name": "Lookout"}, True, "tourism=viewpoint", "tourism"),
        # ADR 011: an unnamed attraction cannot be shown in an itinerary
        ({"tourism": "viewpoint"}, False, "tourism=viewpoint", "attraction_without_name"),
        ({"tourism": "museum", "name": " "}, False, "tourism=museum", "attraction_without_name"),
        ({"tourism": "hotel"}, None, None, None),
        ({"shop": "bakery"}, None, None, None),
        # ADR 026: restaurants and cafes are no longer imported
        ({"amenity": "restaurant"}, None, None, None),
        ({"amenity": "cafe", "name": "x"}, None, None, None),
        ({"amenity": "pub"}, None, None, None),  # not imported in Phase 2
        # ADR 003: never imported
        (
            {"historic": "wayside_shrine", "name": "x", "wikidata": "Q1"},
            False,
            "historic=wayside_shrine",
            "adr003_excluded_class",
        ),
        ({"historic": "wayside_cross"}, False, "historic=wayside_cross", "adr003_excluded_class"),
        ({"historic": "boundary_stone"}, False, "historic=boundary_stone", "adr003_excluded_class"),
        ({"historic": "bomb_crater"}, False, "historic=bomb_crater", "adr003_excluded_class"),
        # stricter memorial test
        ({"historic": "memorial"}, False, "historic=memorial", "memorial_without_wikidata"),
        (
            {"historic": "memorial", "name": "n"},
            False,
            "historic=memorial",
            "memorial_without_wikidata",
        ),
        (
            {"historic": "memorial", "wikidata": "Q1"},
            False,
            "historic=memorial",
            "memorial_without_name",
        ),
        (
            {"historic": "memorial", "wikidata": "Q1", "name": " "},
            False,
            "historic=memorial",
            "memorial_without_name",
        ),
        (
            {"historic": "memorial", "wikidata": "Q1", "name": "n", "memorial": "plaque"},
            False,
            "historic=memorial",
            "memorial_excluded_subtype",
        ),
        (
            {"historic": "memorial", "wikidata": "Q1", "name": "n", "memorial": "Stolperstein"},
            False,
            "historic=memorial",
            "memorial_excluded_subtype",
        ),
        (
            {"historic": "memorial", "wikidata": "Q1", "name": "n", "memorial": "statue"},
            True,
            "historic=memorial",
            "memorial_with_wikidata_and_name",
        ),
        (
            {"historic": "memorial", "wikidata": "Q1", "name": "n"},
            True,
            "historic=memorial",
            "memorial_with_wikidata_and_name",
        ),
        # ADR 011, owner decision after the first real import: never imported, however notable
        (
            {"historic": "tree_shrine", "name": "n", "wikidata": "Q1"},
            False,
            "historic=tree_shrine",
            "adr003_excluded_class",
        ),
        (
            {"historic": "heritage", "name": "n", "wikidata": "Q1"},
            False,
            "historic=heritage",
            "adr003_excluded_class",
        ),
        (
            {"historic": "heritage_building", "name": "n"},
            False,
            "historic=heritage_building",
            "adr003_excluded_class",
        ),
        (
            {"historic": "Heritage Building"},
            False,
            "historic=Heritage Building",
            "adr003_excluded_class",
        ),
        ({"historic": " Tree_Shrine "}, False, "historic= Tree_Shrine ", "adr003_excluded_class"),
        # reviewed generic classes: name and a notability tag
        ({"historic": "yes"}, False, "historic=yes", "generic_class_without_name_and_notability"),
        (
            {"historic": "yes", "name": "n"},
            False,
            "historic=yes",
            "generic_class_without_name_and_notability",
        ),
        (
            {"historic": "yes", "wikidata": "Q1"},
            False,
            "historic=yes",
            "generic_class_without_name_and_notability",
        ),
        (
            {"historic": "yes", "name": "n", "wikipedia": "de:n"},
            True,
            "historic=yes",
            "generic_class_qualified",
        ),
        (
            {"historic": "building", "name": "n", "heritage": "2"},
            True,
            "historic=building",
            "generic_class_qualified",
        ),
        (
            {"historic": "stone", "name": "n", "wikidata": "Q1"},
            True,
            "historic=stone",
            "generic_class_qualified",
        ),
        (
            {"historic": "tomb", "name": "n"},
            False,
            "historic=tomb",
            "generic_class_without_name_and_notability",
        ),
        # the tourist allow-list (named)
        ({"historic": "castle", "name": "c"}, True, "historic=castle", "historic"),
        ({"historic": "castle"}, False, "historic=castle", "attraction_without_name"),
        ({"historic": "ruins", "name": "r"}, True, "historic=ruins", "historic"),
        ({"historic": "Ruins ", "name": "r"}, True, "historic=Ruins ", "historic"),
        ({"historic": "city_gate", "name": "g"}, True, "historic=city_gate", "historic"),
        # everything else is left out, and counted by class
        (
            {"historic": "milestone", "name": "m"},
            False,
            "historic=milestone",
            "historic_class_not_tourist",
        ),
        (
            {"historic": "cannon", "name": "c"},
            False,
            "historic=cannon",
            "historic_class_not_tourist",
        ),
        (
            {"historic": "locomotive", "name": "l"},
            False,
            "historic=locomotive",
            "historic_class_not_tourist",
        ),
        (
            {"historic": "something_new", "name": "x", "wikidata": "Q1"},
            False,
            "historic=something_new",
            "historic_class_not_tourist",
        ),
        # a cafe in a castle is the castle (the amenity is ignored)
        (
            {"amenity": "cafe", "historic": "castle", "name": "x"},
            True,
            "historic=castle",
            "historic",
        ),
    ],
)
def test_selection_rule(
    tags: dict[str, str], kept: bool | None, cls: str | None, reason: str | None
) -> None:
    decision = decide(tags)
    if kept is None:
        assert decision is None
        return
    assert decision is not None
    assert (decision.kept, decision.osm_class, decision.reason) == (kept, cls, reason)
    assert (decision.kind is not None) == kept


def test_the_tourist_allow_list_has_no_overlap_with_the_excluded_classes() -> None:
    from detour_api.importer import selection

    assert not selection.TOURIST_HISTORIC & selection.ALWAYS_EXCLUDED_HISTORIC
    assert not selection.TOURIST_HISTORIC & selection.QUALIFIED_ONLY_HISTORIC
    assert "railway" not in selection.TOURIST_HISTORIC | selection.QUALIFIED_ONLY_HISTORIC
    assert "historic=citywalls" in selection.REVIEW_CLASSES


def test_categories_of_generic_historic_classes_are_meaningful() -> None:
    qualified = {"name": "n", "wikidata": "Q1"}
    assert decide({"historic": "yes", **qualified}).category == "historic"  # type: ignore[union-attr]
    assert decide({"historic": "building", **qualified}).category == "historic_building"  # type: ignore[union-attr]


def test_opening_hours_never_reach_the_source_tags() -> None:
    tags = {"tourism": "museum", "name": "n", "opening_hours": "24/7", "name:en": "n"}
    decision = decide(tags)
    assert isinstance(decision, Decision)
    place = build_place("r", "N", 1, decision, tags, 16.0, 48.0)
    # The Lua style never copies opening_hours; derive keeps whatever it is given except the
    # columns that have their own place, so the guarantee is the Lua whitelist (tested end to
    # end in test_import). Here: names are not repeated in the source tags.
    assert "name:en" not in place.source_tags
    assert place.names_i18n == {"en": "n"}


def test_invalid_wikidata_values_are_unknown_not_guessed() -> None:
    tags = {"tourism": "museum", "name": "m", "wikidata": "Q1;Q2"}
    decision = decide(tags)
    assert decision is not None
    place = build_place("r", "N", 1, decision, tags, 1.0, 2.0)
    assert place.signal.wikidata_id is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Café  Östertal", "cafe ostertal"),
        ("Straße", "strasse"),
        ("Łódź", "lodz"),
        ("Mühlbach", "muhlbach"),
        ("東京ラーメン", "東京ラーメン"),
        ("が", "が"),  # kana keep their dakuten
        ("St. Anna's-Platz", "st anna s platz"),
        ("  ", ""),
    ],
)
def test_normalize_text(raw: str, expected: str) -> None:
    assert normalize_text(raw) == expected


def test_latin_letter_detection() -> None:
    assert has_latin_letters("Café") and has_latin_letters("東京 Ramen")
    assert not has_latin_letters("東京ラーメン") and not has_latin_letters("123")


def test_stable_uuid_is_deterministic_and_namespaced() -> None:
    a = stable_uuid("place", "r/osm/node/1")
    assert a == stable_uuid("place", "r/osm/node/1")
    assert a != stable_uuid("place", "r/osm/node/2")
    assert a != stable_uuid("admin_area", "r/osm/node/1")
    assert a.version == 8


def _counters(attractions: int, att_named: int, named_latin: int | None = None) -> Counters:
    from detour_api.importer.report import KindStats

    c = Counters()
    latin = att_named if named_latin is None else named_latin
    c.kinds["attraction"] = KindStats(total=attractions, named=att_named, named_latin=latin)
    return c


def test_gates_pass_at_the_adr_009_thresholds() -> None:
    # gates 1 to 3 (restaurants) were retired by ADR 026; the numbers 4 to 6 are kept
    gates = evaluate_gates(_counters(12000, 5000), GEO_SIZE_LIMIT_BYTES)
    assert [g.number for g in gates] == [4, 5, 6]
    assert all(g.passed for g in gates)


@pytest.mark.parametrize(
    ("counters", "size", "failing"),
    [
        (_counters(12000, 4999), 0, {4}),
        (_counters(12502, 5000), 0, {4}),  # 39.99 % named
        (_counters(12000, 5000), GEO_SIZE_LIMIT_BYTES + 1, {6}),
        (_counters(0, 0), 0, {4, 5}),  # unknown never passes
    ],
)
def test_each_gate_can_fail_on_its_own(counters: Counters, size: int, failing: set[int]) -> None:
    gates = evaluate_gates(counters, size)
    assert {g.number for g in gates if not g.passed} == failing


def test_exactly_at_a_threshold_passes() -> None:
    # 12,500 attractions of which 5,000 are named: exactly 40 %
    gates = evaluate_gates(_counters(12500, 5000), 0)
    assert all(g.passed for g in gates)
    assert pct(4499, 5000) == 90.0  # the display rounds; the gate does not


def test_japan_like_names_fail_gate_5_while_no_display_rule_exists() -> None:
    gates = evaluate_gates(_counters(30000, 25000, named_latin=5000), 0)
    assert [g.number for g in gates if not g.passed] == [5]


def test_poly_file_becomes_a_multipolygon_with_holes() -> None:
    text = """austria
1
   10.0  47.0
   11.0  47.0
   11.0  48.0
   10.0  48.0
END
!2
   10.2  47.2
   10.4  47.2
   10.4  47.4
   10.2  47.4
END
END
"""
    wkt = poly_to_wkt(text)
    assert wkt.startswith("MULTIPOLYGON(((10.0 47.0")
    assert wkt.count("(10.0 47.0") == 1 and "(10.2 47.2" in wkt
    with pytest.raises(ValueError):
        poly_to_wkt("empty\nEND\n")


def test_download_sends_an_identifying_user_agent_and_hashes_the_file(tmp_path: Path) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["ua"] = request.headers["user-agent"]
        return httpx.Response(
            200, content=b"abc", headers={"Last-Modified": "Tue, 10 Nov 2026 12:00:00 GMT"}
        )

    result = pipeline.download(
        "https://example.invalid/x.pbf",
        tmp_path / "x.pbf",
        transport=httpx.MockTransport(handler),
    )
    assert "Detour-import" in seen["ua"] and "github.com/sandiaes/Detour" in seen["ua"]
    assert result.size == 3
    assert result.sha256 == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert str(result.last_modified) == "2026-11-10"


def test_download_fails_clearly_after_retries(tmp_path: Path) -> None:
    calls = {"n": 0}
    waits: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503)

    with pytest.raises(pipeline.DownloadError, match="could not download"):
        pipeline.download(
            "https://example.invalid/x",
            tmp_path / "x",
            transport=httpx.MockTransport(handler),
            sleep=waits.append,
        )
    assert calls["n"] == 5
    assert waits == [5.0, 10.0, 20.0, 40.0]  # backs off, no wait after the last attempt


def test_pg_env_keeps_passwords_out_of_command_lines() -> None:
    env = pipeline.pg_env("postgresql+psycopg://u:p%40ss@db.example:6000/name?sslmode=require")
    assert (env["PGUSER"], env["PGPASSWORD"], env["PGHOST"], env["PGPORT"]) == (
        "u",
        "p@ss",
        "db.example",
        "6000",
    )
    assert env["PGDATABASE"] == "name" and env["PGSSLMODE"] == "require"


def test_session_mode_is_required_for_the_target() -> None:
    from detour_api.importer.cli import require_session_mode

    require_session_mode("postgresql://u:p@aws-0.pooler.supabase.com:5432/postgres")
    with pytest.raises(SystemExit, match="session-mode"):
        require_session_mode("postgresql://u:p@aws-0.pooler.supabase.com:6543/postgres")


def test_geonames_layouts_are_checked_not_assumed() -> None:
    with pytest.raises(gazetteer.GazetteerError, match="19"):
        list(gazetteer.parse_cities(["1\tonly\tthree"], {"AT"}))
    with pytest.raises(gazetteer.GazetteerError, match="header"):
        gazetteer.parse_country_info("AT\tAUT\n")
    with pytest.raises(gazetteer.GazetteerError, match="lacks columns"):
        gazetteer.parse_country_info("#ISO\tISO3\tCountry\nAT\tAUT\tTestland\n")
    with pytest.raises(gazetteer.GazetteerError, match=r"3 columns"):
        list(gazetteer.parse_code_file("AT.01\tonly\tthree\n", {"AT"}))


def test_alternate_names_are_distinct_short_first_and_capped() -> None:
    alts = ",".join([f"Name{i:03d}" for i in range(100)] + ["Testburg", "TESTBURG", "Éx"])
    picked = gazetteer.pick_alt_names("Testburg", alts)
    assert picked is not None and len(picked) == gazetteer.ALT_NAMES_CAP
    assert picked[0] == "Éx" and "Testburg" not in picked  # the name itself is not an alternate


def test_english_name_is_searchable_only_when_it_differs() -> None:
    tags = {
        "tourism": "museum",
        "name": "Festung Hohensalzburg",
        "name:en": "Hohensalzburg Fortress",
    }
    decision = decide(tags)
    assert isinstance(decision, Decision)
    place = build_place("r", "N", 1, decision, tags, 13.0, 47.8)
    assert place.name_en_norm == "hohensalzburg fortress"
    same = {"tourism": "museum", "name": "Café Test", "name:en": "Cafe  test"}
    decision = decide(same)
    assert isinstance(decision, Decision)
    assert build_place("r", "N", 2, decision, same, 13.0, 47.8).name_en_norm is None


def test_gate_4_asks_less_of_a_city_or_a_state_than_of_a_country() -> None:
    """Paris (Ile-de-France) had 4,212 named attractions and was held back by the country figure
    of 5,000 on 2026-11-19; a part region needs 1,000."""
    paris = _counters(4212, 4212)
    assert {g.number for g in evaluate_gates(paris, 0, "country") if not g.passed} == {4}
    assert all(g.passed for g in evaluate_gates(paris, 0, "part"))
    assert all(g.passed for g in evaluate_gates(_counters(1000, 1000), 0, "part"))
    below = evaluate_gates(_counters(999, 999), 0, "part")
    assert {g.number for g in below if not g.passed} == {4}
    # the other checks do not change with the scope
    named_pct = evaluate_gates(_counters(4000, 1000), 0, "part")
    assert {g.number for g in named_pct if not g.passed} == {4}


def test_a_failed_download_ends_the_import_with_a_code_the_workflow_can_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from detour_api.importer import cli

    def fail(*_a: object, **_k: object) -> None:
        raise pipeline.DownloadError("could not download https://example.invalid/x: ConnectError")

    monkeypatch.setattr(cli, "run_region_import", fail)
    monkeypatch.setenv("DETOUR_IMPORT_DATABASE_URL", "postgresql://u:p@db.example:5432/postgres")
    monkeypatch.setenv("DETOUR_STAGING_DATABASE_URL", "postgresql://u:p@localhost:5432/postgres")
    assert cli.main(["region", "denmark", "--work-dir", str(tmp_path / "w")]) == 75


def test_a_404_is_not_retried_and_says_the_address_is_wrong(tmp_path: Path) -> None:
    """A wrong catalog address (Greater London, 2026-11-19) answered 404: five attempts and three
    whole imports on other machines could never help."""
    calls = {"n": 0}
    waits: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(404)

    with pytest.raises(pipeline.DownloadError, match="HTTP 404") as raised:
        pipeline.download(
            "https://example.invalid/x",
            tmp_path / "x",
            transport=httpx.MockTransport(handler),
            sleep=waits.append,
        )
    assert raised.value.retryable is False
    assert calls["n"] == 1 and waits == []


@pytest.mark.parametrize(
    ("status", "retryable"), [(502, True), (503, True), (408, True), (429, True)]
)
def test_a_server_side_or_busy_answer_is_still_retried(
    tmp_path: Path, status: int, retryable: bool
) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(status)

    with pytest.raises(pipeline.DownloadError) as raised:
        pipeline.download(
            "https://example.invalid/x",
            tmp_path / "x",
            transport=httpx.MockTransport(handler),
            sleep=lambda _s: None,
        )
    assert raised.value.retryable is retryable and calls["n"] == 5


def test_a_missing_file_ends_the_import_with_its_own_exit_code(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from detour_api.importer import cli

    def missing(*_a: object, **_k: object) -> None:
        raise pipeline.DownloadError("could not download https://x/y: HTTP 404", retryable=False)

    monkeypatch.setattr(cli, "run_region_import", missing)
    monkeypatch.setenv("DETOUR_IMPORT_DATABASE_URL", "postgresql://u:p@db.example:5432/postgres")
    monkeypatch.setenv("DETOUR_STAGING_DATABASE_URL", "postgresql://u:p@localhost:5432/postgres")
    assert cli.main(["region", "denmark", "--work-dir", str(tmp_path / "w")]) == 76


def test_the_catalog_addresses_that_were_checked_against_geofabrik() -> None:
    """Read on Geofabrik's pages on 2026-11-19 (no network here): the United Kingdom, not Great
    Britain, holds England and Greater London; France's regions sit under europe/france."""
    from detour_api.importer.regions import REGIONS

    london = REGIONS["greater-london"]
    assert london.extract_url == (
        "https://download.geofabrik.de/europe/united-kingdom/england/greater-london/"
        "greater-london-latest.osm.pbf"
    )
    assert london.poly_url.endswith("/england/greater-london/greater-london.poly")
    assert REGIONS["bordeaux"].extract_url.endswith("/europe/france/aquitaine-latest.osm.pbf")
    assert REGIONS["paris"].extract_url.endswith("/europe/france/ile-de-france-latest.osm.pbf")
    assert all("great-britain" not in r.geofabrik_path for r in REGIONS.values())
