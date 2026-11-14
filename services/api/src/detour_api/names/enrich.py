"""Fetch English names from Wikidata for the places, cities and areas that need them (ADR 025).

Never part of plan generation or of a request: it runs from the ``names`` command and in the
background after a trip is created, generated or read. Per batch of 50 entities it makes:

* one ``wbgetentities`` request for labels, aliases and the English Wikipedia sitelink (``en``,
  ``mul`` and the local languages only, ``sitefilter=enwiki``);
* for cities without a known item, one search per city by GeoNames id (P1566), as the image
  resolver does;
* for places without a QID but with a ``wikipedia`` tag, one ``wbgetentities`` per wiki by
  sitelink (``sites=dewiki&titles=...``);
* with ``coordinate_match`` only (operator command): a ``nearcoord`` search per place, the
  candidates' coordinates, country and classes, and the countries' ISO codes, judged by
  :mod:`detour_api.names.matching`.

Every outcome is written as the batch ends (names and the lookup row), so a run that stops resumes
from what is missing. "No English name" is a stored answer, asked again after 90 days. A Wikimedia
failure ends the run and writes nothing for the unfinished batch.
"""

import uuid
from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import Engine, text

from detour_api.adapters.wikimedia import BATCH_SIZE, WikimediaClient, WikimediaError
from detour_api.names import config
from detour_api.names.matching import MAX_DISTANCE_M, Subject, WikidataCandidate, choose
from detour_api.names.records import original_language, wikidata_records
from detour_api.names.store import prune, record_lookup, write_names

log = structlog.get_logger("detour.names")


@dataclass(frozen=True)
class Entity:
    kind: str  # "place", "city" or "area"
    ref: str  # place uuid, GeoNames id, area uuid
    qid: str | None
    local_name: str | None = None
    lang_hint: str | None = None  # language of the local name, when known
    wikipedia: str | None = None  # the OSM wikipedia tag ("de:Festung Hohensalzburg")
    lat: float | None = None
    lon: float | None = None
    country_iso2: str | None = None
    city_id: int | None = None
    category: str | None = None
    place_kind: str | None = None


@dataclass
class Report:
    found: int = 0
    no_english: int = 0
    no_item: int = 0
    names_written: int = 0
    requests: int = 0
    by_reason: Counter[str] = field(default_factory=Counter)
    unresolved: list[dict[str, str | None]] = field(default_factory=list)
    stopped: str | None = None
    pruned: dict[str, int] = field(default_factory=dict)

    def as_dict(self, unresolved_limit: int = 50) -> dict[str, object]:
        return {
            "found": self.found,
            "no_english": self.no_english,
            "no_item": self.no_item,
            "names_written": self.names_written,
            "requests": self.requests,
            "by_reason": dict(sorted(self.by_reason.items())),
            "unresolved": self.unresolved[:unresolved_limit],
            "unresolved_total": len(self.unresolved),
            "stopped": self.stopped,
            "pruned": self.pruned,
        }


# -- who needs names --------------------------------------------------------------------------

_DUE = (
    "NOT EXISTS (SELECT 1 FROM geo.place_name_lookup l WHERE l.entity_kind = '{kind}'"
    " AND l.entity_ref = {ref} AND l.source = 'wikidata' AND l.retry_after > :now)"
)

_PLACE_SELECT = """
    SELECT p.id::text AS ref, coalesce(s.wikidata_id, l.qid) AS qid, p.name, p.names_i18n,
           p.kind, p.category, ST_Y(p.geom) AS lat, ST_X(p.geom) AS lon, p.city_id,
           c.country_iso2, src.tags->>'wikipedia' AS wikipedia
    FROM geo.place p
    LEFT JOIN geo.place_signal s ON s.place_id = p.id
    LEFT JOIN geo.city c ON c.id = p.city_id
    LEFT JOIN geo.place_name_lookup l ON l.entity_kind = 'place' AND l.entity_ref = p.id::text
         AND l.source = 'wikidata'
    LEFT JOIN LATERAL (SELECT ps.tags FROM geo.place_source ps WHERE ps.place_id = p.id
         AND ps.source = 'osm' ORDER BY ps.source_ref LIMIT 1) src ON true
"""


def _place_entities(rows: Sequence[Any]) -> list[Entity]:
    return [
        Entity(
            kind="place",
            ref=r.ref,
            qid=r.qid,
            local_name=r.name,
            lang_hint=original_language(r.name, r.names_i18n),
            wikipedia=r.wikipedia,
            lat=r.lat,
            lon=r.lon,
            country_iso2=r.country_iso2,
            city_id=r.city_id,
            category=r.category,
            place_kind=r.kind,
        )
        for r in rows
    ]


