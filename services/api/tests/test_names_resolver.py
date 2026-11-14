"""The multilingual name resolver (ADR 025): hierarchy, place classes, scripts, transliteration,
conflicts and overrides. Pure functions: no database, no network."""

from typing import Any

import pytest
from structlog.testing import capture_logs

from detour_api.names import config
from detour_api.names.records import (
    NameRecord,
    geonames_records,
    osm_records,
    override_record,
    stored_record,
    wikidata_records,
)
from detour_api.names.resolver import resolve
from detour_api.names.scripts import detect_script, is_mixed, parse_tag_language
from detour_api.names.search import fold_ascii, place_alias_norm, search_forms
from detour_api.names.translit import transliterate


def osm(name: str | None, i18n: dict[str, str] | None = None, **tags: Any) -> list[NameRecord]:
    return osm_records(name, i18n, {k.replace("__", ":"): v for k, v in tags.items()})


def wd(
    qid: str, en: str | None = None, enwiki: str | None = None, **labels: str
) -> list[NameRecord]:
    all_labels = dict(labels)
    if en:
        all_labels["en"] = en
    return wikidata_records(qid, all_labels, {}, enwiki)


# -- the hierarchy, by language and script ------------------------------------------------------


def test_japanese_place_with_an_english_wikidata_label() -> None:
    r = resolve(wd("Q1", en="Himeji Castle", ja="姫路城") + osm("姫路城", {"ja": "姫路城"}))
    assert (r.display, r.local, r.step) == ("Himeji Castle", "姫路城", "wikidata_label_en")
    assert r.local_lang == "ja" and r.local_script == "Hani"
    assert not r.generated and r.confidence == pytest.approx(0.98)


def test_japanese_place_with_only_an_english_wikipedia_title() -> None:
    r = resolve(wd("Q2", enwiki="Kiyomizu-dera") + osm("清水寺", {"ja": "清水寺"}))
    assert (r.display, r.local, r.step, r.source) == (
        "Kiyomizu-dera",
        "清水寺",
        "enwiki_title",
        "enwiki",
    )


def test_a_wikipedia_title_loses_its_qualifier_but_keeps_it_as_an_alias() -> None:
    r = resolve(wd("Q3", enwiki="Mercury (planet)") + osm("Merkur"))
    assert r.display == "Mercury" and "Mercury (planet)" in r.aliases


def test_japanese_kanji_without_a_verified_reading_stays_original() -> None:
    r = resolve(osm("姫路城", {"ja": "姫路城"}))
    assert (r.display, r.local, r.display_type, r.generated) == ("姫路城", None, "original", False)
    assert transliterate("姫路城", "ja") is None


def test_japanese_with_a_romanization_from_the_source() -> None:
    r = resolve(osm("姫路城", {"ja": "姫路城", "ja-Latn": "Himejijō"}))
    assert (r.display, r.local, r.display_type) == ("Himejijō", "姫路城", "official_romanization")
    assert not r.generated  # the source gave it: not labelled as automatic


def test_japanese_kana_only_is_transliterated_and_labelled() -> None:
    r = resolve(osm("ひめじ", {"ja": "ひめじ"}))
    assert (r.display, r.local, r.generated) == ("Himeji", "ひめじ", True)
    assert r.display_type == "automatic_transliteration" and r.step == "transliteration_specific"


def test_chinese_official_pinyin() -> None:
    r = resolve(osm("故宫", {"zh": "故宫", "zh-Latn-pinyin": "Gùgōng"}))
    assert (r.display, r.local, r.display_type) == ("Gùgōng", "故宫", "official_romanization")
    # An established English name wins over the Pinyin.
    r = resolve(wd("Q4", en="Forbidden City") + osm("故宫", {"zh": "故宫", "zh_pinyin": "Gùgōng"}))
    assert r.display == "Forbidden City" and "Gùgōng" in r.aliases


