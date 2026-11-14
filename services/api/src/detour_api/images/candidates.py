"""Photos to choose from for a destination: "Change photo" (ADR 022, decision 15; amendment,
decisions g and h).

The candidates come in the order of the fallback chain: the item's own image and banner, the English
Wikipedia article's lead image, then the files of the item's Commons category. Each passes the same
licence allow-list and quality gate as an automatic photo; at most ``MAX_CANDIDATES`` are offered.
The app sees only small previews made and served by the backend (``/v1/cover-previews/{id}``), so
it still talks to no one else. The list is cached for a week and every Wikimedia request counts
against the adapter's daily budget.

Choosing a candidate stores it exactly like an automatic photo (one JPEG, longest side 1,080 px, a
``geo.image`` row) and sets the trip's ``cover_image_id``.
"""

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import date, timedelta

import structlog
from sqlalchemy import Connection, Engine, text

from detour_api.adapters.wikimedia import (
    BATCH_SIZE,
    FileInfo,
    WikimediaClient,
    WikimediaError,
    rejection_reason,
)
from detour_api.images import resolver
from detour_api.images.process import UndecodableImage, process_image
from detour_api.images.store import ImageStore
from detour_api.settings import Settings

log = structlog.get_logger("detour.images.candidates")

MAX_CANDIDATES = 12
# A standard Wikimedia thumbnail step, large enough for a sheet of three previews across a tablet.
PREVIEW_WIDTH = 500
PREVIEW_QUALITY = 70
CACHE_DAYS = 7
PREVIEW_NAMESPACE = uuid.UUID("8f5a3c1e-2b7d-4e90-a1c4-6d2e9b0f7a35")


class CandidatesUnavailable(Exception):
    """Wikimedia or storage could not be asked; the app keeps the current cover."""


@dataclass(frozen=True)
class CoverCandidate:
    commons_file: str
    preview_id: str
    author: str
    licence: str
    licence_url: str | None
    source_url: str
    width: int
    height: int


def preview_id_for(commons_file: str) -> uuid.UUID:
    return uuid.uuid5(PREVIEW_NAMESPACE, commons_file)


def _cache_key(kind: str, ref: str) -> str:
    return f"wikimedia:cover-candidates:{kind}:{ref}"


def _qid(conn: Connection, client: WikimediaClient, kind: str, ref: str) -> str | None:
    if kind == "area":
        row = conn.execute(
            text("SELECT wikidata_id FROM geo.admin_area WHERE id::text = :r"), {"r": ref}
        ).first()
        return None if row is None else row[0]
    # A city: the item of a stored photo says it; otherwise the GeoNames-ID search does.
    row = conn.execute(
        text(
            "SELECT i.wikidata_id FROM geo.image_lookup l JOIN geo.image i ON i.id = l.image_id"
            " WHERE l.kind = 'city' AND l.ref_id = :r AND i.wikidata_id IS NOT NULL"
        ),
        {"r": ref},
    ).first()
    if row is not None:
        return str(row[0])
    qid, _ = client.city_item(int(ref))
    return qid


def _cached(engine: Engine, kind: str, ref: str) -> list[CoverCandidate] | None:
    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT response FROM app.provider_cache"
                " WHERE cache_key = :k AND expires_at > now()"
            ),
            {"k": _cache_key(kind, ref)},
        ).first()
        if row is None:
            return None
        found = [CoverCandidate(**c) for c in row[0]]
        have = {
            str(r[0])
            for r in conn.execute(
                text("SELECT id FROM geo.cover_preview WHERE id = ANY(CAST(:ids AS uuid[]))"),
                {"ids": [c.preview_id for c in found]},
            ).all()
        }
    # A preview cleaned up under a still-valid list: build the list again.
    return found if all(c.preview_id in have for c in found) else None


def _remember(engine: Engine, kind: str, ref: str, found: list[CoverCandidate]) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO app.provider_cache (cache_key, provider, response, expires_at)"
                " VALUES (:k, 'wikimedia', CAST(:r AS jsonb), now() + make_interval(days => :d))"
                " ON CONFLICT (cache_key) DO UPDATE SET response = EXCLUDED.response,"
                " fetched_at = now(), expires_at = EXCLUDED.expires_at"
            ),
            {
                "k": _cache_key(kind, ref),
                "r": json.dumps([asdict(c) for c in found]),
                "d": CACHE_DAYS,
            },
        )


