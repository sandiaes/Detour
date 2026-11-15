"""The planning engine without a database: golden files, determinism, trip lengths, incomplete
data, impossible requests, routed times, meals, area destinations and latency.

The candidates are synthetic (``tests/fixtures/planner/make_candidates.py``): invented places, so
the expected output can be fixed. Rewrite the golden files after an intended change with
``pytest tests/test_planner_engine.py --update-golden`` and review the diff.
"""

import dataclasses
import itertools
import json
import time
from collections.abc import Sequence
from datetime import date
from typing import Any

import pytest

from detour_api.planner import engine, scoring
from detour_api.planner.config import DEFAULT_CONFIG, PlannerConfig
from detour_api.planner.durations import DEFAULT_VISIT_MINUTES, visit_minutes
from detour_api.planner.reasons import ISSUE_TEMPLATES, issue_text, item_text, note_text
from detour_api.planner.sequencer import HeuristicSequencer, SequencingProblem
from detour_api.planner.travel import FixedTravelSource, ServiceTravelSource, TravelLookup
from detour_api.planner.types import Candidate, Generation, PlanningImpossible
from detour_api.planner.validator import validate_generation, validate_plan
from detour_api.settings import Settings
from detour_api.travel.estimate import estimate
from detour_api.travel.types import Coord, Mode, distance_m
from tests.conftest import TEST_SECRET
from tests.planner_helpers import (
    GOLDEN,
    candidates,
    request,
    route_request,
    towns,
)

GOLDEN_CASES = [
    ("city3", "city-large", 3, date(2026, 5, 4)),
    ("city7", "city-large", 7, None),
    ("city14", "city-large", 14, date(2026, 7, 1)),
    ("sparse1", "city-sparse", 1, None),
    ("sparse3", "city-sparse", 3, date(2026, 5, 4)),
    ("area3", "area", 3, None),
    ("area7", "area", 7, date(2026, 6, 1)),
    ("area14", "area", 14, None),
]


# Multi-city trips over the synthetic area's towns (ADR 024): driven legs, and a stop in a country
# travelled by rail (JP) whose legs have no time.
ROUTE_CASES = [
    ("route2", [(990001, 2, "AT"), (990002, 2, "AT")], date(2026, 5, 4)),
    ("route3", [(990001, 2, "AT"), (990003, 1, "AT"), (990002, 3, "AT")], None),
    ("route-rail", [(990001, 2, "AT"), (990003, 2, "JP"), (990002, 2, "AT")], None),
]


def run_route(
    stops: Sequence[tuple[int, int, str | None]], start: date | None = None
) -> Generation:
    return engine.generate(
        route_request(stops, start),
        candidates("area"),
        FixedTravelSource(),
    )


def run(name: str, days: int, start: date | None = None, **kw: Any) -> Generation:
    return engine.generate(
        request(name, days, start),
        candidates(name),
        FixedTravelSource(),
        **kw,
    )


def canonical(generation: Generation) -> str:
    return json.dumps(engine.to_json(generation), indent=1, sort_keys=True, ensure_ascii=False)


def assert_valid(generation: Generation, name: str, days: int, start: date | None) -> None:
    """The validator, called again from the test (the engine already calls it)."""
    req = request(name, days, start)
    by_id = {c.place_id: c for c in candidates(name)}
    lookup = TravelLookup(FixedTravelSource(), DEFAULT_CONFIG.walk_max_m)
    for plan in generation.plans:
        for d in plan.days:
            for a, b in zip(d.items, d.items[1:], strict=False):
                lookup.get(Coord.from_degrees(a.lat, a.lon), Coord.from_degrees(b.lat, b.lon))
    for t1 in towns(name):
        for t2 in towns(name):
            lookup.get(t1.coord, t2.coord)
    for plan in generation.plans:
        assert validate_plan(plan, req, by_id, lookup.known(), DEFAULT_CONFIG) == []
    assert validate_generation(generation, DEFAULT_CONFIG) == []


