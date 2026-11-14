"""Find, fetch, resize and store photos for places and cities (ADR 022, decisions 13 and 14).

Never part of plan generation. It runs from the ``images`` command (and, later, as a background
task after a trip is created). For each place or city it asks Wikidata for the image property,
Commons for the file's licence and size, applies the licence allow-list and the quality gate, and
only then downloads one thumbnail, stores one JPEG and writes ``geo.image`` and
``geo.image_lookup``. Every outcome is recorded, so a place with no photo is not asked again for
90 days. Stored images are capped (``image_max_stored``).
"""

import uuid
from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import date

import structlog
from sqlalchemy import Connection, Engine, text

from detour_api.adapters.wikimedia import (
    BATCH_SIZE,
    REASON_CITY_AMBIGUOUS,
    REASON_CITY_NO_MATCH,
    REASON_NO_FILE_INFO,
    REASON_NO_IMAGE,
    REASON_NO_ITEM,
    REASON_NOT_ON_COMMONS,
    REASON_UNDECODABLE,
    EntityImage,
    FileInfo,
    WikimediaClient,
    WikimediaError,
    rejection_reason,
)
from detour_api.images.process import UndecodableImage, process_image
from detour_api.images.store import ImageStore, StoreError
from detour_api.settings import Settings

log = structlog.get_logger("detour.images")

RETRY_AFTER_DAYS = 90
# An answer that may have been a hiccup is asked again sooner: a city whose item was not found by
# its GeoNames id (the search can miss), a file the API gave no information about.
SHORT_RETRY_DAYS = 7
SHORT_RETRY_REASONS = (REASON_CITY_NO_MATCH, REASON_CITY_AMBIGUOUS, REASON_NO_FILE_INFO)
IMAGE_NAMESPACE = uuid.UUID("5d3c7a52-8f7e-4c3e-9a71-0d0e7c0a1d22")


def image_id_for(commons_file: str) -> uuid.UUID:
    """Stable identifier of a Commons file: the same file is the same image in every database."""
    return uuid.uuid5(IMAGE_NAMESPACE, commons_file)


def storage_key_for(image_id: uuid.UUID) -> str:
    return f"{image_id}.jpg"


# Kinds that use the whole fallback chain (ADR 022 amendment, decision a): the item's image and
# banner, then the English Wikipedia article's lead image, then the item's Commons category.
CHAIN_KINDS = ("city", "area")
# How many files of a Commons category are looked at (one categorymembers and one imageinfo
# request).
CATEGORY_FILES = 50


@dataclass(frozen=True)
class Candidate:
    kind: str  # "place", "city" or "area"
    ref_id: str  # place uuid, GeoNames id or admin area uuid, as text
    qid: str | None  # None: no Wikidata item is known


@dataclass
class Report:
    found: int = 0
    none: int = 0
    rejected: int = 0
    reasons: Counter[str] = field(default_factory=Counter)
    # Which step of the chain found each photo, by kind ("city:image", "city:wikipedia",
    # "city:category", "place:image"): the coverage figures of the ADR 022 amendment.
    steps: Counter[str] = field(default_factory=Counter)
    downloaded: int = 0
    stored_bytes: int = 0
    requests: int = 0
    stopped: str | None = None  # why the run ended early
    # What this run wrote, so a dry run can take it back (see discard_run); not part of the report.
    written: list[tuple[str, str]] = field(default_factory=list, repr=False)
    created_images: list[uuid.UUID] = field(default_factory=list, repr=False)

    def as_dict(self) -> dict[str, object]:
        return {
            "found": self.found,
            "none": self.none,
            "rejected": self.rejected,
            "reasons": dict(sorted(self.reasons.items())),
            "steps": dict(sorted(self.steps.items())),
            "downloaded": self.downloaded,
            "stored_bytes": self.stored_bytes,
            "requests": self.requests,
            "stopped": self.stopped,
        }


