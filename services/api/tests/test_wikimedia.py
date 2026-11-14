"""The Wikimedia adapter and the photo processing (ADR 022), against recorded responses.

``wikidata-wbgetentities-3.json`` and ``commons-imageinfo-3.json`` are real answers recorded on
2026-11-14 (trimmed to what the adapter reads). No test reaches the network: the transport is a
stub, the budget counter is replaced, and the clock never sleeps.
"""

import io
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest
from PIL import Image
from sqlalchemy import create_engine

from detour_api.adapters import wikimedia
from detour_api.adapters.wikimedia import (
    IMAGE_HOSTS,
    FileInfo,
    WikimediaBudgetExhausted,
    WikimediaClient,
    WikimediaError,
    check_image_url,
    licence_allowed,
    parse_entities,
    parse_imageinfo,
    rejection_reason,
    strip_html,
)
from detour_api.images.process import UndecodableImage, process_image
from detour_api.settings import Settings

FIXTURES = Path(__file__).parent / "fixtures"
ENTITIES = json.loads((FIXTURES / "wikidata-wbgetentities-3.json").read_text())
IMAGEINFO = json.loads((FIXTURES / "commons-imageinfo-3.json").read_text())


def _info(**changes: Any) -> FileInfo:
    base = FileInfo(
        file="A.jpg",
        thumb_url="https://thumb.wikimedia.org/x/1280px-A.jpg",
        original_url="https://upload.wikimedia.org/x/A.jpg",
        description_url="https://commons.wikimedia.org/wiki/File:A.jpg",
        width=4000,
        height=3000,
        mime="image/jpeg",
        licence="CC BY-SA 4.0",
        licence_url="https://creativecommons.org/licenses/by-sa/4.0",
        author="A. Photographer",
    )
    return replace(base, **changes)


# -- parsing -----------------------------------------------------------------------------------


def test_entities_give_the_image_file_and_the_number_of_sitelinks() -> None:
    found = parse_entities(ENTITIES)
    assert set(found) == {"Q101514119", "Q102203720", "Q105646502"}
    assert found["Q101514119"].file == "Retz - Stadtmauer.JPG"
    assert found["Q101514119"].sitelinks == 2
    assert found["Q105646502"].sitelinks == 0


def test_entities_skip_missing_items_and_prefer_the_preferred_image() -> None:
    payload = {
        "entities": {
            "Q1": {"id": "Q1", "missing": ""},
            "Q2": {
                "claims": {
                    "P18": [
                        {"rank": "normal", "mainsnak": {"datavalue": {"value": "Old.jpg"}}},
                        {"rank": "deprecated", "mainsnak": {"datavalue": {"value": "Bad.jpg"}}},
                        {"rank": "preferred", "mainsnak": {"datavalue": {"value": "Best.jpg"}}},
                    ]
                }
            },
            "Q3": {"claims": {}},
            "bogus": {"claims": {}},
        }
    }
    found = parse_entities(payload)
    assert set(found) == {"Q2", "Q3"}
    assert found["Q2"].file == "Best.jpg"
    assert found["Q3"].file is None
    with pytest.raises(ValueError, match="wbgetentities"):
        parse_entities({"error": {"code": "x"}})


def test_imageinfo_gives_licence_author_size_and_a_thumbnail_url() -> None:
    infos = parse_imageinfo(IMAGEINFO)
    assert len(infos) == 3
    retz = infos["Retz - Stadtmauer.JPG"]
    assert (retz.width, retz.height, retz.mime) == (3803, 2446, "image/jpeg")
    assert retz.licence == "CC BY-SA 4.0"
    assert retz.licence_url == "https://creativecommons.org/licenses/by-sa/4.0"
    assert retz.author == "C.Stadler/Bwag"  # the link's markup is gone, the name stays
    assert retz.thumb_url and retz.thumb_url.startswith("https://thumb.wikimedia.org/")
    assert retz.description_url == "https://commons.wikimedia.org/wiki/File:Retz_-_Stadtmauer.JPG"
    assert all(rejection_reason(i) is None for i in infos.values())
    with pytest.raises(ValueError, match="imageinfo"):
        parse_imageinfo({"nothing": 1})