def clean_previews(engine: Engine, store: ImageStore, today: date | None = None) -> int:
    """Delete previews older than a week (at most 50 a call); returns how many."""
    cutoff = (today or date.today()) - timedelta(days=CACHE_DAYS)
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT id, storage_key FROM geo.cover_preview WHERE created_date < :c"
                " ORDER BY created_date, id LIMIT 50"
            ),
            {"c": cutoff},
        ).all()
    for preview_id, key in rows:
        store.delete(key)
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM geo.cover_preview WHERE id = :id"), {"id": preview_id})
    return len(rows)


def candidate_files(client: WikimediaClient, qid: str) -> list[str]:
    """Every file the chain offers for an item, in the chain's order, without repeats."""
    entity = client.entities([qid]).get(qid)
    if entity is None:
        return []
    files: list[str] = list(entity.files)
    if entity.enwiki:
        lead = client.page_images([entity.enwiki]).get(entity.enwiki)
        if lead:
            files.append(lead)
    if entity.commons_category:
        files.extend(client.category_files(entity.commons_category, BATCH_SIZE))
    return list(dict.fromkeys(files))


def _preview(
    engine: Engine, client: WikimediaClient, store: ImageStore, info: FileInfo
) -> str | None:
    """The preview id of a file, making and storing the preview first if needed."""
    preview_id = preview_id_for(info.file)
    with engine.begin() as conn:
        if conn.execute(
            text("SELECT 1 FROM geo.cover_preview WHERE id = :id"), {"id": preview_id}
        ).first():
            return str(preview_id)
    url = info.thumb_url or info.original_url
    if url is None:
        return None
    try:
        processed = process_image(
            client.download(url), max_side=PREVIEW_WIDTH, quality=PREVIEW_QUALITY
        )
    except UndecodableImage:
        return None
    key = f"previews/{preview_id}.jpg"
    store.put(key, processed.data)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO geo.cover_preview (id, commons_file, storage_key, created_date)"
                " VALUES (:id, :f, :k, :d) ON CONFLICT (id) DO NOTHING"
            ),
            {"id": preview_id, "f": info.file, "k": key, "d": date.today()},
        )
    return str(preview_id)


def candidates_for(
    engine: Engine,
    client: WikimediaClient,
    store: ImageStore,
    kind: str,
    ref: str,
) -> list[CoverCandidate]:
    """Up to 12 photos for a destination (``city`` with a GeoNames id, or ``area``)."""
    cached = _cached(engine, kind, ref)
    if cached is not None:
        return cached
    try:
        clean_previews(engine, store)
        with engine.begin() as conn:
            qid = _qid(conn, client, kind, ref)
        if qid is None:
            _remember(engine, kind, ref, [])
            return []
        files = candidate_files(client, qid)
        found: list[CoverCandidate] = []
        for start in range(0, len(files), BATCH_SIZE):
            if len(found) >= MAX_CANDIDATES:
                break
            chunk = files[start : start + BATCH_SIZE]
            infos = client.file_infos(chunk, PREVIEW_WIDTH)
            for file in chunk:
                info = infos.get(file)
                if info is None or rejection_reason(info) is not None:
                    continue
                preview = _preview(engine, client, store, info)
                if preview is None:
                    continue
                assert info.author is not None and info.licence is not None  # noqa: S101 - gate
                found.append(
                    CoverCandidate(
                        commons_file=info.file,
                        preview_id=preview,
                        author=info.author,
                        licence=info.licence,
                        licence_url=info.licence_url,
                        source_url=info.description_url,
                        width=info.width,
                        height=info.height,
                    )
                )
                if len(found) >= MAX_CANDIDATES:
                    break
    except WikimediaError as exc:
        raise CandidatesUnavailable(str(exc)) from exc
    _remember(engine, kind, ref, found)
    return found


class ChoiceRefused(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def store_choice(
    engine: Engine,
    client: WikimediaClient,
    store: ImageStore,
    settings: Settings,
    commons_file: str,
    offered: list[CoverCandidate],
) -> uuid.UUID:
    """Store a chosen candidate as a photo and return its image id. Only a file that was offered
    for the destination can be chosen."""
    if commons_file not in {c.commons_file for c in offered}:
        raise ChoiceRefused("not_offered")
    try:
        info = client.file_infos([commons_file]).get(commons_file)
        if info is None:
            raise ChoiceRefused("not_on_commons")
        reason = rejection_reason(info)
        if reason is not None:
            raise ChoiceRefused(reason)
        qid = None
        # The image row keeps the item when it is known; a category file may have none.
        result = resolver.ensure_image(
            engine, client, store, settings, info, qid, resolver.Report()
        )
    except WikimediaError as exc:
        raise CandidatesUnavailable(str(exc)) from exc
    if result == "cap":
        raise ChoiceRefused("image_cap_reached")
    if not isinstance(result, uuid.UUID):
        raise ChoiceRefused(result)
    return result