def test_chinese_hanzi_is_never_transliterated() -> None:
    r = resolve(osm("天坛", {"zh": "天坛"}))
    assert r.display == "天坛" and not r.generated


def test_korean_official_romanization_beats_transliteration() -> None:
    r = resolve(osm("경복궁", {"ko": "경복궁", "ko_rm": "Gyeongbokgung"}))
    assert (r.display, r.display_type, r.generated) == (
        "Gyeongbokgung",
        "official_romanization",
        False,
    )
    # Without one, Revised Romanization is made and labelled.
    r = resolve(osm("경복궁", {"ko": "경복궁"}))
    assert (r.display, r.generated, r.local) == ("Gyeongbokgung", True, "경복궁")


def test_thai_place_with_an_established_english_name() -> None:
    r = resolve(wd("Q5", en="Grand Palace") + osm("พระบรมมหาราชวัง", {"th": "พระบรมมหาราชวัง"}))
    assert (r.display, r.local) == ("Grand Palace", "พระบรมมหาราชวัง")


def test_thai_romanization_from_the_source_is_used_and_thai_is_never_transliterated() -> None:
    r = resolve(osm("วัดพระแก้ว", {"th": "วัดพระแก้ว", "th-Latn": "Wat Phra Kaeo"}))
    assert (r.display, r.local) == ("Wat Phra Kaeo", "วัดพระแก้ว")
    r = resolve(osm("วัดพระแก้ว", {"th": "วัดพระแก้ว"}))
    assert (r.display, r.generated) == ("วัดพระแก้ว", False)


@pytest.mark.parametrize(
    ("name", "lang", "english"),
    [("قصر الحمراء", "ar", "Alhambra"), ("بادشاہی مسجد", "ur", "Badshahi Mosque")],
)
def test_arabic_and_urdu_names(name: str, lang: str, english: str) -> None:
    r = resolve(wd("Q6", en=english) + osm(name, {lang: name}))
    assert (r.display, r.local, r.local_script) == (english, name, "Arab")
    # Without an English name the original is shown; the abjad is never guessed at.
    r = resolve(osm(name, {lang: name}))
    assert (r.display, r.generated) == (name, False)


def test_hindi_and_greek_names() -> None:
    r = resolve(wd("Q7", en="Qutb Minar") + osm("क़ुतुब मीनार", {"hi": "क़ुतुब मीनार"}))
    assert (r.display, r.local) == ("Qutb Minar", "क़ुतुब मीनार")
    r = resolve(
        wd("Q8", en="Acropolis of Athens") + osm("Ακρόπολη Αθηνών", {"el": "Ακρόπολη Αθηνών"})
    )
    assert (r.display, r.local) == ("Acropolis of Athens", "Ακρόπολη Αθηνών")
    # Greek without an English name: ELOT 743, language-specific, labelled.
    r = resolve(osm("Θεσσαλονίκη", {"el": "Θεσσαλονίκη"}))
    assert (r.display, r.step, r.generated) == ("Thessaloniki", "transliteration_specific", True)


@pytest.mark.parametrize(
    ("name", "lang", "expected", "step"),
    [
        ("Красная площадь", "ru", "Krasnaya ploshchad", "transliteration_specific"),
        ("Київ", "uk", "Kyiv", "transliteration_specific"),
        ("Запоріжжя", "uk", "Zaporizhzhia", "transliteration_specific"),
        ("София", "bg", "Sofia", "transliteration_specific"),
        ("Београд", "sr", "Beograd", "transliteration_specific"),
        # Cyrillic of unknown language: the generic table, the last resort.
        ("Москва", None, "Moskva", "transliteration_generic"),
    ],
)
def test_cyrillic_names(name: str, lang: str | None, expected: str, step: str) -> None:
    r = resolve(osm(name, {lang: name} if lang else None))
    assert (r.display, r.step, r.generated, r.local) == (expected, step, True, name)


def test_cyrillic_with_an_english_name_is_not_transliterated() -> None:
    r = resolve(wd("Q9", en="Red Square") + osm("Красная площадь", {"ru": "Красная площадь"}))
    assert (r.display, r.generated) == ("Red Square", False)