# -- golden files and determinism ----------------------------------------------------------------


@pytest.mark.parametrize(("case", "fixture", "days", "start"), GOLDEN_CASES)
def test_golden_output_is_reproduced(
    request: pytest.FixtureRequest, case: str, fixture: str, days: int, start: date | None
) -> None:
    text = canonical(run(fixture, days, start)) + "\n"
    path = GOLDEN / f"{case}.json"
    if request.config.getoption("--update-golden"):
        path.write_text(text, encoding="utf-8")
    assert path.exists(), f"missing golden file {path.name}: run with --update-golden"
    assert text == path.read_text(encoding="utf-8")


@pytest.mark.parametrize(("case", "stops", "start"), ROUTE_CASES)
def test_route_golden_output_is_reproduced(
    request: pytest.FixtureRequest,
    case: str,
    stops: list[tuple[int, int, str | None]],
    start: date | None,
) -> None:
    text = canonical(run_route(stops, start)) + "\n"
    path = GOLDEN / f"{case}.json"
    if request.config.getoption("--update-golden"):
        path.write_text(text, encoding="utf-8")
    assert path.exists(), f"missing golden file {path.name}: run with --update-golden"
    assert text == path.read_text(encoding="utf-8")


def test_same_input_in_any_order_gives_identical_output() -> None:
    first = canonical(run("city-large", 3))
    again = canonical(run("city-large", 3))
    shuffled = list(reversed(candidates("city-large")))
    third = canonical(
        engine.generate(
            request("city-large", 3),
            shuffled[60:] + shuffled[:60],
            FixedTravelSource(),
        )
    )
    assert first == again == third


def test_versions_and_seed_are_on_every_generation() -> None:
    g = run("city-large", 3)
    assert g.engine_version == "planner-3.0.0"
    assert g.config_version == DEFAULT_CONFIG.version and "durations-" in g.config_version
    assert g.data_version == "run-fixture" and g.seed == 0


# -- trip lengths --------------------------------------------------------------------------------


@pytest.mark.parametrize(("days", "start"), [(3, date(2026, 5, 4)), (7, None), (14, None)])
def test_city_trip_gives_two_distinct_valid_plans(days: int, start: date | None) -> None:
    g = run("city-large", days, start)
    assert_valid(g, "city-large", days, start)
    assert [p.profile for p in g.plans] == ["essentials", "wider"] and g.distinct
    a, b = (p.place_ids() for p in g.plans)
    assert len(a & b) * 5 <= 3 * len(a | b)  # Jaccard <= 0.6
    assert g.jaccard_permille == len(a & b) * 1000 // len(a | b)
    for plan in g.plans:
        assert len(plan.days) == days
        assert all(d.visits for d in plan.days), "a city with 180 sights fills every day"
        if start is not None:
            assert plan.days[0].date == start
        assert plan.days[-1].day_index == days
    essentials = g.plans[0].stats
    assert essentials.travel_share_permille <= 250  # KPI: travel share <= 25 % (Essentials)


@pytest.mark.parametrize("days", [3, 7])
def test_day_utilisation_is_inside_the_kpi_band(days: int) -> None:
    for plan in run("city-large", days).plans:
        assert 600 <= plan.stats.day_utilisation_permille <= 900, plan.profile


def test_essentials_is_more_compact_than_wider() -> None:
    g = run("city-large", 3)
    centre = request("city-large", 3).centre
    by_id = {c.place_id: c for c in candidates("city-large")}

    def mean_distance(ids: frozenset[str]) -> float:
        return sum(scoring.centre_distance(by_id[i], centre) for i in ids) / len(ids)

    essentials, wider = g.plans
    assert mean_distance(essentials.place_ids()) < mean_distance(wider.place_ids())
    assert essentials.stats.travel_share_permille < wider.stats.travel_share_permille
    assert all(scoring.centre_distance(by_id[i], centre) <= 5000 for i in essentials.place_ids())


