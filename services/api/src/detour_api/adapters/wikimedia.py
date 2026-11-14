"""Wikidata and Wikimedia Commons adapter for reference photos (ADR 022).

Only the backend calls it, only from the image resolver (never during plan generation, never from
a test: tests inject a recorded-response transport). It provides what architecture section 6
requires of every provider:

* an identifying User-Agent of the form the Wikimedia User-Agent policy asks for
  (``Detour-bot/<version> (+<url>) httpx/<version>``; read 2026-11-14, ADR 022),
* a timeout,
* a daily call budget in ``app.provider_usage``, reserved before every request,
* pacing: one request at a time, at least ``wikimedia_min_interval_seconds`` apart (the rate-limit
  page allows 3 concurrent requests and 200 a minute for an identified client),
* batching with ``|`` (up to 50 titles or items per request), ``maxlag`` on every API request,
  ``Retry-After`` obeyed on 429 and 503 (otherwise a pause of at least five seconds, doubling),
* a fallback: a failure raises :class:`WikimediaError`; the resolver records nothing for the item
  and the app keeps its illustration.

Everything that reads Wikimedia's answers is a pure function so it is tested against recorded
responses (``tests/fixtures/wikidata-wbgetentities-3.json``, ``commons-imageinfo-3.json``).
"""

import html
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx
import structlog
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from detour_api.adapters.budget import reserve_call
from detour_api.settings import Settings

log = structlog.get_logger("detour.wikimedia")

PROVIDER = "wikimedia"
BATCH_SIZE = 50
MAX_ATTEMPTS = 4
# A lagged server (maxlag) is waited for longer than a rate limit: Wikidata's lag can last minutes.
MAXLAG_ATTEMPTS = 10
MAXLAG_MIN_PAUSE_SECONDS = 5.0
MAXLAG_MAX_PAUSE_SECONDS = 60.0
DEFAULT_RETRY_SECONDS = 5.0
MAX_RETRY_SECONDS = 120.0
# The hosts an image may be downloaded from. The URL comes from the Commons API's own answer;
# anything else is refused instead of fetched.
IMAGE_HOSTS = frozenset({"upload.wikimedia.org", "thumb.wikimedia.org"})

# Licences that may be shown (ADR 022, decision 2): CC0, public domain, CC BY and CC BY-SA, with
# the version and an optional jurisdiction suffix Commons adds ("CC BY-SA 3.0 at"). Anything else
# (non-commercial, no-derivatives, GFDL, unknown) is rejected.
_LICENCE_OK = re.compile(
    r"^(?:CC0(?: 1\.0)?|Public domain|CC BY(?:-SA)? [0-9]\.[0-9](?: [a-z]{2,3})?)$", re.IGNORECASE
)
_TAG = re.compile(r"<[^>]*>")
_QID = re.compile(r"^Q[0-9]+$")

# Fixed vocabulary of reasons a photo is not used (stored in ``geo.image_lookup.reason``).
REASON_NO_ITEM = "no_wikidata_item"
REASON_NO_IMAGE = "no_image_property"
REASON_CITY_NO_MATCH = "no_item_for_geonames_id"
REASON_CITY_AMBIGUOUS = "several_items_for_geonames_id"
REASON_NOT_PHOTO = "not_a_jpeg_or_png"
REASON_TOO_SMALL = "too_small"
REASON_NOT_LANDSCAPE = "not_landscape"
REASON_LICENCE = "licence_not_allowed"
REASON_NO_AUTHOR = "no_author"
REASON_NO_FILE_INFO = "no_file_info"
REASON_UNDECODABLE = "could_not_decode"

MIN_ORIGINAL_WIDTH = 1200


class WikimediaError(Exception):
    """Wikimedia could not be asked or answered unusably; the caller leaves the item for later."""


class WikimediaBudgetExhausted(WikimediaError):
    pass