def test_german_attraction_with_an_established_english_name() -> None:
    i18n = {"de": "Festung Hohensalzburg", "en": "Hohensalzburg Fortress"}
    r = resolve(osm("Festung Hohensalzburg", i18n))
    assert (r.display, r.local, r.step) == (
        "Hohensalzburg Fortress",
        "Festung Hohensalzburg",
        "osm_name_en",
    )
    r = resolve(
        wd("Q10", en="Schönbrunn Palace") + osm("Schloss Schönbrunn", {"de": "Schloss Schönbrunn"})
    )
    assert (r.display, r.local) == ("Schönbrunn Palace", "Schloss Schönbrunn")


def test_a_place_known_by_its_original_name_has_no_second_line() -> None:
    r = resolve(wd("Q11", en="Kunsthistorisches Museum") + osm("Kunsthistorisches Museum"))
    assert (r.display, r.local) == ("Kunsthistorisches Museum", None)


def test_spanish_and_portuguese_attractions_with_an_established_english_name() -> None:
    r = resolve(
        wd("Q12", en="Museo del Prado")
        + osm("Museo Nacional del Prado", {"es": "Museo Nacional del Prado"})
    )
    assert (r.display, r.local) == ("Museo del Prado", "Museo Nacional del Prado")
    r = resolve(wd("Q13", en="Belém Tower") + osm("Torre de Belém", {"pt": "Torre de Belém"}))
    assert (r.display, r.local) == ("Belém Tower", "Torre de Belém")


def test_german_restaurant_keeps_its_name() -> None:
    # A mapper's name:en for a business is a translation: never shown.
    r = resolve(
        osm("Gasthaus Zum Wilden Mann", {"en": "Inn of the Wild Man"}),
        place_class=config.place_class("restaurant", "restaurant"),
    )
    assert (r.display, r.local) == ("Gasthaus Zum Wilden Mann", None)
    assert "Inn of the Wild Man" in r.aliases  # still found by search


def test_business_name_is_not_translated_even_with_wikidata() -> None:
    cls = config.place_class("restaurant", "restaurant")
    r = resolve(
        wd("Q14", en="Casa do Alentejo restaurant") + osm("Restaurante Casa do Alentejo"),
        place_class=cls,
    )
    assert r.display == "Restaurante Casa do Alentejo"
    # Nor transliterated or romanized.
    r = resolve(
        osm("東京ラーメン", {"ja": "東京ラーメン", "ja-Latn": "Tokyo Ramen"}), place_class=cls
    )
    assert (r.display, r.generated) == ("東京ラーメン", False)


def test_business_with_an_official_english_or_international_name() -> None:
    cls = "business"
    r = resolve(
        osm("Stiftskulinarium St. Peter", official_name__en="St. Peter Abbey Restaurant"),
        place_class=cls,
    )
    assert r.display == "St. Peter Abbey Restaurant" and r.display_type == "official_english"
    r = resolve(osm("สตาร์บัคส์", {"th": "สตาร์บัคส์"}, brand__en="Starbucks"), place_class=cls)
    assert (r.display, r.display_type, r.local) == ("Starbucks", "localized_brand", "สตาร์บัคส์")
    r = resolve(osm("Café Москва", {"int": "Cafe Moskva"}), place_class=cls)
    assert r.display == "Cafe Moskva"


def test_official_city_exonym() -> None:
    for local, lang, en in (
        ("München", "de", "Munich"),
        ("Firenze", "it", "Florence"),
        ("Wien", "de", "Vienna"),
    ):
        records = wikidata_records("Q15", {"en": en, lang: local}, {}, None, native_lang=lang)
        r = resolve(records + geonames_records(en, en, 1), place_class="settlement")
        assert (r.display, r.local, r.local_lang) == (en, local, lang)


