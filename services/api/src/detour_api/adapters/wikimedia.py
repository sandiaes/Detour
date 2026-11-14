"""Wikidata and Wikimedia Commons adapter for reference photos (ADR 022) and place names (ADR 025).

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

Three API hosts are asked (Wikidata, Commons and, for the fallback chain of the ADR 022 amendment,
English Wikipedia's lead images); they share one queue, so there is never more than one request in
flight from this process and they are at least the minimum interval apart.

Everything that reads Wikimedia's answers is a pure function so it is tested against recorded
responses (``tests/fixtures/wikidata-wbgetentities-3.json``, ``commons-imageinfo-3.json``).
"""

import html
import re
import threading
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
REASON_NOT_ON_COMMONS = "not_on_commons"
REASON_LICENCE = "licence_not_allowed"
REASON_NO_AUTHOR = "no_author"
REASON_NO_FILE_INFO = "no_file_info"
REASON_UNDECODABLE = "could_not_decode"

# The size gate (ADR 022 amendment, decision e): portrait photos are accepted and cropped to fit
# on screen, so the rule is on the longer and the shorter side, not on the width.
MIN_LONGER_SIDE = 1200
MIN_SHORTER_SIDE = 800

# One queue for every client in this process: the background resolver and a cover-candidates
# request may run at the same time, and Wikimedia counts them as one client.
_QUEUE = threading.Lock()
_LAST_REQUEST = [-1e9]


class WikimediaError(Exception):
    """Wikimedia could not be asked or answered unusably; the caller leaves the item for later."""


class WikimediaBudgetExhausted(WikimediaError):
    pass


@dataclass(frozen=True)
class EntityImage:
    qid: str
    files: tuple[str, ...]  # image candidates, best first, without "File:" (P18, then P948)
    sitelinks: int
    enwiki: str | None = None  # the English Wikipedia article's title, if the item has one
    commons_category: str | None = None  # P373, without "Category:"

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
        sitelinks = sitelinks if isinstance(sitelinks, dict) else {}
        enwiki = sitelinks.get("enwiki")
        enwiki_title = enwiki.get("title") if isinstance(enwiki, dict) else None
        categories = _ranked_files(claims.get("P373"))
        found[qid] = EntityImage(
            qid=qid,
            files=tuple(files),
            sitelinks=len(sitelinks),
            enwiki=enwiki_title if isinstance(enwiki_title, str) and enwiki_title else None,
            commons_category=categories[0] if categories else None,
        )
    return found


def parse_pageimages(payload: Any) -> dict[str, str]:
    """Read ``query&prop=pageimages`` from Wikipedia: the lead image's file name for each requested
    title (redirects and normalisations followed back to the title that was asked for)."""
    query = payload.get("query") if isinstance(payload, dict) else None
    if not isinstance(query, dict):
        raise ValueError("not a pageimages answer")
    pages = query.get("pages")
    by_title: dict[str, str] = {}
    for page in pages.values() if isinstance(pages, dict) else []:
        if not isinstance(page, dict) or "missing" in page:
            continue
        name = page.get("pageimage")
        title = page.get("title")
        if isinstance(name, str) and name and isinstance(title, str):
            by_title[title] = name.replace("_", " ")
    for key in ("redirects", "normalized"):
        steps = query.get(key)
        for step in reversed(steps if isinstance(steps, list) else []):
            if isinstance(step, dict) and step.get("to") in by_title and "from" in step:
                by_title.setdefault(str(step["from"]), by_title[str(step["to"])])
    return by_title


def parse_category_files(payload: Any) -> list[str]:
    """Read ``list=categorymembers``: the files of a Commons category, in the API's order."""
    query = payload.get("query") if isinstance(payload, dict) else None
    members = query.get("categorymembers") if isinstance(query, dict) else None
    if not isinstance(members, list):
        raise ValueError("not a categorymembers answer")
    out: list[str] = []
    for m in members:
        title = m.get("title") if isinstance(m, dict) else None
        if isinstance(title, str) and title.startswith("File:"):
            out.append(title[len("File:") :])
    return out


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