def test_a_title_commons_normalised_is_found_under_both_spellings() -> None:
    page = {
        "title": "File:My photo.jpg",
        "imageinfo": [
            {
                "width": 2000,
                "height": 1000,
                "mime": "image/jpeg",
                "descriptionurl": "https://commons.wikimedia.org/wiki/File:My_photo.jpg",
                "extmetadata": {},
            }
        ],
    }
    payload = {
        "query": {
            "normalized": [{"from": "File:My_photo.jpg", "to": "File:My photo.jpg"}],
            "pages": {"1": page},
        }
    }
    infos = parse_imageinfo(payload)
    assert set(infos) == {"My photo.jpg", "My_photo.jpg"}


def test_author_html_is_reduced_to_text() -> None:
    raw = '<bdi><a href="x" title="t">Jane &amp; John</a></bdi>\n  (cropped)'
    assert strip_html(raw) == "Jane & John (cropped)"
    assert len(strip_html("x" * 500)) == 300


# -- the licence allow-list and the quality gate ------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "CC0",
        "CC0 1.0",
        "Public domain",
        "CC BY 3.0",
        "CC BY-SA 4.0",
        "CC BY-SA 3.0 at",
        "cc by-sa 2.5",
    ],
)
def test_allowed_licences(name: str) -> None:
    assert licence_allowed(name)


@pytest.mark.parametrize(
    "name",
    [
        None,
        "",
        "CC BY-NC 4.0",
        "CC BY-ND 2.0",
        "CC BY-NC-SA 3.0",
        "GFDL",
        "Fair use",
        "Copyrighted free use",
    ],
)
def test_rejected_licences(name: str | None) -> None:
    assert not licence_allowed(name)


def test_the_quality_gate_names_the_first_reason() -> None:
    assert rejection_reason(_info()) is None
    assert rejection_reason(_info(mime="image/svg+xml")) == wikimedia.REASON_NOT_PHOTO
    assert rejection_reason(_info(mime="image/png")) is None
    assert rejection_reason(_info(width=1199, height=800)) == wikimedia.REASON_TOO_SMALL
    assert rejection_reason(_info(width=1500, height=1500)) == wikimedia.REASON_NOT_LANDSCAPE
    assert rejection_reason(_info(width=1500, height=2000)) == wikimedia.REASON_NOT_LANDSCAPE
    assert rejection_reason(_info(licence="CC BY-NC 4.0")) == wikimedia.REASON_LICENCE
    assert rejection_reason(_info(author=None)) == wikimedia.REASON_NO_AUTHOR


def test_images_come_only_from_wikimedia_image_hosts() -> None:
    for host in IMAGE_HOSTS:
        assert check_image_url(f"https://{host}/a.jpg")
    for bad in (
        "http://upload.wikimedia.org/a.jpg",
        "https://evil.example/a.jpg",
        "https://upload.wikimedia.org.evil.example/a.jpg",
        "file:///etc/passwd",
    ):
        with pytest.raises(WikimediaError):
            check_image_url(bad)


# -- the stored rendition ----------------------------------------------------------------------