# -- who to look up ---------------------------------------------------------------------------


def place_candidates(engine: Engine, region_id: str, limit: int) -> list[Candidate]:
    """Attractions of the region with a Wikidata item and no current answer, best score first."""
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT p.id::text, s.wikidata_id FROM geo.place p"
                " JOIN geo.place_signal s ON s.place_id = p.id"
                " LEFT JOIN geo.image_lookup l ON l.kind = 'place' AND l.ref_id = p.id::text"
                " WHERE p.region_id = :region AND p.kind = 'attraction' AND p.is_active"
                "   AND s.wikidata_id IS NOT NULL"
                "   AND (l.ref_id IS NULL OR (l.status <> 'found'"
                "        AND l.checked_date < current_date -"
                "        CASE WHEN l.reason = ANY(:short) THEN :short_days ELSE :days END))"
                " ORDER BY s.score DESC NULLS LAST, p.id LIMIT :n"
            ),
            {
                "region": region_id,
                "days": RETRY_AFTER_DAYS,
                "short": list(SHORT_RETRY_REASONS),
                "short_days": SHORT_RETRY_DAYS,
                "n": limit,
            },
        ).all()
    return [Candidate("place", r[0], r[1]) for r in rows]


def city_candidates(engine: Engine, countries: Sequence[str], limit: int) -> list[Candidate]:
    """The most populous cities of the countries with no current answer. Their Wikidata item is
    found through the GeoNames-ID property, so ``qid`` is filled in by the resolver."""
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT c.id::text FROM geo.city c"
                " LEFT JOIN geo.image_lookup l ON l.kind = 'city' AND l.ref_id = c.id::text"
                " WHERE c.country_iso2 = ANY(:countries)"
                "   AND (l.ref_id IS NULL OR (l.status <> 'found'"
                "        AND l.checked_date < current_date -"
                "        CASE WHEN l.reason = ANY(:short) THEN :short_days ELSE :days END))"
                " ORDER BY c.population DESC NULLS LAST, c.id LIMIT :n"
            ),
            {
                "countries": list(countries),
                "days": RETRY_AFTER_DAYS,
                "short": list(SHORT_RETRY_REASONS),
                "short_days": SHORT_RETRY_DAYS,
                "n": limit,
            },
        ).all()
    return [Candidate("city", r[0], None) for r in rows]


def area_candidates(engine: Engine, region_id: str, limit: int) -> list[Candidate]:
    """Areas of the region (countries and regions) with a Wikidata item and no current answer,
    the larger level first (a country before its regions)."""
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT a.id::text, a.wikidata_id FROM geo.admin_area a"
                " LEFT JOIN geo.image_lookup l ON l.kind = 'area' AND l.ref_id = a.id::text"
                " WHERE a.region_id = :region AND a.is_active AND a.wikidata_id IS NOT NULL"
                "   AND (l.ref_id IS NULL OR (l.status <> 'found'"
                "        AND l.checked_date < current_date -"
                "        CASE WHEN l.reason = ANY(:short) THEN :short_days ELSE :days END))"
                " ORDER BY a.level, a.id LIMIT :n"
            ),
            {
                "region": region_id,
                "days": RETRY_AFTER_DAYS,
                "short": list(SHORT_RETRY_REASONS),
                "short_days": SHORT_RETRY_DAYS,
                "n": limit,
            },
        ).all()
    return [Candidate("area", r[0], r[1]) for r in rows]


# -- the work ---------------------------------------------------------------------------------


def _batches(items: Sequence[Candidate]) -> Iterator[Sequence[Candidate]]:
    for start in range(0, len(items), BATCH_SIZE):
        yield items[start : start + BATCH_SIZE]