@dataclass(frozen=True)
class EntityNames:
    """The names of one Wikidata item (ADR 025): only these strings and the identifiers are kept,
    never the answer itself."""

    qid: str
    labels: dict[str, str]
    aliases: dict[str, list[str]]
    enwiki: str | None


def parse_entity_names(payload: Any) -> dict[str, EntityNames]:
    """Read ``wbgetentities`` with ``props=labels|aliases|sitelinks``. A missing item is absent; a
    redirected item is found under the identifier that was asked for and the one it points to."""
    entities = payload.get("entities") if isinstance(payload, dict) else None
    if not isinstance(entities, dict):
        raise ValueError("not a wbgetentities answer")
    found: dict[str, EntityNames] = {}
    for key, entity in entities.items():
        if not isinstance(entity, dict) or "missing" in entity:
            continue
        qid = str(entity.get("id") or key)
        if not _QID.match(qid):
            continue
        labels = {
            lang: str(v["value"])
            for lang, v in (entity.get("labels") or {}).items()
            if isinstance(v, dict) and isinstance(v.get("value"), str) and v["value"].strip()
        }
        aliases: dict[str, list[str]] = {}
        for lang, values in (entity.get("aliases") or {}).items():
            texts = [
                str(v["value"])
                for v in values if isinstance(v, dict) and isinstance(v.get("value"), str)
            ] if isinstance(values, list) else []  # fmt: skip
            if texts:
                aliases[lang] = texts
        sitelinks = entity.get("sitelinks")
        enwiki = sitelinks.get("enwiki") if isinstance(sitelinks, dict) else None
        title = enwiki.get("title") if isinstance(enwiki, dict) else None
        names = EntityNames(
            qid, labels, aliases, title if isinstance(title, str) and title else None
        )
        found[qid] = names
        if _QID.match(str(key)) and key != qid:
            found[str(key)] = names
    return found


def parse_sitelink_items(payload: Any) -> dict[str, str]:
    """Read ``wbgetentities`` asked by ``sites`` and ``titles``: page title -> QID."""
    entities = payload.get("entities") if isinstance(payload, dict) else None
    if not isinstance(entities, dict):
        raise ValueError("not a wbgetentities answer")
    out: dict[str, str] = {}
    for key, entity in entities.items():
        if not isinstance(entity, dict) or "missing" in entity or not _QID.match(str(key)):
            continue
        for link in (entity.get("sitelinks") or {}).values():
            if isinstance(link, dict) and isinstance(link.get("title"), str):
                out[link["title"]] = str(key)
    return out


@dataclass(frozen=True)
class MatchFacts:
    """What the controlled coordinate match needs to know about a candidate item."""

    qid: str
    lat: float | None
    lon: float | None
    country_qid: str | None
    instance_of: frozenset[str]
    names: tuple[str, ...]


def _claim_values(claims: dict[str, Any], prop: str) -> list[Any]:
    out = []
    for statement in claims.get(prop) or []:
        if not isinstance(statement, dict) or statement.get("rank") == "deprecated":
            continue
        snak = statement.get("mainsnak")
        value = snak.get("datavalue", {}).get("value") if isinstance(snak, dict) else None
        if value is not None:
            out.append(value)
    return out


