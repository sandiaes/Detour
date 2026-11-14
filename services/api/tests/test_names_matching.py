"""Matching places to Wikidata items (ADR 025) and the adapter's name questions.

The Wikidata answers below are written in the documented ``wbgetentities``/``wbgetclaims``/search
shapes (https://www.wikidata.org/w/api.php?action=help&modules=wbgetentities); they are not
recordings: Wikidata answered 429 to this development environment's shared address.
"""

from typing import Any

import httpx
import pytest
from sqlalchemy import create_engine

from detour_api.adapters import wikimedia
from detour_api.adapters.wikimedia import (
    WikimediaClient,
    parse_entity_names,
    parse_iso_code,
    parse_match_facts,
    parse_search_titles,
    parse_sitelink_items,
)
from detour_api.names.matching import Subject, WikidataCandidate, choose, distance_m, judge
from detour_api.settings import Settings

SALZBURG = Subject(47.7949, 13.0475, "AT", 1, "landmark", "Festung Hohensalzburg")


def cand(qid: str, **over: Any) -> WikidataCandidate:
    base: dict[str, Any] = {
        "qid": qid,
        "lat": 47.7950,
        "lon": 13.0476,
        "country_iso2": "AT",
        "city_id": 1,
        "instance_of": frozenset({"Q57821"}),
        "names": ("Hohensalzburg Fortress", "Festung Hohensalzburg"),
    }
    base.update(over)
    return WikidataCandidate(**base)


def test_a_candidate_that_meets_every_rule_matches() -> None:
    qid, verdicts = choose(SALZBURG, [cand("Q1")])
    assert qid == "Q1" and verdicts[0].accepted
    assert verdicts[0].distance_m is not None and verdicts[0].distance_m < 20


def test_the_same_name_in_another_country_is_not_matched() -> None:
    # "Hohensalzburg" does not exist twice, but "Schlossberg" does in every German-speaking country.
    subject = Subject(47.0763, 15.4377, "AT", 7, "landmark", "Schlossberg")
    other = cand("Q2", lat=47.0764, lon=15.4378, country_iso2="DE", names=("Schlossberg",))
    v = judge(subject, other)
    assert not v.accepted and "other_country" in v.reasons


def test_duplicate_names_far_apart_are_not_matched() -> None:
    subject = Subject(48.2085, 16.3721, "AT", 1, "landmark", "Stephansdom")
    far = cand("Q3", lat=48.30, lon=16.40, names=("Stephansdom",))
    assert "too_far" in judge(subject, far).reasons


def test_nearby_places_with_similar_names_are_not_matched() -> None:
    near_but_other = cand("Q4", names=("Hohensalzburg Funicular", "Festungsbahn"))
    v = judge(SALZBURG, near_but_other)
    assert not v.accepted and v.reasons == ("name_differs",)


def test_two_matching_candidates_are_ambiguous() -> None:
    qid, verdicts = choose(SALZBURG, [cand("Q5"), cand("Q6")])
    assert qid is None and sum(v.accepted for v in verdicts) == 2


def test_other_city_unknown_country_and_non_places_are_refused() -> None:
    assert "other_city" in judge(SALZBURG, cand("Q7", city_id=2)).reasons
    assert "country_unknown" in judge(SALZBURG, cand("Q8", country_iso2=None)).reasons
    assert "not_a_place" in judge(SALZBURG, cand("Q9", instance_of=frozenset({"Q5"}))).reasons
    assert "no_coordinates" in judge(SALZBURG, cand("Q10", lat=None, lon=None)).reasons


def test_names_match_after_accent_and_ascii_folding_only() -> None:
    subject = Subject(47.80, 13.04, "AT", 1, "natural", "Mönchsberg")
    assert judge(subject, cand("Q11", lat=47.80, lon=13.04, names=("Moenchsberg",))).accepted
    assert not judge(
        subject, cand("Q12", lat=47.80, lon=13.04, names=("Mönchsberg Lift",))
    ).accepted


def test_distance_is_great_circle() -> None:
    assert distance_m(0, 0, 0, 1) == pytest.approx(111_195, rel=1e-3)


# -- parsing Wikidata's answers --------------------------------------------------------------------