def test_the_schedule_starts_at_nine_and_ends_by_the_profile_end() -> None:
    for plan in run("city-large", 7).plans:
        end = DEFAULT_CONFIG.profile(plan.profile).day_end_minute
        for day in plan.days:
            assert day.items[0].start_minute == 9 * 60
            assert day.items[-1].end_minute <= end
            for v, nxt in zip(day.items, day.items[1:], strict=False):
                assert v.transfer is not None
                # A visit follows at once, except after the midday gap (ADR 026).
                assert nxt.start_minute >= v.end_minute + v.transfer.minutes


def test_every_visit_is_an_input_candidate_with_its_own_data() -> None:
    by_id = {c.place_id: c for c in candidates("city-large")}
    for plan in run("city-large", 14).plans:
        for day in plan.days:
            for v in day.visits:
                c = by_id[v.place_id]
                assert (v.name, v.lat, v.lon, v.category) == (c.name, c.lat, c.lon, c.category)
                assert v.duration_minutes == visit_minutes(c.category)


def test_every_transfer_is_labelled_and_without_a_provider_estimated() -> None:
    for plan in run("city-large", 3).plans:
        legs = [v.transfer for d in plan.days for v in d.items if v.transfer]
        assert legs and all(x.confidence == "estimated" for x in legs)
        assert all(x.estimate_reason == "provider_not_asked" for x in legs)
        assert plan.stats.estimated_transfers == len(legs)
        assert any(n.code == "ESTIMATED_TRANSFERS" for n in plan.notes)


def test_without_use_provider_the_source_is_never_asked_to_call_out() -> None:
    source = FixedTravelSource()
    engine.generate(request("city-large", 3), candidates("city-large"), source)
    assert source.calls and all(use is False for use, _ in source.calls)


def test_reasons_and_notes_render_through_their_templates() -> None:
    g = run("city-large", 3)
    texts = [
        item_text(code) for p in g.plans for d in p.days for v in d.items for code in v.reasons
    ]
    assert texts and all(t.endswith(".") for t in texts)
    for note in [*g.notes, *(n for p in g.plans for n in p.notes)]:
        assert note_text(note.code, note.params)
    codes = {c for p in g.plans for d in p.days for v in d.visits for c in v.reasons}
    assert {"NEAR_PREVIOUS_ITEM", "WIKIDATA_LINKED", "NEAR_CENTRE", "ADDS_VARIETY"} <= codes
    assert not [m for p in g.plans for d in p.days for m in d.meals]  # ADR 026: sights only
    # The reasons and notes of meals stored before ADR 026 still render.
    for code in ("LUNCH_WINDOW", "DINNER_WINDOW", "VENUE_SUITS_MEAL", "NEW_CUISINE"):
        assert item_text(code)
    assert note_text("MEALS_FROM_MAP_DATA", {})
    assert {n.code for n in g.notes} >= {"DISTINCT_PLANS", "NO_OPENING_HOURS", "SIGHTS_ONLY"}


# -- incomplete place data -------------------------------------------------------------------------


def test_incomplete_data_plans_with_what_is_known_and_invents_nothing() -> None:
    g = run("city-sparse", 1)
    assert_valid(g, "city-sparse", 1, None)
    by_id = {c.place_id: c for c in candidates("city-sparse")}
    visits = [v for p in g.plans for d in p.days for v in d.visits]
    unlisted = [v for v in visits if v.category == "unlisted_category"]
    assert unlisted and all(v.duration_minutes == DEFAULT_VISIT_MINUTES for v in unlisted)
    for v in visits:
        c = by_id[v.place_id]
        # Reasons only from data the place has: no Wikidata reason without the flag, etc.
        assert ("WIKIDATA_LINKED" in v.reasons) == bool(c.signals.get("has_wikidata"))
        assert ("WIKIDATA_SITELINKS" in v.reasons) == ((c.sitelink_count or 0) >= 50)
        if not c.signals:
            assert set(v.reasons) <= {"NAMED_SIGHT", "NEAR_CENTRE", "NEAR_PREVIOUS_ITEM",
                                      "ADDS_VARIETY", "HIGHLIGHT_CATEGORY"}  # fmt: skip