def trip_entities(
    engine: Engine, trip_ids: Sequence[uuid.UUID], limit: int, now: datetime | None = None
) -> list[Entity]:
    """What these trips show and have no current answer for: their cities and areas, then the
    places in their itineraries and past-trip visits. Only places with a way to their item
    (a QID or a ``wikipedia`` tag) are asked."""
    ids = sorted({str(t) for t in trip_ids})
    if not ids:
        return []
    moment = now or datetime.now(UTC)
    params = {"ids": ids, "now": moment, "n": limit}
    with engine.begin() as conn:
        cities = conn.execute(
            text(
                "SELECT DISTINCT c.ref FROM ("
                "  SELECT t.destination_ref AS ref FROM app.trip t"
                "  WHERE t.id = ANY(CAST(:ids AS uuid[]))"
                "  AND t.destination_kind IN ('city', 'route')"
                "  UNION SELECT s.city_id::text FROM app.trip_stop s"
                "  WHERE s.trip_id = ANY(CAST(:ids AS uuid[]))"
                "  UNION SELECT d.base_city_id::text FROM app.itinerary_day d"
                "  JOIN app.itinerary it ON it.id = d.itinerary_id"
                "  WHERE it.trip_id = ANY(CAST(:ids AS uuid[])) AND d.base_city_id IS NOT NULL"
                f") c WHERE c.ref ~ '^[0-9]+$' AND {_DUE.format(kind='city', ref='c.ref')}"
                " ORDER BY 1 LIMIT :n"
            ),
            params,
        ).all()
        areas = conn.execute(
            text(
                "SELECT a.id::text AS ref, a.wikidata_id AS qid, a.name FROM app.trip t"
                " JOIN geo.admin_area a ON a.id::text = t.destination_ref"
                " WHERE t.id = ANY(CAST(:ids AS uuid[])) AND t.destination_kind = 'area'"
                f" AND a.wikidata_id IS NOT NULL AND {_DUE.format(kind='area', ref='a.id::text')}"
                " ORDER BY 1 LIMIT :n"
            ),
            params,
        ).all()
        places = conn.execute(
            text(
                _PLACE_SELECT + " WHERE p.id IN (SELECT i.place_id FROM app.itinerary it"
                "   JOIN app.itinerary_day d ON d.itinerary_id = it.id"
                "   JOIN app.itinerary_item i ON i.day_id = d.id"
                "   WHERE it.trip_id = ANY(CAST(:ids AS uuid[])) AND i.place_id IS NOT NULL"
                "   UNION SELECT CAST(v.geo_place_ref AS uuid) FROM app.trip_visit v"
                "   WHERE v.trip_id = ANY(CAST(:ids AS uuid[])) AND v.geo_place_ref IS NOT NULL)"
                "  AND (s.wikidata_id IS NOT NULL OR l.qid IS NOT NULL"
                "       OR src.tags ? 'wikipedia')"
                f"  AND {_DUE.format(kind='place', ref='p.id::text')}"
                " ORDER BY p.id LIMIT :n"
            ),
            params,
        ).all()
        hints = _city_language_hints(conn, [int(r.ref) for r in cities])
    out = [Entity("city", r.ref, None, lang_hint=hints.get(int(r.ref))) for r in cities]
    out += [Entity("area", r.ref, r.qid, local_name=r.name) for r in areas]
    out += _place_entities(places)
    return out[:limit]


def region_entities(
    engine: Engine,
    region_id: str,
    limit: int,
    *,
    with_coordinates: bool = False,
    now: datetime | None = None,
) -> list[Entity]:
    """The region's attractions with no current answer, best score first: those with a QID or a
    ``wikipedia`` tag, and, with ``with_coordinates``, the named ones without either."""
    moment = now or datetime.now(UTC)
    reach = "TRUE" if with_coordinates else (
        "(s.wikidata_id IS NOT NULL OR l.qid IS NOT NULL OR src.tags ? 'wikipedia')"
    )  # fmt: skip
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                _PLACE_SELECT
                + " WHERE p.region_id = :region AND p.is_active AND p.kind = 'attraction'"
                f"  AND p.name IS NOT NULL AND {reach}"
                f"  AND {_DUE.format(kind='place', ref='p.id::text')}"
                " ORDER BY s.score DESC NULLS LAST, p.id LIMIT :n"
            ),
            {"region": region_id, "now": moment, "n": limit},
        ).all()
    return _place_entities(rows)