@dataclass(frozen=True)
class EntityImage:
    qid: str
    files: tuple[str, ...]  # image candidates, best first, without "File:" (P18, then P948)
    sitelinks: int

    @property
    def file(self) -> str | None:
        return self.files[0] if self.files else None


@dataclass(frozen=True)
class FileInfo:
    file: str
    thumb_url: str | None
    original_url: str | None
    description_url: str
    width: int
    height: int
    mime: str
    licence: str | None
    licence_url: str | None
    author: str | None


def strip_html(value: str, limit: int = 300) -> str:
    """Commons returns the author as HTML (often a link). Keep the words, drop the markup."""
    text = html.unescape(_TAG.sub("", value))
    return " ".join(text.split())[:limit].strip()


def licence_allowed(short_name: str | None) -> bool:
    return short_name is not None and _LICENCE_OK.match(short_name.strip()) is not None


def parse_entities(payload: Any) -> dict[str, EntityImage]:
    """Read ``wbgetentities`` (claims and sitelinks). A missing item or image is not an error."""
    entities = payload.get("entities") if isinstance(payload, dict) else None
    if not isinstance(entities, dict):
        raise ValueError("not a wbgetentities answer")
    found: dict[str, EntityImage] = {}
    for qid, entity in entities.items():
        if not isinstance(entity, dict) or not _QID.match(str(qid)) or "missing" in entity:
            continue
        claims = entity.get("claims")
        claims = claims if isinstance(claims, dict) else {}
        # The item's image (P18) first, then its page banner (P948): a city often has only a banner.
        files = list(
            dict.fromkeys(_ranked_files(claims.get("P18")) + _ranked_files(claims.get("P948")))
        )
        sitelinks = entity.get("sitelinks")
        found[qid] = EntityImage(
            qid=qid,
            files=tuple(files),
            sitelinks=len(sitelinks) if isinstance(sitelinks, dict) else 0,
        )
    return found


def _ranked_files(statements: Any) -> list[str]:
    """File names of the non-deprecated statements, preferred rank first, then statement order."""
    if not isinstance(statements, list):
        return []
    ranked: list[tuple[int, int, str]] = []
    for index, statement in enumerate(statements):
        if not isinstance(statement, dict) or statement.get("rank") == "deprecated":
            continue
        snak = statement.get("mainsnak")
        value = snak.get("datavalue", {}).get("value") if isinstance(snak, dict) else None
        if isinstance(value, str) and value.strip():
            ranked.append((0 if statement.get("rank") == "preferred" else 1, index, value.strip()))
    return [name for _, _, name in sorted(ranked)]


def parse_imageinfo(payload: Any) -> dict[str, FileInfo]:
    """Read ``query&prop=imageinfo``; the result is keyed by the file name without ``File:``."""
    query = payload.get("query") if isinstance(payload, dict) else None
    if not isinstance(query, dict) or not isinstance(query.get("pages"), dict):
        raise ValueError("not an imageinfo answer")
    pages = query["pages"]
    normalized = query.get("normalized")
    renamed = {
        n["from"]: n["to"]
        for n in (normalized if isinstance(normalized, list) else [])
        if isinstance(n, dict) and "from" in n and "to" in n
    }
    infos: dict[str, FileInfo] = {}
    for page in pages.values():
        if not isinstance(page, dict) or "missing" in page or not page.get("imageinfo"):
            continue
        title = str(page.get("title", ""))
        if not title.startswith("File:"):
            continue
        ii = page["imageinfo"][0]
        meta = ii.get("extmetadata") if isinstance(ii.get("extmetadata"), dict) else {}
        width, height = ii.get("width"), ii.get("height")
        if not isinstance(width, int) or not isinstance(height, int):
            continue
        name = title[len("File:") :]
        author_raw = _meta(meta, "Artist")
        infos[name] = FileInfo(
            file=name,
            thumb_url=ii.get("thumburl") if isinstance(ii.get("thumburl"), str) else None,
            original_url=ii.get("url") if isinstance(ii.get("url"), str) else None,
            description_url=str(
                ii.get("descriptionurl") or f"https://commons.wikimedia.org/wiki/{title}"
            ),
            width=width,
            height=height,
            mime=str(ii.get("mime", "")),
            licence=_meta(meta, "LicenseShortName"),
            licence_url=_meta(meta, "LicenseUrl"),
            author=strip_html(author_raw) if author_raw else None,
        )
    # A requested title that Commons normalised (underscores to spaces) is found under both.
    for original, target in renamed.items():
        key = original[len("File:") :] if original.startswith("File:") else original
        tgt = target[len("File:") :] if target.startswith("File:") else target
        if tgt in infos and key not in infos:
            infos[key] = infos[tgt]
    return infos