def test_a_destination_too_small_for_two_plans_says_so_and_returns_one() -> None:
    g = run("city-sparse", 3, date(2026, 5, 4))
    assert_valid(g, "city-sparse", 3, date(2026, 5, 4))
    assert len(g.plans) == 1 and not g.distinct and g.jaccard_permille is None
    note = next(n for n in g.notes if n.code == "SINGLE_PLAN")
    assert note.params == {
        "candidates": 8,
        "radius_km": 15,
        "jaccard_percent": 100,
        "max_percent": 60,
    }
    assert note_text(note.code, note.params) == (
        "Only one plan is shown: 8 sights are available within 15 km, too few for two clearly "
        "different plans (overlap 100 %, at most 60 % allowed)."
    )
    # Without meals a 4-hour theme park fits a day with the midday gap: nothing is left out.
    assert g.plans[0].stats.visits == 8
    assert not any(n.code == "VISITS_REMOVED_TO_FIT" for n in g.plans[0].notes)


def test_days_without_visits_are_explained() -> None:
    g = run("city-sparse", 14)
    plan = g.plans[0]
    empty = [d.day_index for d in plan.days if not d.visits]
    assert empty and empty == list(range(len(plan.days) - len(empty) + 1, 15))  # at the end
    note = next(n for n in plan.notes if n.code == "DAYS_WITHOUT_VISITS")
    assert note.params["empty_days"] == len(empty) and note.params["days"] == 14


# -- impossible requests ------------------------------------------------------------------------


def test_no_candidates_explains_exactly_which_constraint() -> None:
    with pytest.raises(PlanningImpossible) as exc:
        engine.generate(request("city-large", 3), [], FixedTravelSource())
    [issue] = exc.value.issues
    assert (issue.code, issue.params) == (
        "NO_CANDIDATES",
        {"radius_km": 15, "destination": "Synthetic City"},
    )
    assert issue_text(issue.code, issue.params) == (
        "There are no named sights within 15 km of Synthetic City in the imported data."
    )


def test_candidates_beyond_every_radius_count_as_none() -> None:
    far = [dataclasses.replace(c, lat=c.lat + 1.0) for c in candidates("city-sparse")]  # ~111 km
    with pytest.raises(PlanningImpossible) as exc:
        engine.generate(request("city-sparse", 2), far, FixedTravelSource())
    assert [i.code for i in exc.value.issues] == ["NO_CANDIDATES"]


def test_visits_longer_than_any_day_are_explained() -> None:
    zoo_only = [dataclasses.replace(c, category="theme_park") for c in candidates("city-sparse")]
    short = dataclasses.replace(
        DEFAULT_CONFIG,
        midday_gap=dataclasses.replace(DEFAULT_CONFIG.midday_gap, minutes=0),
        profiles=tuple(
            dataclasses.replace(
                p, day_end_minute=DEFAULT_CONFIG.day_start_minute + 180, free_minutes=0
            )
            for p in DEFAULT_CONFIG.profiles
        ),
    )
    with pytest.raises(PlanningImpossible) as exc:
        engine.generate(request("city-sparse", 2), zoo_only, FixedTravelSource(), config=short)
    [issue] = exc.value.issues
    assert issue.code == "VISITS_LONGER_THAN_DAY"
    assert issue.params == {"candidates": 8, "destination": "Synthetic City", "day_minutes": 180}
    assert "take longer than the 180 minutes" in issue_text(issue.code, issue.params)
    assert set(ISSUE_TEMPLATES) >= {"NO_CANDIDATES", "VISITS_LONGER_THAN_DAY"}


def test_bad_inputs_are_programming_errors() -> None:
    with pytest.raises(ValueError, match="days"):
        engine.generate(request("city-sparse", 0), candidates("city-sparse"), FixedTravelSource())
    twice = candidates("city-sparse") + candidates("city-sparse")[:1]
    with pytest.raises(ValueError, match="duplicate"):
        engine.generate(request("city-sparse", 1), twice, FixedTravelSource())


