"""One sight, one candidate: the same-named copies that OpenStreetMap maps twice collapse."""

from detour_api.planner.dedupe import collapse_duplicates
from detour_api.planner.types import Candidate


def cand(pid: str, name: str, lat: float, lon: float, **kw: object) -> Candidate:
    return Candidate(place_id=pid, name=name, category="artwork", lat=lat, lon=lon, **kw)  # type: ignore[arg-type]


def test_same_name_close_together_is_one_sight() -> None:
    a = cand("b", "Beyond Recall", 47.8000, 13.0400)
    b = cand("a", "Beyond  Recall", 47.8001, 13.0401)  # a few metres away, spacing differs
    assert [c.place_id for c in collapse_duplicates([a, b])] == ["a"]


def test_better_documented_copy_wins() -> None:
    plain = cand("a", "Dom", 47.8, 13.04)
    linked = cand("z", "Dom", 47.8, 13.0401, signals={"has_wikidata": True})
    assert [c.place_id for c in collapse_duplicates([plain, linked])] == ["z"]


def test_same_name_far_apart_stays_two_sights() -> None:
    a = cand("a", "Kirche", 47.80, 13.04)
    b = cand("b", "Kirche", 47.85, 13.10)
    assert [c.place_id for c in collapse_duplicates([a, b])] == ["a", "b"]


def test_different_names_are_untouched_and_order_is_stable() -> None:
    items = [cand("c", "A", 1, 1), cand("a", "B", 1, 1), cand("b", "C", 1, 1)]
    assert [c.place_id for c in collapse_duplicates(items)] == ["a", "b", "c"]
    assert collapse_duplicates(items) == collapse_duplicates(list(reversed(items)))