def resolve(
    engine: Engine,
    client: WikimediaClient,
    store: ImageStore,
    settings: Settings,
    candidates: Sequence[Candidate],
) -> Report:
    """Resolve candidates in batches of 50, committing after each batch. A Wikimedia or storage
    failure ends the run (``report.stopped``); what was done stays, the rest waits for next time."""
    report = Report()
    try:
        for batch in _batches(candidates):
            _resolve_batch(engine, client, store, settings, batch, report)
    except WikimediaError as exc:
        report.stopped = f"wikimedia: {exc}"
    except StoreError as exc:
        report.stopped = f"storage: {exc}"
    report.requests = client.requests_made
    return report


MAX_FILES_TRIED = 3


def _resolve_batch(
    engine: Engine,
    client: WikimediaClient,
    store: ImageStore,
    settings: Settings,
    batch: Sequence[Candidate],
    report: Report,
) -> None:
    why: dict[str, str] = {}  # why a city has no Wikidata item
    resolved: list[Candidate] = []
    for cand in batch:
        if cand.kind == "city" and cand.qid is None:
            qid, missing = client.city_item(int(cand.ref_id))
            if missing:
                why[cand.ref_id] = missing
            cand = Candidate(cand.kind, cand.ref_id, qid)
        resolved.append(cand)
    qids = sorted({c.qid for c in resolved if c.qid})
    entities: dict[str, EntityImage] = client.entities(qids) if qids else {}
    files = sorted({f for e in entities.values() for f in e.files[:MAX_FILES_TRIED]})
    infos: dict[str, FileInfo] = {}
    for start in range(0, len(files), BATCH_SIZE):
        infos.update(client.file_infos(files[start : start + BATCH_SIZE]))

    outcomes: list[tuple[Candidate, str, str | None, uuid.UUID | None]] = []
    later: list[tuple[Candidate, EntityImage, str | None]] = []  # for the rest of the chain
    capped = False
    for cand in resolved:
        entity = entities.get(cand.qid) if cand.qid else None
        if cand.qid is None or entity is None:
            outcomes.append((cand, "none", why.get(cand.ref_id, REASON_NO_ITEM), None))
            continue
        files = list(entity.files[:MAX_FILES_TRIED])
        known = [f for f in files if f in infos]
        reason: str | None = None
        if not files:
            reason = REASON_NO_IMAGE
        elif not known:
            reason = REASON_NO_FILE_INFO
        else:
            chosen, reason, capped = _first_usable(
                engine, client, store, settings, infos, known, cand.qid, report
            )
            if capped:
                break
            if chosen is not None:
                report.steps[f"{cand.kind}:image"] += 1
                outcomes.append((cand, "found", None, chosen))
                continue
        if cand.kind in CHAIN_KINDS:
            later.append((cand, entity, reason))
        else:
            outcomes.append((cand, "none" if not known else "rejected", reason, None))
    if not capped and later:
        capped = _rest_of_chain(engine, client, store, settings, later, infos, outcomes, report)
    if capped:
        report.stopped = "image cap reached"

    with engine.begin() as conn:
        for cand, status, reason, image_id in outcomes:
            _write_lookup(conn, cand, status, reason, image_id)
            report.written.append((cand.kind, cand.ref_id))
            if status == "found":
                report.found += 1
            elif status == "none":
                report.none += 1
            else:
                report.rejected += 1
            if reason:
                report.reasons[reason] += 1


def _first_usable(
    engine: Engine,
    client: WikimediaClient,
    store: ImageStore,
    settings: Settings,
    infos: dict[str, FileInfo],
    files: Sequence[str],
    qid: str,
    report: Report,
) -> tuple[uuid.UUID | None, str | None, bool]:
    """The first file that passes the gate, stored. Returns (image id, first reason, cap reached).
    A file Commons gave no information about is not a Commons file (a local Wikipedia upload) and
    is rejected as such."""
    first_reason: str | None = None
    for file in files:
        info = infos.get(file)
        if info is None:
            first_reason = first_reason or REASON_NOT_ON_COMMONS
            continue
        reason = rejection_reason(info)
        if reason is None:
            result = _ensure_image(engine, client, store, settings, info, qid, report)
            if result == "cap":
                return None, first_reason, True
            if isinstance(result, uuid.UUID):
                return result, None, False
            reason = result
        first_reason = first_reason or reason
    return None, first_reason, False