def _city_language_hints(conn: Any, city_ids: Sequence[int]) -> dict[int, str]:
    """The local language of each city, read from the data itself: the language most of its
    places' own names are tagged in (``name:de`` equal to ``name``). No country table."""
    if not city_ids:
        return {}
    rows = conn.execute(
        text(
            "SELECT DISTINCT ON (city_id) city_id, k FROM ("
            "  SELECT p.city_id, e.key AS k, count(*) AS n FROM geo.place p,"
            "  jsonb_each_text(p.names_i18n) e"
            "  WHERE p.city_id = ANY(:ids) AND e.value = p.name AND e.key ~ '^[a-z]{2,3}$'"
            "  AND e.key NOT IN ('en', 'int') GROUP BY 1, 2) x ORDER BY city_id, n DESC, k"
        ),
        {"ids": list(city_ids)},
    ).all()
    return {r.city_id: r.k for r in rows}


# -- the work ---------------------------------------------------------------------------------


def _batches(items: Sequence[Entity]) -> Iterator[Sequence[Entity]]:
    for start in range(0, len(items), BATCH_SIZE):
        yield items[start : start + BATCH_SIZE]


def enrich(
    engine: Engine,
    client: WikimediaClient,
    entities: Sequence[Entity],
    *,
    coordinate_match: bool = False,
    now: datetime | None = None,
) -> Report:
    report = Report()
    moment = now or datetime.now(UTC)
    countries: dict[str, str | None] = {}
    try:
        for batch in _batches(entities):
            _enrich_batch(engine, client, batch, report, moment, coordinate_match, countries)
    except WikimediaError as exc:
        report.stopped = f"wikimedia: {exc}"
        log.warning("names_enrich_stopped", reason=str(exc))
    report.requests = client.requests_made
    return report


def _unresolved(report: Report, entity: Entity, reason: str) -> None:
    report.unresolved.append(
        {"kind": entity.kind, "ref": entity.ref, "name": entity.local_name, "reason": reason}
    )


def _enrich_batch(
    engine: Engine,
    client: WikimediaClient,
    batch: Sequence[Entity],
    report: Report,
    now: datetime,
    coordinate_match: bool,
    countries: dict[str, str | None],
) -> None:
    missing: dict[str, str] = {}  # entity ref -> why there is no item
    found_by: dict[str, str] = {}  # entity ref -> how the item was found
    resolved: list[Entity] = []
    # 1. Identifiers first: a GeoNames id for a city, a Wikipedia sitelink for a place.
    by_site: dict[str, list[tuple[Entity, str]]] = {}
    for entity in batch:
        if entity.qid:
            resolved.append(entity)
            found_by[entity.ref] = "qid"
            continue
        if entity.kind == "city":
            qid, why = client.city_item(int(entity.ref))
            if qid:
                found_by[entity.ref] = "geonames_id"
            else:
                missing[entity.ref] = why or "no_item"
            resolved.append(_with_qid(entity, qid))
            continue
        site_title = _sitelink(entity.wikipedia)
        if site_title is not None:
            by_site.setdefault(site_title[0], []).append((entity, site_title[1]))
            continue
        resolved.append(entity)
    for site, pairs in sorted(by_site.items()):
        items = client.items_for_sitelinks(site, [t for _, t in pairs])
        for entity, title in pairs:
            qid = items.get(title)
            if qid:
                found_by[entity.ref] = "wikipedia_sitelink"
            resolved.append(_with_qid(entity, qid))
    # 2. Coordinates, only on request and only for places still without an item.
    if coordinate_match:
        resolved = [
            _coordinate_match(engine, client, e, countries, found_by, missing)
            if e.qid is None and e.kind == "place"
            else e
            for e in resolved
        ]
    # 3. The names of every item found, in one request.
    qids = sorted({e.qid for e in resolved if e.qid})
    languages = {"en", "mul"} | {e.lang_hint for e in resolved if e.lang_hint}
    names = client.entity_names(qids, sorted(languages)) if qids else {}
    expires = now + timedelta(days=config.STORED_NAME_DAYS)
    with engine.begin() as conn:
        for entity in resolved:
            item = names.get(entity.qid) if entity.qid else None
            if item is None:
                reason = missing.get(entity.ref) or ("item_missing" if entity.qid else "no_item")
                record_lookup(conn, entity.kind, entity.ref, qid=entity.qid, status="no_item",
                              reason=reason, now=now)  # fmt: skip
                report.no_item += 1
                report.by_reason[reason] += 1
                _unresolved(report, entity, reason)
                continue
            records = wikidata_records(
                item.qid,
                item.labels,
                item.aliases,
                item.enwiki,
                native_lang=entity.lang_hint if entity.kind != "place" else None,
                retrieved_at=now,
                expires_at=expires,
            )
            report.names_written += write_names(conn, entity.kind, entity.ref, records, now)
            has_english = "en" in item.labels or item.enwiki is not None
            status = "found" if has_english else "no_english"
            why = found_by.get(entity.ref) if has_english else "no_english_label_or_article"
            record_lookup(conn, entity.kind, entity.ref, qid=item.qid, status=status,
                          reason=why, now=now)  # fmt: skip
            if has_english:
                report.found += 1
            else:
                report.no_english += 1
                report.by_reason["no_english_label_or_article"] += 1
                _unresolved(report, entity, "no_english_label_or_article")