def test_a_city_without_wikidata_shows_its_gazetteer_name() -> None:
    r = resolve(geonames_records("Hallstatt", "Hallstatt", 2), place_class="settlement")
    assert (r.display, r.local) == ("Hallstatt", None)


def test_openstreetmap_name_en_fallback() -> None:
    r = resolve(osm("Stift Melk", {"de": "Stift Melk", "en": "Melk Abbey"}))
    assert (r.display, r.step) == ("Melk Abbey", "osm_name_en")
    assert r.confidence == pytest.approx(0.93)


def test_openstreetmap_int_name_fallback_only_in_latin_letters() -> None:
    r = resolve(osm("Καστέλλι", {"el": "Καστέλλι", "int": "Kastelli"}))
    assert (r.display, r.step) == ("Kastelli", "osm_int_name")
    # int_name in another script is not taken as an international (English-facing) name.
    r = resolve(osm("Kastelli", {"int": "Καστέλλι"}))
    assert r.display == "Kastelli" and r.step == "original"


def test_official_and_short_english_names() -> None:
    r = resolve(
        osm("Hofburg", official_name__en="Hofburg Imperial Palace", short_name__en="The Hofburg")
    )
    assert r.display == "Hofburg Imperial Palace"
    r = resolve(osm("Stephansdom", short_name__en="St. Stephen's"))
    assert (r.display, r.step) == ("St. Stephen's", "osm_short_name_en")


def test_generic_transliteration_is_the_last_resort() -> None:
    r = resolve(osm("თბილისი"))
    assert (r.display, r.step, r.generated) == ("Tbilisi", "transliteration_generic", True)
    assert r.confidence == pytest.approx(0.35)
    # Anything a source gives beats it.
    r = resolve(osm("თბილისი", {"int": "Tbilisi Old Town"}))
    assert (r.display, r.generated) == ("Tbilisi Old Town", False)


def test_mixed_script_names() -> None:
    # Latin with a safe script: the Latin part passes through.
    r = resolve(osm("Café Москва", {"ru": "Café Москва"}))
    assert (r.display, r.generated) == ("Café Moskva", True)
    # Latin with an unsafe script: nothing is made.
    r = resolve(osm("Café 東京"))
    assert (r.display, r.generated) == ("Café 東京", False)
    assert is_mixed("Café 東京") and not is_mixed("東京タワー")
    assert detect_script("東京タワー") == "Jpan" and detect_script("서울 大學") == "Kore"


def test_accented_latin_characters_are_kept_for_display_and_folded_for_search() -> None:
    r = resolve(osm("Mönchsberg", {"de": "Mönchsberg"}))
    assert (r.display, r.local, r.generated) == ("Mönchsberg", None, False)
    assert search_forms("Mönchsberg") == ["monchsberg", "moenchsberg"]
    assert search_forms("Großglockner") == ["grossglockner"]
    assert fold_ascii("Ærø") == "Aeroe"


def test_no_reliable_english_name_shows_the_original() -> None:
    r = resolve(osm("Feldkapelle Oberndorf", {"de": "Feldkapelle Oberndorf"}))
    assert (r.display, r.display_type, r.local, r.generated) == (
        "Feldkapelle Oberndorf",
        "original",
        None,
        False,
    )


def test_an_unnamed_place_has_no_display_name() -> None:
    r = resolve(osm(None))
    assert r.display is None


# -- overrides, conflicts, machine translation ---------------------------------------------------


def test_user_override_takes_precedence_and_keeps_the_original() -> None:
    records = [
        override_record("Salzburg Castle"),
        *wd("Q16", en="Hohensalzburg Fortress"),
        *osm("Festung Hohensalzburg", {"de": "Festung Hohensalzburg"}),
    ]
    r = resolve(records)
    assert (r.display, r.local, r.user_override, r.confidence) == (
        "Salzburg Castle",
        "Festung Hohensalzburg",
        True,
        1.0,
    )
    # Even for a business.
    r = resolve([override_record("My café"), *osm("Café Sacher")], place_class="business")
    assert r.display == "My café"