def _rest_of_chain(
    engine: Engine,
    client: WikimediaClient,
    store: ImageStore,
    settings: Settings,
    later: list[tuple[Candidate, EntityImage, str | None]],
    infos: dict[str, FileInfo],
    outcomes: list[tuple[Candidate, str, str | None, uuid.UUID | None]],
    report: Report,
) -> bool:
    """Wikipedia's lead image, then the Commons category, for the cities and areas the item's own
    image did not serve. Returns whether the image cap was reached."""
    titles = sorted({e.enwiki for _, e, _ in later if e.enwiki})
    lead = client.page_images(titles) if titles else {}
    lead_files = sorted({f for f in lead.values() if f not in infos})
    for start in range(0, len(lead_files), BATCH_SIZE):
        infos.update(client.file_infos(lead_files[start : start + BATCH_SIZE]))
    for cand, entity, reason in later:
        assert cand.qid is not None  # noqa: S101 - only candidates with an item come here
        steps: list[tuple[str, list[str]]] = []
        if entity.enwiki and entity.enwiki in lead:
            steps.append(("wikipedia", [lead[entity.enwiki]]))
        if entity.commons_category:
            steps.append(("category", []))  # filled only if the earlier steps fail
        chosen: uuid.UUID | None = None
        for step, files in steps:
            if step == "category":
                files = client.category_files(entity.commons_category or "", CATEGORY_FILES)
                unknown = [f for f in files if f not in infos]
                if unknown:
                    infos.update(client.file_infos(unknown[:BATCH_SIZE]))
            if not files:
                continue
            chosen, why, capped = _first_usable(
                engine, client, store, settings, infos, files, cand.qid, report
            )
            if capped:
                return True
            if reason in (None, REASON_NO_IMAGE):  # a concrete refusal says more than "none"
                reason = why or reason
            if chosen is not None:
                report.steps[f"{cand.kind}:{step}"] += 1
                break
        if chosen is not None:
            outcomes.append((cand, "found", None, chosen))
        elif reason in (None, REASON_NO_IMAGE):
            outcomes.append((cand, "none", REASON_NO_IMAGE, None))
        else:
            outcomes.append((cand, "rejected", reason, None))
    return False


def _ensure_image(
    engine: Engine,
    client: WikimediaClient,
    store: ImageStore,
    settings: Settings,
    info: FileInfo,
    qid: str,
    report: Report,
) -> uuid.UUID | str:
    """The image id for this file, downloading and storing it first if it is new. Returns a
    reason string if the file cannot be used, or ``"cap"`` when the cap is reached."""
    image_id = image_id_for(info.file)
    with engine.begin() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM geo.image WHERE id = :id"), {"id": image_id}
        ).first()
        if exists:
            return image_id
        stored = conn.execute(text("SELECT count(*) FROM geo.image")).scalar_one()
    if stored >= settings.image_max_stored:
        return "cap"
    url = info.thumb_url or info.original_url
    if url is None:
        return REASON_NO_FILE_INFO
    raw = client.download(url)
    try:
        processed = process_image(
            raw, max_side=settings.image_max_side, quality=settings.image_jpeg_quality
        )
    except UndecodableImage:
        return REASON_UNDECODABLE
    key = storage_key_for(image_id)
    store.put(key, processed.data)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO geo.image (id, source, commons_file, source_url, wikidata_id, author,"
                " licence, licence_url, width, height, bytes, color, storage_key, fetched_date)"
                " VALUES (:id, 'wikimedia_commons', :file, :src, :qid, :author, :licence, :lurl,"
                " :w, :h, :bytes, :color, :key, :today) ON CONFLICT (id) DO NOTHING"
            ),
            {
                "id": image_id,
                "file": info.file,
                "src": info.description_url,
                "qid": qid,
                "author": info.author,
                "licence": info.licence,
                "lurl": info.licence_url,
                "w": processed.width,
                "h": processed.height,
                "bytes": len(processed.data),
                "color": processed.color,
                "key": key,
                "today": date.today(),
            },
        )
    report.downloaded += 1
    report.stored_bytes += len(processed.data)
    report.created_images.append(image_id)
    return image_id