# -- routed travel times ------------------------------------------------------------------------


def _slow_routed_table() -> dict[tuple[Coord, Coord], tuple[int, int]]:
    """Synthetic "routed" answers six times slower than the estimate, for pairs within 3 km."""
    cs = candidates("city-large")
    table: dict[tuple[Coord, Coord], tuple[int, int]] = {}
    for a in cs:
        for b in cs:
            if a is b or distance_m(a.coord, b.coord) > 3000:
                continue
            mode: Mode = "walk" if distance_m(a.coord, b.coord) <= 2000 else "drive"
            seconds, meters = estimate(a.coord, b.coord, mode)
            table[(a.coord, b.coord)] = (seconds * 6 + 300, meters * 12 // 10)
    return table


def test_routed_transfers_replace_estimates_and_the_day_still_fits() -> None:
    source = FixedTravelSource(_slow_routed_table(), provider_only=True)
    req = request("city-large", 3)
    g = engine.generate(req, candidates("city-large"), source, use_provider=True)
    uses = [use for use, _ in source.calls]
    # The cache read, the provider call for the planned legs, at most two follow-ups for legs
    # joined by fitting a day.
    assert uses[0] is False and all(uses[1:]) and 2 <= len(uses) <= 4
    for plan in g.plans:
        legs = [v.transfer for d in plan.days for v in d.items if v.transfer]
        routed = [x for x in legs if x.confidence == "routed"]
        # The table has sight-to-sight legs within 3 km only: legs to and from places to eat,
        # and longer ones, stay estimates.
        by_point = {(c.lat, c.lon): c for c in candidates("city-large")}
        for d in plan.days:
            for v, nxt in itertools.pairwise(d.visits):
                if d.items.index(nxt) != d.items.index(v) + 1:
                    continue  # a meal lies between them
                assert v.transfer is not None
                far = (
                    distance_m(by_point[(v.lat, v.lon)].coord, by_point[(nxt.lat, nxt.lon)].coord)
                    > 3000
                )
                assert (v.transfer.confidence == "estimated") == far
            for m in d.meals:
                assert m.transfer is None or m.transfer.confidence == "estimated"
        assert routed and plan.stats.routed_transfers == len(routed)
        for d in plan.days:
            assert d.items[-1].end_minute <= DEFAULT_CONFIG.profile(plan.profile).day_end_minute
    removed = [n for p in g.plans for n in p.notes if n.code == "VISITS_REMOVED_TO_FIT"]
    assert removed, "the slower routed times force visits out of the planned days"


def test_service_source_uses_the_travel_service_and_labels_estimates() -> None:
    from detour_api.adapters.valhalla import ValhallaClient
    from detour_api.travel.service import TravelTimeService

    settings = Settings(environment="test", token_secret=TEST_SECRET)
    service = TravelTimeService(settings, None, ValhallaClient(settings, None))
    source = ServiceTravelSource(service, max_seconds=1.0)
    g = engine.generate(
        request("city-sparse", 1),
        candidates("city-sparse"),
        source,
        use_provider=True,
    )
    legs = [v.transfer for p in g.plans for d in p.days for v in d.items if v.transfer]
    assert legs and {x.estimate_reason for x in legs} == {"adapter_disabled"}


# -- diversity gate ------------------------------------------------------------------------------


def test_the_gate_penalises_shared_visits_until_the_plans_differ() -> None:
    lenient = dataclasses.replace(DEFAULT_CONFIG, max_jaccard_num=1, max_jaccard_den=1)
    g_lenient = run("city-large", 4, config=lenient)
    g = run("city-large", 4)
    a, b = (p.place_ids() for p in g_lenient.plans)
    assert len(a & b) * 5 > 3 * len(a | b), "unpenalised, the profiles overlap too much"
    adjusted = [n for n in g.plans[1].notes if n.code == "DIVERSITY_ADJUSTED"]
    assert adjusted and adjusted[0].params["kept_percent"] in DEFAULT_CONFIG.diversity_rounds_pct
    c, d = (p.place_ids() for p in g.plans)
    assert len(c & d) * 5 <= 3 * len(c | d)
    assert not any(n.code == "DIVERSITY_ADJUSTED" for n in g_lenient.plans[1].notes)


def test_a_much_smaller_second_variant_is_not_an_alternative() -> None:
    g = run("city-sparse", 1)
    assert [p.stats.visits for p in g.plans] == [5, 7]  # Wider has 140 % of Essentials' visits
    demanding = dataclasses.replace(DEFAULT_CONFIG, min_second_variant_pct=200)
    g = run("city-sparse", 1, config=demanding)
    assert len(g.plans) == 1 and any(n.code == "SINGLE_PLAN" for n in g.notes)


def test_without_re_solves_overlapping_plans_fall_back_to_one() -> None:
    no_rounds = dataclasses.replace(DEFAULT_CONFIG, diversity_rounds_pct=())
    g = run("city-sparse", 2, config=no_rounds)
    assert len(g.plans) == 1 and not g.distinct
    assert any(n.code == "SINGLE_PLAN" for n in g.notes)


# -- sequencer and scoring units -------------------------------------------------------------------


def _problem(**over: object) -> SequencingProblem:
    base: dict[str, object] = {
        "ids": ("a", "b", "c", "d"),
        "value": (100, 90, 80, 10),
        "duration": (60, 60, 60, 60),
        # a-b-c on a line 10 minutes apart; d far from everything
        "travel": ((0, 10, 20, 90), (10, 0, 10, 90), (20, 10, 0, 90), (90, 90, 90, 0)),
        "days": 1,
        "day_minutes": 240,
        "travel_weight": 1,
    }
    base.update(over)
    return SequencingProblem(**base)  # type: ignore[arg-type]


def test_sequencer_orders_along_the_line_and_drops_what_does_not_pay() -> None:
    routes = HeuristicSequencer().solve(_problem())
    assert routes in ([[0, 1, 2]], [[2, 1, 0]])


def test_sequencer_respects_the_day_length_and_skips_overlong_visits() -> None:
    routes = HeuristicSequencer().solve(_problem(day_minutes=130, duration=(60, 60, 60, 500)))
    assert len(routes[0]) == 2 and 3 not in routes[0]
    total = 120 + sum(
        _problem().travel[a][b] for a, b in zip(routes[0], routes[0][1:], strict=False)
    )
    assert total <= 130


def test_sequencer_spreads_over_days_and_is_repeatable() -> None:
    p = _problem(days=2, day_minutes=130)
    first = HeuristicSequencer().solve(p)
    # Two of a, b, c fit in one day; the third alone in the other; d (90 minutes away) fits
    # nowhere next to them.
    assert sorted(len(r) for r in first) == [1, 2] and 3 not in first[0] + first[1]
    assert all(HeuristicSequencer().solve(p) == first for _ in range(3))


def test_scoring_is_integer_deterministic_and_cut_at_the_radius() -> None:
    cs = candidates("city-large")
    centre = request("city-large", 1).centre
    profile = DEFAULT_CONFIG.profile("essentials")
    scored = scoring.score(cs, centre, profile, DEFAULT_CONFIG, 1000)
    assert all(isinstance(s.value, int) and s.value > 0 for s in scored)
    assert all(s.distance_m <= profile.radius_m for s in scored)
    assert scored == scoring.score(list(reversed(cs)), centre, profile, DEFAULT_CONFIG, 1000)
    keys = [(-s.value, s.candidate.place_id) for s in scored]
    assert keys == sorted(keys)


def test_scoring_repeat_category_and_sitelinks() -> None:
    config = PlannerConfig()
    twin = Candidate("p1", "One", "church", 48.2082, 16.3738, {"has_wikidata": True})
    twin2 = dataclasses.replace(twin, place_id="p2", name="Two")
    famous = dataclasses.replace(twin, place_id="p3", category="museum", sitelink_count=80)
    centre = twin.coord
    wider = config.profile("wider")
    values = {
        s.candidate.place_id: s.value
        for s in scoring.score([twin, twin2, famous], centre, wider, config, 10)
    }
    assert values["p1"] == (10 + 30 + 15) * 10  # base + wikidata + church, full value at centre
    assert values["p2"] == values["p1"] * 60 // 100  # second church keeps 60 % in Wider
    assert values["p3"] == (10 + 30 + 30 + 30) * 10  # + museum + sitelinks >= 50


def test_mode_rule_and_routed_answers_win_over_estimates() -> None:
    a, b = candidates("city-large")[:2]
    lookup = TravelLookup(FixedTravelSource({(a.coord, b.coord): (123, 456)}), 2000)
    assert lookup.get(a.coord, b.coord).confidence == "estimated"  # not fetched yet
    lookup.fetch([(a.coord, b.coord)], use_provider=False)
    assert (lookup.get(a.coord, b.coord).seconds, lookup.get(a.coord, b.coord).confidence) == (
        123,
        "routed",
    )
    lookup.fetch([(a.coord, b.coord)], use_provider=True)  # already routed: not asked again
    expected = "walk" if distance_m(a.coord, b.coord) <= 2000 else "drive"
    assert lookup.mode(a.coord, b.coord) == expected


# -- latency (KPI: two variants of a trip up to 7 days within 5 s, the whole request) -------------


def test_engine_latency_leaves_room_in_the_kpi_budget() -> None:
    """The engine's share: the request also reads the database and may wait up to
    ``planner_provider_max_seconds`` (3 s) on the routing provider, so the engine gets 1.5 s on
    a CI runner (measured about 0.2 s for 7 days on a 4-CPU cloud container)."""
    started = time.perf_counter()
    g = run("city-large", 7)
    elapsed = time.perf_counter() - started
    assert len(g.plans) == 2
    assert elapsed < 1.5, f"engine took {elapsed:.2f} s for 7 days"


def test_generated_plans_hold_sights_only_with_one_midday_gap() -> None:
    """ADR 026: no meals and no places to eat; a day keeps one unplanned stretch around midday."""
    gap = DEFAULT_CONFIG.midday_gap
    assert (gap.earliest_start, gap.latest_start, gap.minutes) == (12 * 60 + 30, 14 * 60, 90)
    assert DEFAULT_CONFIG.day_window_end_minute == 20 * 60
    for profile in DEFAULT_CONFIG.profiles:
        assert profile.day_end_minute == 20 * 60
    assert [DEFAULT_CONFIG.visit_budget(p) for p in DEFAULT_CONFIG.profiles] == [450, 405]
    g = run("city-large", 3)
    gaps = 0
    for plan in g.plans:
        assert plan.stats.meals == 0 and plan.stats.meal_minutes == 0
        assert any(n.code == "SIGHTS_ONLY" for n in g.notes)
        for day in plan.days:
            assert all(i.kind == "visit" for i in day.items)
            for a, b in itertools.pairwise(day.items):
                assert a.transfer is not None
                idle = b.start_minute - (a.end_minute + a.transfer.minutes)
                if idle:
                    gaps += 1
                    assert idle >= gap.minutes and b.start_minute >= gap.earliest_start + idle
    assert gaps, "a day with sights before and after midday has its gap"


# -- multi-city trips (ADR 024) -----------------------------------------------------------------


def test_a_route_keeps_the_users_stops_order_and_days() -> None:
    stops = [(990003, 1, "AT"), (990001, 2, "AT"), (990002, 1, "AT")]
    generation = run_route(stops)
    assert generation.distinct
    for plan in generation.plans:
        assert [d.base_city_id for d in plan.days] == [990003, 990001, 990001, 990002]
        assert [d.arrival is not None for d in plan.days] == [False, True, False, True]
        assert not any(d.arrival_unknown for d in plan.days)


def test_a_city_that_comes_back_is_planned_without_repeating_a_visit() -> None:
    generation = run_route([(990001, 1, "AT"), (990005, 1, "AT"), (990001, 1, "AT")])
    for plan in generation.plans:
        ids = [i.place_id for d in plan.days for i in d.items if i.kind == "visit"]
        assert len(ids) == len(set(ids))
        assert plan.days[2].visits, "the second stay still has sights"


def test_a_leg_into_a_rail_country_has_no_time_and_its_day_is_planned_in_full() -> None:
    generation = run_route([(990001, 1, "AT"), (990003, 1, "JP")])
    for plan in generation.plans:
        day = plan.days[1]
        assert day.arrival is None and day.arrival_unknown
        assert day.items[0].start_minute == DEFAULT_CONFIG.day_start_minute
        notes = [n for n in plan.notes if n.code == "ARRIVAL_TIME_UNKNOWN"]
        assert notes and notes[0].params["to_name"] == "Synthetic Town C"
        assert plan.stats.intercity_legs == 0  # nothing invented, nothing counted


def test_the_validator_refuses_a_route_out_of_order_or_with_an_invented_rail_time() -> None:
    from dataclasses import replace

    req = route_request([(990001, 1, "AT"), (990003, 1, "JP")])
    generation = run_route([(990001, 1, "AT"), (990003, 1, "JP")])
    plan = generation.plans[0]
    by_id = {c.place_id: c for c in candidates("area")}
    swapped = replace(plan, days=(replace(plan.days[0], base_city_id=990003), *plan.days[1:]))
    codes = {v.code for v in validate_plan(swapped, req, by_id, {}, DEFAULT_CONFIG)}
    assert "ROUTE_ORDER" in codes
    known = replace(plan, days=(plan.days[0], replace(plan.days[1], arrival_unknown=False)))
    codes = {v.code for v in validate_plan(known, req, by_id, {}, DEFAULT_CONFIG)}
    assert "ARRIVAL_MISMATCH" in codes
    driven = route_request([(990001, 1, "AT"), (990003, 1, "AT")])
    codes = {v.code for v in validate_plan(plan, driven, by_id, {}, DEFAULT_CONFIG)}
    assert "UNKNOWN_LEG_MISMATCH" in codes


def test_a_stay_makes_each_day_start_there_and_the_plan_stays_valid() -> None:
    from detour_api.planner.types import StayPoint

    base = request("city-large", 3, None)
    plain = engine.generate(base, candidates("city-large"), FixedTravelSource())
    # The traveller sleeps at the far edge of the first place the plan visits on day 1.
    first = plain.plans[0].days[0].items[0]
    stay = Coord.from_degrees(first.lat + 0.01, first.lon + 0.01)
    with_stay = dataclasses.replace(base, stays=(StayPoint(1, 3, stay),))
    got = engine.generate(with_stay, candidates("city-large"), FixedTravelSource())
    assert validate_generation(got, DEFAULT_CONFIG) == []
    for plan in got.plans:
        for day in plan.days:
            if day.items:
                # The first visit starts after the walk or drive from the stay, never before 09:00.
                assert day.items[0].start_minute >= DEFAULT_CONFIG.day_start_minute
    # Same input, same output: stays keep the engine deterministic.
    again = engine.generate(with_stay, candidates("city-large"), FixedTravelSource())
    assert canonical(got) == canonical(again)


def test_the_sequencer_counts_the_leg_from_the_stay() -> None:
    # Two far-apart nodes and one day: the stay is next to node 1, so it must be the first visit.
    travel = ((0, 30), (30, 0))
    problem = SequencingProblem(
        ids=("a", "b"),
        value=(100, 100),
        duration=(60, 60),
        travel=travel,
        days=1,
        day_minutes=400,
        travel_weight=1,
        start_travel=((40, 1),),
    )
    assert HeuristicSequencer().solve(problem) == [[1, 0]]