NAMES_ANSWER = {
    "entities": {
        "Q233413": {
            "type": "item",
            "id": "Q233413",
            "labels": {
                "en": {"language": "en", "value": "Himeji Castle"},
                "ja": {"language": "ja", "value": "姫路城"},
            },
            "aliases": {
                "en": [{"language": "en", "value": "White Heron Castle"}],
                "ja": [{"language": "ja", "value": "白鷺城"}],
            },
            "sitelinks": {"enwiki": {"site": "enwiki", "title": "Himeji Castle", "badges": []}},
        },
        "Q99": {"id": "Q99", "missing": ""},
        "Q100": {"type": "item", "id": "Q101", "labels": {}, "aliases": {}, "sitelinks": {}},
    }
}


def test_entity_names_read_labels_aliases_and_the_english_article() -> None:
    names = parse_entity_names(NAMES_ANSWER)
    himeji = names["Q233413"]
    assert himeji.labels == {"en": "Himeji Castle", "ja": "姫路城"}
    assert himeji.aliases == {"en": ["White Heron Castle"], "ja": ["白鷺城"]}
    assert himeji.enwiki == "Himeji Castle"
    assert "Q99" not in names
    assert names["Q100"].qid == "Q101" and names["Q101"].enwiki is None  # a redirect, both ways


def test_sitelink_lookup_search_claims_and_iso_code() -> None:
    sitelinks = {
        "entities": {
            "Q694": {
                "id": "Q694",
                "sitelinks": {"dewiki": {"site": "dewiki", "title": "Festung Hohensalzburg"}},
            },
            "-1": {"site": "dewiki", "title": "Nichts", "missing": ""},
        }
    }
    assert parse_sitelink_items(sitelinks) == {"Festung Hohensalzburg": "Q694"}
    search = {"query": {"search": [{"title": "Q694"}, {"title": "Property:P1"}, {"title": "Q5"}]}}
    assert parse_search_titles(search) == ["Q694", "Q5"]
    claims = {
        "entities": {
            "Q694": {
                "labels": {"de": {"value": "Festung Hohensalzburg"}},
                "aliases": {"en": [{"value": "Hohensalzburg"}]},
                "claims": {
                    "P625": [
                        {
                            "mainsnak": {
                                "datavalue": {"value": {"latitude": 47.795, "longitude": 13.0477}}
                            },
                            "rank": "normal",
                        }
                    ],
                    "P17": [
                        {"mainsnak": {"datavalue": {"value": {"id": "Q40"}}}, "rank": "normal"}
                    ],
                    "P31": [
                        {"mainsnak": {"datavalue": {"value": {"id": "Q57821"}}}, "rank": "normal"},
                        {"mainsnak": {"datavalue": {"value": {"id": "Q5"}}}, "rank": "deprecated"},
                    ],
                },
            }
        }
    }
    facts = parse_match_facts(claims)["Q694"]
    assert (facts.lat, facts.lon, facts.country_qid) == (47.795, 13.0477, "Q40")
    assert facts.instance_of == frozenset({"Q57821"})  # the deprecated statement is ignored
    assert facts.names == ("Festung Hohensalzburg", "Hohensalzburg")
    iso = {"claims": {"P297": [{"mainsnak": {"datavalue": {"value": "at"}}, "rank": "normal"}]}}
    assert parse_iso_code(iso) == "AT"
    with pytest.raises(ValueError):
        parse_entity_names({"error": {}})


@pytest.fixture
def no_budget_counter(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    calls: list[int] = []

    def reserve(*args: Any) -> bool:
        calls.append(1)
        return True

    monkeypatch.setattr(wikimedia, "reserve_call", reserve)
    return calls


def test_entity_names_is_one_small_request(no_budget_counter: list[int]) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=NAMES_ANSWER)

    client = WikimediaClient(
        Settings(environment="test"),
        create_engine("postgresql+psycopg://x@localhost/none"),
        httpx.MockTransport(handler),
        sleep=lambda s: None,
    )
    client.entity_names([f"Q{n}" for n in range(1, 80)], ["en", "mul", "ja", "en"])
    [request] = seen
    params = request.url.params
    assert params["props"] == "labels|aliases|sitelinks"
    assert params["sitefilter"] == "enwiki"  # only the English sitelink comes back
    assert params["languages"] == "en|ja|mul"
    assert params["ids"].count("|") == 49 and params["maxlag"] == "30"
    assert request.headers["user-agent"].startswith("Detour-bot/")