def _write_lookup(
    conn: Connection,
    cand: Candidate,
    status: str,
    reason: str | None,
    image_id: uuid.UUID | None,
) -> None:
    conn.execute(
        text(
            "INSERT INTO geo.image_lookup (kind, ref_id, status, reason, image_id, checked_date)"
            " VALUES (:kind, :ref, :status, :reason, :image, :today)"
            " ON CONFLICT (kind, ref_id) DO UPDATE SET status = EXCLUDED.status,"
            " reason = EXCLUDED.reason, image_id = EXCLUDED.image_id,"
            " checked_date = EXCLUDED.checked_date"
        ),
        {
            "kind": cand.kind,
            "ref": cand.ref_id,
            "status": status,
            "reason": reason,
            "image": image_id,
            "today": date.today(),
        },
    )


def discard_runs(engine: Engine, reports: Sequence[Report]) -> None:
    """Take back what dry runs wrote. A dry run keeps no files, so the rows it wrote would claim
    photos that are stored nowhere, and its lookups would stop them being fetched later. Lookups
    go first, across all the runs, so an image shared by two runs is removed too."""
    with engine.begin() as conn:
        for report in reports:
            for kind, ref_id in report.written:
                conn.execute(
                    text("DELETE FROM geo.image_lookup WHERE kind = :k AND ref_id = :r"),
                    {"k": kind, "r": ref_id},
                )
        for report in reports:
            for image_id in report.created_images:
                conn.execute(
                    text(
                        "DELETE FROM geo.image WHERE id = :id AND NOT EXISTS"
                        " (SELECT 1 FROM geo.image_lookup WHERE image_id = :id)"
                    ),
                    {"id": image_id},
                )


def repair_missing(
    engine: Engine, client: WikimediaClient, store: ImageStore, settings: Settings
) -> dict[str, int]:
    """Fetch again every image row whose file is missing from the store (a dry run, a lost
    object). Returns counts; a file Commons no longer offers under the gate is left alone and
    counted as ``unrepairable``, never silently dropped."""
    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT id, commons_file, storage_key FROM geo.image ORDER BY id")
        ).all()
    missing = [r for r in rows if not store.exists(r[2])]
    counts = {"checked": len(rows), "missing": len(missing), "repaired": 0, "unrepairable": 0}
    for start in range(0, len(missing), BATCH_SIZE):
        batch = missing[start : start + BATCH_SIZE]
        infos = client.file_infos([r[1] for r in batch])
        for image_id, file, key in batch:
            info = infos.get(file)
            url = info.thumb_url or info.original_url if info else None
            if info is None or url is None or rejection_reason(info) is not None:
                counts["unrepairable"] += 1
                continue
            try:
                processed = process_image(
                    client.download(url),
                    max_side=settings.image_max_side,
                    quality=settings.image_jpeg_quality,
                )
            except UndecodableImage:
                counts["unrepairable"] += 1
                continue
            store.put(key, processed.data)
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "UPDATE geo.image SET width = :w, height = :h, bytes = :b, color = :c,"
                        " fetched_date = :d WHERE id = :id"
                    ),
                    {
                        "w": processed.width,
                        "h": processed.height,
                        "b": len(processed.data),
                        "c": processed.color,
                        "d": date.today(),
                        "id": image_id,
                    },
                )
            counts["repaired"] += 1
    return counts