def parse_match_facts(payload: Any) -> dict[str, MatchFacts]:
    """Read ``wbgetentities`` (labels, aliases, claims) for the candidates of a coordinate match:
    coordinates (P625), country (P17) and classes (P31)."""
    entities = payload.get("entities") if isinstance(payload, dict) else None
    if not isinstance(entities, dict):
        raise ValueError("not a wbgetentities answer")
    out: dict[str, MatchFacts] = {}
    for qid, entity in entities.items():
        if not isinstance(entity, dict) or "missing" in entity or not _QID.match(str(qid)):
            continue
        raw_claims = entity.get("claims")
        claims: dict[str, Any] = raw_claims if isinstance(raw_claims, dict) else {}
        coords = [v for v in _claim_values(claims, "P625") if isinstance(v, dict)]
        lat = coords[0].get("latitude") if coords else None
        lon = coords[0].get("longitude") if coords else None
        countries = [v.get("id") for v in _claim_values(claims, "P17") if isinstance(v, dict)]
        classes = frozenset(
            str(v.get("id")) for v in _claim_values(claims, "P31") if isinstance(v, dict)
        )
        names = [
            str(v["value"]) for v in (entity.get("labels") or {}).values()
            if isinstance(v, dict) and isinstance(v.get("value"), str)
        ]  # fmt: skip
        for values in (entity.get("aliases") or {}).values():
            names += [str(v["value"]) for v in values if isinstance(v, dict) and "value" in v]
        out[str(qid)] = MatchFacts(
            qid=str(qid),
            lat=float(lat) if isinstance(lat, (int, float)) else None,
            lon=float(lon) if isinstance(lon, (int, float)) else None,
            country_qid=str(countries[0]) if len(set(countries)) == 1 else None,
            instance_of=classes,
            names=tuple(dict.fromkeys(names)),
        )
    return out


def parse_search_titles(payload: Any) -> list[str]:
    """Read ``list=search`` on Wikidata: the QIDs of the hits, in the API's order."""
    hits = payload.get("query", {}).get("search") if isinstance(payload, dict) else None
    if not isinstance(hits, list):
        raise ValueError("not a search answer")
    return [
        str(h.get("title")) for h in hits if isinstance(h, dict) and _QID.match(str(h.get("title")))
    ]