def _jpeg(width: int, height: int, colour: tuple[int, int, int] = (200, 30, 30)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(out, format="JPEG")
    return out.getvalue()


def test_the_rendition_is_a_small_progressive_jpeg_with_its_average_colour() -> None:
    result = process_image(_jpeg(3000, 2000), max_side=1080, quality=75)
    assert (result.width, result.height) == (1080, 720)
    assert len(result.data) < 150_000
    with Image.open(io.BytesIO(result.data)) as stored:
        assert stored.format == "JPEG"
        assert stored.info.get("progressive") == 1
    red, green, blue = (int(result.color[i : i + 2], 16) for i in (1, 3, 5))
    assert red > 150 and green < 80 and blue < 80


def test_a_png_is_accepted_and_other_formats_or_junk_are_not() -> None:
    png = io.BytesIO()
    Image.new("RGBA", (1400, 900), (10, 10, 10, 255)).save(png, format="PNG")
    assert process_image(png.getvalue(), max_side=1080, quality=75).width == 1080
    gif = io.BytesIO()
    Image.new("P", (40, 40)).save(gif, format="GIF")
    for junk in (gif.getvalue(), b"not an image", b""):
        with pytest.raises(UndecodableImage):
            process_image(junk, max_side=1080, quality=75)


# -- the client: politeness ---------------------------------------------------------------------


@pytest.fixture
def no_budget_counter(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    calls: list[int] = []

    def reserve(engine: Any, provider: str, budget: int) -> bool:
        calls.append(budget)
        return budget > 0 and len(calls) <= budget

    monkeypatch.setattr(wikimedia, "reserve_call", reserve)
    return calls


class _Clock:
    """A fake clock: sleeping advances it, so pacing is observable without waiting."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(round(seconds, 3))
        self.now += seconds

    def __call__(self) -> float:
        return self.now


def _client(handler: Any, clock: _Clock, **settings: Any) -> WikimediaClient:
    engine = create_engine("postgresql+psycopg://x@localhost/none")
    return WikimediaClient(
        Settings(environment="test", **settings),
        engine,
        httpx.MockTransport(handler),
        sleep=clock.sleep,
        clock=clock,
    )


def test_it_is_off_in_tests_unless_a_transport_is_injected() -> None:
    engine = create_engine("postgresql+psycopg://x@localhost/none")
    assert WikimediaClient(Settings(environment="test"), engine).enabled is False
    assert WikimediaClient(Settings(environment="local"), None).enabled is False
    with pytest.raises(WikimediaError, match="disabled"):
        WikimediaClient(Settings(environment="test"), engine).entities(["Q1"])


def test_requests_carry_a_descriptive_user_agent_maxlag_and_one_batch(
    no_budget_counter: list[int],
) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=ENTITIES)

    client = _client(handler, _Clock())
    qids = [f"Q{n}" for n in range(1, 80)]
    client.entities(qids)
    assert len(seen) == 1  # one request, however many ids were asked (capped at 50)
    request = seen[0]
    agent = request.headers["user-agent"]
    assert agent.startswith("Detour-bot/") and "github.com/sandiaes/Detour" in agent
    assert "httpx/" in agent and "@" not in agent  # contact is a URL, never a personal email
    assert request.url.params["maxlag"] == "30"
    assert request.url.params["ids"].count("|") == 49
    assert request.url.params["action"] == "wbgetentities"


def test_requests_are_paced_one_at_a_time(no_budget_counter: list[int]) -> None:
    clock = _Clock()
    client = _client(lambda r: httpx.Response(200, json=ENTITIES), clock)
    client.entities(["Q1"])
    client.entities(["Q2"])
    client.entities(["Q3"])
    assert clock.sleeps == [1.0, 1.0]  # the first needs no wait; then the minimum interval


def test_retry_after_is_obeyed_on_429_and_503(no_budget_counter: list[int]) -> None:
    answers = [
        httpx.Response(429, headers={"Retry-After": "7"}),
        httpx.Response(503),  # no header: five seconds
        httpx.Response(200, json=ENTITIES),
    ]
    clock = _Clock()
    client = _client(lambda r: answers.pop(0), clock)
    assert "Q101514119" in client.entities(["Q101514119"])
    assert 7.0 in clock.sleeps
    assert 10.0 in clock.sleeps  # attempt 1 without a header: 5 s doubled once
    assert client.requests_made == 3


def test_it_gives_up_after_repeated_429s(no_budget_counter: list[int]) -> None:
    client = _client(lambda r: httpx.Response(429, headers={"Retry-After": "1"}), _Clock())
    with pytest.raises(WikimediaError, match="rate limited"):
        client.entities(["Q1"])
    assert client.requests_made == wikimedia.MAX_ATTEMPTS


def test_a_lagged_server_is_waited_for(no_budget_counter: list[int]) -> None:
    lagged = httpx.Response(200, json={"error": {"code": "maxlag"}}, headers={"Retry-After": "30"})
    answers = [lagged, httpx.Response(200, json=ENTITIES)]
    clock = _Clock()
    client = _client(lambda r: answers.pop(0), clock)
    client.entities(["Q1"])
    assert 30.0 in clock.sleeps  # the server's own figure is obeyed


def test_a_server_lagged_for_long_is_waited_for_then_reported_with_its_lag(
    no_budget_counter: list[int],
) -> None:
    lagged = {"error": {"code": "maxlag", "lag": 23.5, "host": "db1"}}
    clock = _Clock()
    client = _client(lambda r: httpx.Response(200, json=lagged), clock)
    with pytest.raises(WikimediaError, match=r"lagged \(last reported lag 23.5 s, limit 30 s\)"):
        client.entities(["Q1"])
    assert client.requests_made == wikimedia.MAXLAG_ATTEMPTS
    waits = [w for w in clock.sleeps if w >= 5.0]
    assert waits[:5] == [5.0, 10.0, 20.0, 40.0, 60.0]  # doubling, capped at a minute
    assert max(waits) == 60.0


def test_other_errors_and_bad_answers_raise(no_budget_counter: list[int]) -> None:
    for response in (
        httpx.Response(404),
        httpx.Response(200, text="<html>"),
        httpx.Response(200, json={"error": {"code": "badid"}}),
    ):
        client = _client(lambda r, resp=response: resp, _Clock())
        with pytest.raises(WikimediaError):
            client.entities(["Q1"])

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("slow", request=request)

    with pytest.raises(WikimediaError, match="ConnectTimeout"):
        _client(boom, _Clock()).entities(["Q1"])


def test_the_daily_budget_stops_requests(no_budget_counter: list[int]) -> None:
    client = _client(
        lambda r: httpx.Response(200, json=ENTITIES), _Clock(), wikimedia_daily_budget=0
    )
    with pytest.raises(WikimediaBudgetExhausted):
        client.entities(["Q1"])
    assert client.requests_made == 0


def test_a_city_is_matched_only_when_exactly_one_item_has_its_geonames_id(
    no_budget_counter: list[int],
) -> None:
    seen: list[httpx.Request] = []

    def answer(titles: list[str]) -> Any:
        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json={"query": {"search": [{"title": t} for t in titles]}})

        return handler

    assert _client(answer(["Q34713"]), _Clock()).city_item(2766824) == "Q34713"
    assert seen[0].url.params["srsearch"] == "haswbstatement:P1566=2766824"
    assert _client(answer([]), _Clock()).city_item(1) is None
    assert _client(answer(["Q1", "Q2"]), _Clock()).city_item(1) is None


def test_downloads_are_limited_in_host_and_size(no_budget_counter: list[int]) -> None:
    client = _client(
        lambda r: httpx.Response(200, content=b"x" * 2000),
        _Clock(),
        wikimedia_max_download_bytes=100_000,
    )
    assert client.download("https://thumb.wikimedia.org/a.jpg") == b"x" * 2000
    with pytest.raises(WikimediaError, match="image host"):
        client.download("https://example.org/a.jpg")
    big = _client(
        lambda r: httpx.Response(200, content=b"x" * 200_000),
        _Clock(),
        wikimedia_max_download_bytes=100_000,
    )
    with pytest.raises(WikimediaError, match="larger"):
        big.download("https://upload.wikimedia.org/a.jpg")
    redirect = _client(
        lambda r: httpx.Response(302, headers={"Location": "https://evil.example/x"}), _Clock()
    )
    with pytest.raises(WikimediaError, match="HTTP 302"):
        redirect.download("https://upload.wikimedia.org/a.jpg")
