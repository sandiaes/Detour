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
    REASON_NO_FILE_INFO,
    REASON_NO_IMAGE,
    REASON_NO_ITEM,
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
IMAGE_NAMESPACE = uuid.UUID("5d3c7a52-8f7e-4c3e-9a71-0d0e7c0a1d22")


def image_id_for(commons_file: str) -> uuid.UUID:
    """Stable identifier of a Commons file: the same file is the same image in every database."""
    return uuid.uuid5(IMAGE_NAMESPACE, commons_file)


def storage_key_for(image_id: uuid.UUID) -> str:
    return f"{image_id}.jpg"


@dataclass(frozen=True)
class Candidate:
    kind: str  # "place" or "city"
    ref_id: str  # place uuid or GeoNames id, as text
    qid: str | None  # None: no Wikidata item is known


@dataclass
class Report:
    found: int = 0
    none: int = 0
    rejected: int = 0
    reasons: Counter[str] = field(default_factory=Counter)
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
                "        AND l.checked_date < current_date - :days))"
                " ORDER BY s.score DESC NULLS LAST, p.id LIMIT :n"
            ),
            {"region": region_id, "days": RETRY_AFTER_DAYS, "n": limit},
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
                "        AND l.checked_date < current_date - :days))"
                " ORDER BY c.population DESC NULLS LAST, c.id LIMIT :n"
            ),
            {"countries": list(countries), "days": RETRY_AFTER_DAYS, "n": limit},
        ).all()
    return [Candidate("city", r[0], None) for r in rows]


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


def _resolve_batch(
    engine: Engine,
    client: WikimediaClient,
    store: ImageStore,
    settings: Settings,
    batch: Sequence[Candidate],
    report: Report,
) -> None:
    resolved = [
        Candidate(c.kind, c.ref_id, c.qid or _city_item(client, c)) if c.kind == "city" else c
        for c in batch
    ]
    qids = sorted({c.qid for c in resolved if c.qid})
    entities: dict[str, EntityImage] = client.entities(qids) if qids else {}
    files = sorted({e.file for e in entities.values() if e.file})
    infos: dict[str, FileInfo] = client.file_infos(files) if files else {}

    outcomes: list[tuple[Candidate, str, str | None, uuid.UUID | None]] = []
    for cand in resolved:
        entity = entities.get(cand.qid) if cand.qid else None
        if cand.qid is None or entity is None:
            outcomes.append((cand, "none", REASON_NO_ITEM, None))
        elif entity.file is None:
            outcomes.append((cand, "none", REASON_NO_IMAGE, None))
        elif entity.file not in infos:
            outcomes.append((cand, "none", REASON_NO_FILE_INFO, None))
        else:
            info = infos[entity.file]
            reason = rejection_reason(info)
            if reason is not None:
                outcomes.append((cand, "rejected", reason, None))
            else:
                result = _ensure_image(engine, client, store, settings, info, cand.qid, report)
                if result == "cap":
                    report.stopped = "image cap reached"
                    continue  # nothing recorded: asked again after the cap is raised
                if isinstance(result, str):
                    outcomes.append((cand, "rejected", result, None))
                else:
                    outcomes.append((cand, "found", None, result))

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


def _city_item(client: WikimediaClient, cand: Candidate) -> str | None:
    return client.city_item(int(cand.ref_id))


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