def parse_iso_code(payload: Any) -> str | None:
    """Read ``wbgetclaims`` for P297 (ISO 3166-1 alpha-2) of a country item."""
    claims = payload.get("claims") if isinstance(payload, dict) else None
    if not isinstance(claims, dict):
        raise ValueError("not a wbgetclaims answer")
    values = [v for v in _claim_values(claims, "P297") if isinstance(v, str)]
    return values[0].upper() if len(set(values)) == 1 else None


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
    if max(info.width, info.height) < MIN_LONGER_SIDE or min(info.width, info.height) < (
        MIN_SHORTER_SIDE
    ):
        return REASON_TOO_SMALL
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

    # -- the questions the resolver asks ---------------------------------------------------------

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

    def file_infos(self, files: list[str], width: int | None = None) -> dict[str, FileInfo]:
        """Size, type, licence, author and a thumbnail URL ``width`` wide (default: the source
        width of a stored photo) for up to 50 Commons files."""
        if not files:
            return {}
        params = {
            "action": "query",
            "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata",
            "iiurlwidth": str(width or self._settings.image_source_width),
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

    def page_images(self, titles: list[str]) -> dict[str, str]:
        """The free lead image of up to 50 English Wikipedia articles (``pilicense=free``, the
        API's default, stated anyway). The file may be a local upload: the caller checks it on
        Commons before using it."""
        if not titles:
            return {}
        params = {
            "action": "query",
            "prop": "pageimages",
            "piprop": "name",
            "pilicense": "free",
            "pilimit": str(BATCH_SIZE),
            "redirects": "1",
            "titles": "|".join(titles[:BATCH_SIZE]),
            "format": "json",
        }
        return parse_pageimages(self._api(self._settings.enwiki_api_url, params))

    def category_files(self, category: str, limit: int = BATCH_SIZE) -> list[str]:
        """The first files of a Commons category, in the API's order."""
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": f"Category:{category}",
            "cmtype": "file",
            "cmnamespace": "6",
            "cmlimit": str(min(limit, BATCH_SIZE)),
            "format": "json",
        }
        return parse_category_files(self._api(self._settings.commons_api_url, params))

    def entity_names(self, qids: list[str], languages: list[str]) -> dict[str, EntityNames]:
        """Labels and aliases in ``languages`` and the English Wikipedia title of up to 50 items,
        in one request (ADR 025). ``sitefilter`` keeps the answer small."""
        if not qids:
            return {}
        params = {
            "action": "wbgetentities",
            "ids": "|".join(qids[:BATCH_SIZE]),
            "props": "labels|aliases|sitelinks",
            "languages": "|".join(sorted(set(languages))),
            "sitefilter": "enwiki",
            "format": "json",
        }
        return parse_entity_names(self._api(self._settings.wikidata_api_url, params))

    def items_for_sitelinks(self, site: str, titles: list[str]) -> dict[str, str]:
        """The Wikidata items of up to 50 Wikipedia pages of one wiki (``dewiki``): a page's
        ``wikibase_item``, asked of Wikidata itself, so no other wiki is called."""
        if not titles:
            return {}
        params = {
            "action": "wbgetentities",
            "sites": site,
            "titles": "|".join(titles[:BATCH_SIZE]),
            "props": "sitelinks",
            "sitefilter": site,
            "format": "json",
        }
        return parse_sitelink_items(self._api(self._settings.wikidata_api_url, params))

    def items_near(
        self, name: str, lat: float, lon: float, radius_km: float, limit: int = 5
    ) -> list[str]:
        """Items with coordinates near a point whose text matches a name (CirrusSearch
        ``nearcoord``): candidates for the controlled coordinate match only."""
        quoted = name.replace('"', " ")
        params = {
            "action": "query",
            "list": "search",
            "srsearch": f'"{quoted}" haswbstatement:P625 nearcoord:{radius_km:g}km,{lat:.6f},{lon:.6f}',
            "srlimit": str(limit),
            "format": "json",
        }
        return parse_search_titles(self._api(self._settings.wikidata_api_url, params))

    def match_facts(self, qids: list[str]) -> dict[str, MatchFacts]:
        if not qids:
            return {}
        params = {
            "action": "wbgetentities",
            "ids": "|".join(qids[:BATCH_SIZE]),
            "props": "labels|aliases|claims",
            "format": "json",
        }
        return parse_match_facts(self._api(self._settings.wikidata_api_url, params))

    def country_iso(self, country_qid: str) -> str | None:
        params = {
            "action": "wbgetclaims",
            "entity": country_qid,
            "property": "P297",
            "format": "json",
        }
        return parse_iso_code(self._api(self._settings.wikidata_api_url, params))

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
            with _QUEUE:
                response = self._attempt(method, url, params)
            if response.status_code in (429, 503):
                self._pause(response, attempt)
                continue
            if response.status_code >= 300:  # redirects are not followed, so they are errors
                raise WikimediaError(f"HTTP {response.status_code}")
            if max_bytes is not None and len(response.content) > max_bytes:
                raise WikimediaError("download larger than the limit")
            return response
        raise WikimediaError("rate limited; try later")

    def _attempt(self, method: str, url: str, params: dict[str, str] | None) -> httpx.Response:
        """One request, in this process's queue."""
        if self._engine is None:
            raise WikimediaError("the Wikimedia adapter is disabled")
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
                return client.request(method, url, params=params)
        except httpx.HTTPError as exc:
            raise WikimediaError(f"network error {type(exc).__name__}") from exc

    def _wait_turn(self) -> None:
        """Called inside the queue. With the real clock the spacing is kept across every client
        of the process; a test's clock keeps its own."""
        shared = self._clock is time.monotonic
        last = max(self._last_request, _LAST_REQUEST[0]) if shared else self._last_request
        gap = self._settings.wikimedia_min_interval_seconds - (self._clock() - last)
        if gap > 0:
            self._sleep(gap)
        self._last_request = self._clock()
        if shared:
            _LAST_REQUEST[0] = self._last_request

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