def test_conflicting_high_confidence_names_keep_the_priority_and_log() -> None:
    records = wd("Q17", en="Hohensalzburg Castle") + osm(
        "Festung Hohensalzburg", {"en": "Hohensalzburg Fortress"}
    )
    with capture_logs() as logs:
        r = resolve(records, place_ref="p1")
    assert r.display == "Hohensalzburg Castle"  # Wikidata label before OSM name:en
    assert r.conflicts == ("Hohensalzburg Fortress",)
    assert "Hohensalzburg Fortress" in r.aliases
    assert any(e["event"] == "place_name_conflict" and e["place"] == "p1" for e in logs)


def test_a_name_the_provider_marks_official_wins_a_conflict() -> None:
    official = stored_record(
        {
            "name": "Official Fortress Name",
            "lang": "en",
            "name_type": "official_english",
            "source": "provider",
            "step": "provider_official_en",
            "official": True,
        }
    )
    r = resolve([*wd("Q18", en="Hohensalzburg Castle"), official, *osm("Festung Hohensalzburg")])
    assert r.display == "Official Fortress Name" and r.display_type == "official_english"


def test_machine_translation_is_never_used_by_default() -> None:
    mt = stored_record(
        {
            "name": "Fortress High Salzburg",
            "lang": "en",
            "name_type": "machine_translation",
            "source": "provider",
            "step": "machine_translation",
        }
    )
    r = resolve([mt, *osm("Festung Hohensalzburg")])
    assert r.display == "Festung Hohensalzburg"
    assert config.ALLOW_MACHINE_TRANSLATION is False


def test_a_generated_name_is_never_labelled_official() -> None:
    r = resolve(osm("Київ", {"uk": "Київ"}))
    assert r.generated and r.display_type == "automatic_transliteration"
    assert r.display_type not in ("official_english", "official_romanization")


def test_confidence_values_are_centralised() -> None:
    expected = {
        "user_override": 1.00,
        "provider_official_en": 0.99,
        "wikidata_label_en": 0.98,
        "enwiki_title": 0.97,
        "osm_name_en": 0.93,
        "osm_official_name_en": 0.85,
        "osm_int_name": 0.85,
        "provider_romanization": 0.85,
        "transliteration_specific": 0.70,
        "machine_translation": 0.50,
        "transliteration_generic": 0.35,
    }
    assert {k: config.STEP_BY_KEY[k].confidence for k in expected} == expected
    assert [s.key for s in config.STEPS][-1] == "original"


# -- the model and its helpers --------------------------------------------------------------------


def test_records_are_deduplicated_by_language_source_and_normalised_value() -> None:
    records = osm("Wien", {"de": "Wien", "en": "Vienna"}, alt_name="WIEN;Wien")
    assert sum(r.name_norm == "wien" for r in records) == 1


def test_osm_language_suffixes_are_read_as_bcp47() -> None:
    assert parse_tag_language("ja-Latn") == ("ja", "Latn", True)
    assert parse_tag_language("ja_rm") == ("ja", "Latn", True)
    assert parse_tag_language("zh-Latn-pinyin") == ("zh", "Latn", True)
    assert parse_tag_language("zh_pinyin") == ("zh", "Latn", True)
    assert parse_tag_language("de") == ("de", None, False)
    assert parse_tag_language("int") is None


def test_search_aliases_cover_every_written_form() -> None:
    aliases = place_alias_norm(
        "경복궁",
        {"ko": "경복궁", "en": "Gyeongbokgung Palace", "ja": "景福宮"},
        None,
        "gyeongbokgung palace",
    )
    assert aliases is not None
    forms = aliases.split("|")
    assert "gyeongbokgung" in forms  # the made romanization, for search only
    assert "景福宮" in forms
    assert "gyeongbokgung palace" not in forms  # already in name_en_norm
    assert place_alias_norm("Mönchsberg", None, None) == "moenchsberg"