def _meta(meta: dict[str, Any], key: str) -> str | None:
    entry = meta.get(key)
    value = entry.get("value") if isinstance(entry, dict) else None
    return value.strip() if isinstance(value, str) and value.strip() else None


def rejection_reason(info: FileInfo) -> str | None:
    """The ADR 022 quality gate and licence allow-list. ``None`` means the photo may be used."""
    if info.mime not in ("image/jpeg", "image/png"):
        return REASON_NOT_PHOTO
    if info.width < MIN_ORIGINAL_WIDTH:
        return REASON_TOO_SMALL
    if info.width <= info.height:
        return REASON_NOT_LANDSCAPE
    if not licence_allowed(info.licence):
        return REASON_LICENCE
    if not info.author:
        return REASON_NO_AUTHOR
    return None


def check_image_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in IMAGE_HOSTS:
        raise WikimediaError("image url is not on a Wikimedia image host")
    return url


class WikimediaClient:
    def __init__(
        self,
        settings: Settings,
        engine: Engine | None,
        transport: httpx.BaseTransport | None = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._engine = engine
        self._transport = transport
        self._sleep = sleep
        self._clock = clock
        self._last_request = -1e9
        self.requests_made = 0
        # Tests must never reach the network: only an injected transport enables it there.
        self.enabled = (
            settings.wikimedia_enabled
            and engine is not None
            and (settings.environment != "test" or transport is not None)
        )

    @property
    def user_agent(self) -> str:
        return f"{self._settings.wikimedia_user_agent} httpx/{httpx.__version__}"

    # -- the three questions the resolver asks -------------------------------------------------

    def entities(self, qids: list[str]) -> dict[str, EntityImage]:
        """Image property and sitelink count for up to 50 Wikidata items, in one request."""
        if not qids:
            return {}
        params = {
            "action": "wbgetentities",
            "ids": "|".join(qids[:BATCH_SIZE]),
            "props": "claims|sitelinks",
            "format": "json",
        }
        return parse_entities(self._api(self._settings.wikidata_api_url, params))

    def file_infos(self, files: list[str]) -> dict[str, FileInfo]:
        """Size, type, licence, author and thumbnail URL for up to 50 Commons files."""
        if not files:
            return {}
        params = {
            "action": "query",
            "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata",
            "iiurlwidth": str(self._settings.image_source_width),
            "iiextmetadatafilter": "LicenseShortName|LicenseUrl|Artist",
            "titles": "|".join(f"File:{f}" for f in files[:BATCH_SIZE]),
            "format": "json",
        }
        return parse_imageinfo(self._api(self._settings.commons_api_url, params))

    def city_item(self, geonames_id: int) -> tuple[str | None, str | None]:
        """The Wikidata item whose GeoNames-ID property (P1566) is ``geonames_id``, with the reason
        there is none. Exactly one match is used; none or several are not guessed."""
        params = {
            "action": "query",
            "list": "search",
            "srsearch": f"haswbstatement:P1566={int(geonames_id)}",
            "srlimit": "3",
            "format": "json",
        }
        payload = self._api(self._settings.wikidata_api_url, params)
        hits = payload.get("query", {}).get("search") if isinstance(payload, dict) else None
        if not isinstance(hits, list):
            raise WikimediaError("unexpected search answer")
        titles = [
            str(h.get("title"))
            for h in hits
            if isinstance(h, dict) and _QID.match(str(h.get("title")))
        ]
        if len(titles) == 1:
            return titles[0], None
        return None, REASON_CITY_NO_MATCH if not titles else REASON_CITY_AMBIGUOUS

    def download(self, url: str) -> bytes:
        """The image bytes, capped in size, only from a Wikimedia image host."""
        check_image_url(url)
        response = self._request(
            "GET", url, params=None, max_bytes=self._settings.wikimedia_max_download_bytes
        )
        return response.content

    # -- HTTP ---------------------------------------------------------------------------------

    def _api(self, url: str, params: dict[str, str]) -> Any:
        maxlag = self._settings.wikimedia_maxlag_seconds
        full = {**params, "maxlag": str(maxlag)}
        last_lag: object = None
        for attempt in range(MAXLAG_ATTEMPTS):
            response = self._request("GET", url, params=full)
            try:
                payload = response.json()
            except ValueError as exc:
                raise WikimediaError("answer is not JSON") from exc
            error = payload.get("error") if isinstance(payload, dict) else None
            if isinstance(error, dict) and error.get("code") == "maxlag":
                last_lag = error.get("lag")
                self._pause(
                    response,
                    attempt,
                    minimum=MAXLAG_MIN_PAUSE_SECONDS,
                    maximum=MAXLAG_MAX_PAUSE_SECONDS,
                )
                continue
            if isinstance(error, dict):
                raise WikimediaError(f"api error {error.get('code')}")
            return payload
        raise WikimediaError(
            f"servers are lagged (last reported lag {last_lag} s, limit {maxlag} s); try later"
        )

    def _request(
        self, method: str, url: str, *, params: dict[str, str] | None, max_bytes: int | None = None
    ) -> httpx.Response:
        if not self.enabled or self._engine is None:
            raise WikimediaError("the Wikimedia adapter is disabled")
        for attempt in range(MAX_ATTEMPTS):
            self._wait_turn()
            try:
                if not reserve_call(self._engine, PROVIDER, self._settings.wikimedia_daily_budget):
                    raise WikimediaBudgetExhausted("daily budget used up")
            except SQLAlchemyError as exc:
                raise WikimediaError("budget counter unavailable") from exc
            self.requests_made += 1
            try:
                with httpx.Client(
                    headers={"User-Agent": self.user_agent},
                    timeout=self._settings.wikimedia_timeout_seconds,
                    transport=self._transport,
                    follow_redirects=False,
                ) as client:
                    response = client.request(method, url, params=params)
            except httpx.HTTPError as exc:
                raise WikimediaError(f"network error {type(exc).__name__}") from exc
            if response.status_code in (429, 503):
                self._pause(response, attempt)
                continue
            if response.status_code >= 300:  # redirects are not followed, so they are errors
                raise WikimediaError(f"HTTP {response.status_code}")
            if max_bytes is not None and len(response.content) > max_bytes:
                raise WikimediaError("download larger than the limit")
            return response
        raise WikimediaError("rate limited; try later")

    def _wait_turn(self) -> None:
        gap = self._settings.wikimedia_min_interval_seconds - (self._clock() - self._last_request)
        if gap > 0:
            self._sleep(gap)
        self._last_request = self._clock()

    def _pause(
        self,
        response: httpx.Response,
        attempt: int,
        *,
        minimum: float = 0.0,
        maximum: float = MAX_RETRY_SECONDS,
    ) -> None:
        """Wait as the server asked; with no ``Retry-After``, five seconds, doubling."""
        header = response.headers.get("Retry-After", "")
        try:
            seconds = float(header)
        except ValueError:
            seconds = DEFAULT_RETRY_SECONDS * (2**attempt)
        seconds = max(minimum, min(seconds, maximum))
        log.warning("wikimedia_backoff", status=response.status_code, seconds=seconds)
        self._sleep(seconds)