def _with_qid(entity: Entity, qid: str | None) -> Entity:
    return Entity(**{**entity.__dict__, "qid": qid})


def _sitelink(tag: str | None) -> tuple[str, str] | None:
    """``de:Festung Hohensalzburg`` -> ("dewiki", "Festung Hohensalzburg")."""
    if not tag or ":" not in tag:
        return None
    lang, title = tag.split(":", 1)
    lang = lang.strip().lower()
    if not lang.isalpha() or not 2 <= len(lang) <= 3 or not title.strip():
        return None
    return f"{lang}wiki", title.strip()


def _coordinate_match(
    engine: Engine,
    client: WikimediaClient,
    entity: Entity,
    countries: dict[str, str | None],
    found_by: dict[str, str],
    missing: dict[str, str],
) -> Entity:
    if entity.lat is None or entity.lon is None or not entity.local_name:
        missing[entity.ref] = "no_coordinates_or_name"
        return entity
    place_class = config.place_class(entity.place_kind, entity.category)
    radius_km = max(MAX_DISTANCE_M.get(place_class, 300.0) / 1000.0, 0.1)
    qids = client.items_near(entity.local_name, entity.lat, entity.lon, radius_km)
    if not qids:
        missing[entity.ref] = "no_coordinate_candidate"
        return entity
    facts = client.match_facts(qids)
    for fact in facts.values():
        if fact.country_qid and fact.country_qid not in countries:
            countries[fact.country_qid] = client.country_iso(fact.country_qid)
    with engine.begin() as conn:
        candidates = [
            WikidataCandidate(
                qid=f.qid,
                lat=f.lat,
                lon=f.lon,
                country_iso2=countries.get(f.country_qid) if f.country_qid else None,
                city_id=_nearest_city(conn, f.lat, f.lon, entity.country_iso2),
                instance_of=f.instance_of,
                names=f.names,
            )
            for f in facts.values()
        ]
    subject = Subject(
        lat=entity.lat,
        lon=entity.lon,
        country_iso2=entity.country_iso2,
        city_id=entity.city_id,
        place_class=place_class,
        local_name=entity.local_name,
    )
    qid, verdicts = choose(subject, candidates)
    log.info(
        "names_coordinate_match",
        place=entity.ref,
        chosen=qid,
        verdicts=[{"qid": v.qid, "ok": v.accepted, "why": list(v.reasons)} for v in verdicts],
    )
    if qid is None:
        accepted = sum(v.accepted for v in verdicts)
        missing[entity.ref] = (
            "ambiguous_coordinate_match" if accepted > 1 else "no_coordinate_match"
        )
        return entity
    found_by[entity.ref] = "coordinate_match"
    return _with_qid(entity, qid)


def _nearest_city(
    conn: Any, lat: float | None, lon: float | None, country: str | None
) -> int | None:
    if lat is None or lon is None or country is None:
        return None
    value = conn.execute(
        text(
            "SELECT id FROM geo.city WHERE country_iso2 = :c"
            " ORDER BY geom <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), id LIMIT 1"
        ),
        {"c": country, "lat": lat, "lon": lon},
    ).scalar()
    return int(value) if value is not None else None


def run_prune(engine: Engine, now: datetime | None = None) -> dict[str, int]:
    with engine.begin() as conn:
        return prune(conn, now)
