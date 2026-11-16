"""Album links and trip files on the server (ADR 034, step 5).

Album links are shared by everyone on the trip; the album itself is never read (ADR 031). A cover
chosen from a phone is re-encoded here as a JPEG of at most ``cover_max_side`` pixels (EXIF
orientation applied, metadata such as the location dropped), kept in the private ``trip-files``
bucket and served only to the trip's members. The bytes in the bucket are counted against a budget
(``trip_files_budget_bytes``); objects whose row went away are removed after the change commits.
"""

import base64
import binascii
import hashlib
import io
import json
import uuid
from datetime import datetime
from typing import Any

import structlog
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import Connection, Engine, text

from detour_api.errors import ApiError, conflict, invalid, not_found
from detour_api.images.store import ImageStore, StoreError
from detour_api.models.trips import (
    OwnCover,
    TripAlbum,
    TripDocumentFields,
    TripDocumentInfo,
    TripDocumentUpload,
)
from detour_api.repo import trips
from detour_api.settings import Settings

log = structlog.get_logger("detour.trip_files")

MAX_ALBUMS = 20
# A picture larger than this many pixels is refused before it is decoded (a "zip bomb" picture).
MAX_PIXELS = 60_000_000


# -- albums -------------------------------------------------------------------------------------


def normalise_url(raw: str) -> str:
    """The link alone: words around a pasted share message are dropped; only https is kept."""
    for word in raw.split():
        if word.startswith("https://") and len(word) <= 2000:
            return word.rstrip(".,;)")
    raise invalid("album_url", "paste the album's share link; it starts with https://")


def list_albums(conn: Connection, person_id: uuid.UUID, trip_id: uuid.UUID) -> list[TripAlbum]:
    trips.require_trip(conn, person_id, trip_id)
    rows = conn.execute(
        text(
            "SELECT a.id, a.name, a.url, a.created_at, p.display_name FROM app.trip_album a"
            " LEFT JOIN app.person p ON p.id = a.added_by"
            " WHERE a.trip_id = :t ORDER BY a.created_at, a.id"
        ),
        {"t": trip_id},
    ).all()
    return [
        TripAlbum(id=r.id, name=r.name, url=r.url, added_by=r.display_name, created_at=r.created_at)
        for r in rows
    ]


def add_album(
    conn: Connection, person_id: uuid.UUID, trip_id: uuid.UUID, url: str, name: str | None
) -> TripAlbum:
    """Links are allowed on past trips too (photos come after the journey; ADR 006)."""
    trips.require_trip(conn, person_id, trip_id)
    clean = normalise_url(url)
    count = conn.execute(
        text("SELECT count(*) FROM app.trip_album WHERE trip_id = :t"), {"t": trip_id}
    ).scalar_one()
    if count >= MAX_ALBUMS:
        raise conflict("limit_reached", f"a trip can have up to {MAX_ALBUMS} albums")
    album_id = uuid.uuid4()
    added = conn.execute(
        text(
            "INSERT INTO app.trip_album (id, trip_id, url, name, added_by)"
            " VALUES (:i, :t, :u, :n, :p) ON CONFLICT (trip_id, url) DO NOTHING RETURNING 1"
        ),
        {
            "i": album_id,
            "t": trip_id,
            "u": clean,
            "n": " ".join((name or "").split())[:80] or "Trip album",
            "p": person_id,
        },
    ).first()
    if added is None:
        raise conflict("album_exists", "this album is already linked to the trip")
    return next(a for a in list_albums(conn, person_id, trip_id) if a.id == album_id)


def rename_album(
    conn: Connection, person_id: uuid.UUID, trip_id: uuid.UUID, album_id: uuid.UUID, name: str
) -> TripAlbum:
    trips.require_trip(conn, person_id, trip_id)
    done = conn.execute(
        text("UPDATE app.trip_album SET name = :n WHERE id = :a AND trip_id = :t RETURNING 1"),
        {"n": " ".join(name.split())[:80], "a": album_id, "t": trip_id},
    ).first()
    if done is None:
        raise not_found("album")
    return next(a for a in list_albums(conn, person_id, trip_id) if a.id == album_id)


def remove_album(
    conn: Connection, person_id: uuid.UUID, trip_id: uuid.UUID, album_id: uuid.UUID
) -> None:
    trips.require_trip(conn, person_id, trip_id)
    done = conn.execute(
        text("DELETE FROM app.trip_album WHERE id = :a AND trip_id = :t RETURNING 1"),
        {"a": album_id, "t": trip_id},
    ).first()
    if done is None:
        raise not_found("album")


# -- covers -------------------------------------------------------------------------------------


def reencode_cover(data: bytes, max_side: int) -> bytes:
    """A JPEG of at most ``max_side`` pixels on its longer side, upright, without metadata."""
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.width * image.height > MAX_PIXELS:
                raise invalid("picture_too_large", "this picture has too many pixels")
            image.load()
            upright = ImageOps.exif_transpose(image) or image
            rgb = upright.convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise invalid("not_a_picture", "this file is not a JPEG, PNG or WebP picture") from None
    rgb.thumbnail((max_side, max_side))
    out = io.BytesIO()
    rgb.save(out, format="JPEG", quality=85, optimize=True)  # no exif: no location is kept
    return out.getvalue()


def _used_bytes(conn: Connection) -> int:
    used: int = conn.execute(text("SELECT coalesce(sum(bytes), 0) FROM app.trip_file")).scalar_one()
    return used


def set_own_cover(
    conn: Connection,
    store: ImageStore | None,
    settings: Settings,
    person_id: uuid.UUID,
    trip_id: uuid.UUID,
    encoded: str,
) -> OwnCover:
    """Store a cover chosen on a phone for everyone on the trip. The previous one, if any, is
    replaced (its object is removed after the change commits)."""
    trips.require_trip(conn, person_id, trip_id)
    if store is None:
        raise ApiError(503, "storage_unavailable", "pictures cannot be stored on this server")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise invalid("not_a_picture", "the picture is not valid base64") from None
    if len(raw) > settings.cover_upload_max_bytes:
        raise invalid(
            "picture_too_large",
            f"a cover can be at most {settings.cover_upload_max_bytes // 1_000_000} MB",
        )
    jpeg = reencode_cover(raw, settings.cover_max_side)
    if _used_bytes(conn) + len(jpeg) > settings.trip_files_budget_bytes:
        raise conflict("storage_full", "the server's space for trip files is full")
    file_id = uuid.uuid4()
    key = f"trips/{trip_id}/cover-{file_id}.jpg"
    try:
        store.put(key, jpeg, "image/jpeg")
    except StoreError as exc:
        raise ApiError(503, "storage_unavailable", "the picture could not be stored") from exc
    conn.execute(
        text("DELETE FROM app.trip_file WHERE trip_id = :t AND kind = 'cover'"), {"t": trip_id}
    )
    created: datetime = conn.execute(
        text(
            "INSERT INTO app.trip_file (id, trip_id, kind, storage_key, content_type, bytes,"
            " sha256, uploaded_by) VALUES (:i, :t, 'cover', :k, 'image/jpeg', :b, :h, :p)"
            " RETURNING created_at"
        ),
        {
            "i": file_id,
            "t": trip_id,
            "k": key,
            "b": len(jpeg),
            "h": hashlib.sha256(jpeg).digest(),
            "p": person_id,
        },
    ).scalar_one()
    # A changed cover is a change to the trip (who did it is recorded, ADR 034 step 4).
    conn.execute(text("UPDATE app.trip SET updated_at = now() WHERE id = :t"), {"t": trip_id})
    return OwnCover(id=file_id, bytes=len(jpeg), uploaded_at=created)


def get_own_cover(
    conn: Connection, store: ImageStore | None, person_id: uuid.UUID, trip_id: uuid.UUID
) -> tuple[uuid.UUID, bytes]:
    trips.require_trip(conn, person_id, trip_id)
    row = conn.execute(
        text("SELECT id, storage_key FROM app.trip_file WHERE trip_id = :t AND kind = 'cover'"),
        {"t": trip_id},
    ).first()
    if row is None:
        raise not_found("cover")
    if store is None:
        raise ApiError(503, "storage_unavailable", "pictures cannot be read on this server")
    try:
        data = store.get(row.storage_key)
    except StoreError as exc:
        raise ApiError(503, "storage_unavailable", "the picture could not be read") from exc
    if data is None:
        raise not_found("cover")
    return row.id, data


def clear_own_cover(conn: Connection, person_id: uuid.UUID, trip_id: uuid.UUID) -> None:
    trips.require_trip(conn, person_id, trip_id)
    gone = conn.execute(
        text("DELETE FROM app.trip_file WHERE trip_id = :t AND kind = 'cover' RETURNING 1"),
        {"t": trip_id},
    ).first()
    if gone is None:
        raise not_found("cover")
    conn.execute(text("UPDATE app.trip SET updated_at = now() WHERE id = :t"), {"t": trip_id})


def sweep_orphans(engine: Engine | None, store: ImageStore | None, limit: int = 50) -> int:
    """Remove from the bucket the objects whose row is gone (a replaced cover, a deleted trip).
    Best effort, after the change committed: what fails stays listed for the next sweep."""
    if engine is None or store is None:
        return 0
    with engine.begin() as conn:
        keys = (
            conn.execute(
                text("SELECT storage_key FROM app.trip_file_orphan ORDER BY created_at LIMIT :n"),
                {"n": limit},
            )
            .scalars()
            .all()
        )
    removed = 0
    for key in keys:
        try:
            store.delete(key)
        except StoreError:
            log.warning("orphan_delete_failed")
            continue
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM app.trip_file_orphan WHERE storage_key = :k"), {"k": key}
            )
        removed += 1
    return removed


# -- shared documents (ADR 034, step 6) ---------------------------------------------------------

# What the first bytes of each accepted kind look like. Documents are kept as they are (a ticket's
# QR code must not be re-encoded), so the check is on the bytes, not on what the phone says.
_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    "application/pdf": (b"%PDF-",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/gif": (b"GIF87a", b"GIF89a"),
}

_DOCUMENT_COLUMNS = """
    d.id, d.title, d.category, d.link, d.doc_date, d.notes, d.file_name, d.updated_at,
    f.content_type, f.bytes, f.created_at, p.display_name
"""
_DOCUMENT_FROM = """
    FROM app.trip_document d JOIN app.trip_file f ON f.id = d.id
    LEFT JOIN app.person p ON p.id = f.uploaded_by
"""


def _looks_like(content_type: str, data: bytes) -> bool:
    if content_type in _SIGNATURES:
        return data.startswith(_SIGNATURES[content_type])
    if content_type == "image/webp":
        return data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    if content_type in ("image/heic", "image/heif"):
        return data[4:8] == b"ftyp"
    return False


def _document(row: Any) -> TripDocumentInfo:
    return TripDocumentInfo(
        id=row.id,
        title=row.title,
        category=row.category,
        link=row.link,
        date=row.doc_date,
        notes=row.notes,
        file_name=row.file_name,
        content_type=row.content_type,
        bytes=row.bytes,
        added_by=row.display_name,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def list_documents(
    conn: Connection, person_id: uuid.UUID, trip_id: uuid.UUID
) -> list[TripDocumentInfo]:
    trips.require_trip(conn, person_id, trip_id)
    rows = conn.execute(
        text(
            f"SELECT {_DOCUMENT_COLUMNS} {_DOCUMENT_FROM}"
            " WHERE d.trip_id = :t ORDER BY f.created_at, d.id"
        ),
        {"t": trip_id},
    ).all()
    return [_document(r) for r in rows]


def _require_document(
    conn: Connection, trip_id: uuid.UUID, document_id: uuid.UUID
) -> TripDocumentInfo:
    row = conn.execute(
        text(f"SELECT {_DOCUMENT_COLUMNS} {_DOCUMENT_FROM} WHERE d.id = :d AND d.trip_id = :t"),
        {"d": document_id, "t": trip_id},
    ).first()
    if row is None:
        raise not_found("document")
    return _document(row)


def _link_json(link: Any) -> str:
    return json.dumps(link.model_dump(mode="json"))


def add_document(
    conn: Connection,
    store: ImageStore | None,
    settings: Settings,
    person_id: uuid.UUID,
    trip_id: uuid.UUID,
    body: TripDocumentUpload,
) -> TripDocumentInfo:
    """Share a document with everyone on the trip. Allowed on past trips (ADR 006). Sending the
    same id again returns what is stored, so a retried upload does not store it twice."""
    trips.require_trip(conn, person_id, trip_id)
    existing = conn.execute(
        text("SELECT trip_id FROM app.trip_file WHERE id = :i"), {"i": body.id}
    ).first()
    if existing is not None:
        if existing.trip_id != trip_id:
            raise conflict("document_exists", "this document belongs to another trip")
        return _require_document(conn, trip_id, body.id)
    if store is None:
        raise ApiError(503, "storage_unavailable", "documents cannot be stored on this server")
    try:
        raw = base64.b64decode(body.data, validate=True)
    except (binascii.Error, ValueError):
        raise invalid("not_a_document", "the file is not valid base64") from None
    if len(raw) > settings.document_upload_max_bytes:
        raise invalid(
            "document_too_large",
            f"a document can be at most {settings.document_upload_max_bytes // 1_000_000} MB",
        )
    if not _looks_like(body.content_type, raw):
        raise invalid("not_a_document", "this file is not a PDF or a picture of the kind it says")
    if _used_bytes(conn) + len(raw) > settings.trip_files_budget_bytes:
        raise conflict("storage_full", "the server's space for trip files is full")
    key = f"trips/{trip_id}/document-{body.id}"
    try:
        store.put(key, raw, body.content_type)
    except StoreError as exc:
        raise ApiError(503, "storage_unavailable", "the document could not be stored") from exc
    conn.execute(
        text(
            "INSERT INTO app.trip_file (id, trip_id, kind, storage_key, content_type, bytes,"
            " sha256, uploaded_by) VALUES (:i, :t, 'document', :k, :c, :b, :h, :p)"
        ),
        {
            "i": body.id,
            "t": trip_id,
            "k": key,
            "c": body.content_type,
            "b": len(raw),
            "h": hashlib.sha256(raw).digest(),
            "p": person_id,
        },
    )
    conn.execute(
        text(
            "INSERT INTO app.trip_document (id, trip_id, title, category, link, doc_date, notes,"
            " file_name, updated_by) VALUES (:i, :t, :title, :cat, CAST(:link AS jsonb), :date,"
            " :notes, :name, :p)"
        ),
        {
            "i": body.id,
            "t": trip_id,
            "title": body.title.strip(),
            "cat": body.category,
            "link": _link_json(body.link),
            "date": body.date,
            "notes": (body.notes or "").strip() or None,
            "name": body.file_name,
            "p": person_id,
        },
    )
    return _require_document(conn, trip_id, body.id)


def update_document(
    conn: Connection,
    person_id: uuid.UUID,
    trip_id: uuid.UUID,
    document_id: uuid.UUID,
    body: TripDocumentFields,
) -> TripDocumentInfo:
    trips.require_trip(conn, person_id, trip_id)
    _require_document(conn, trip_id, document_id)
    conn.execute(
        text(
            "UPDATE app.trip_document SET title = :title, category = :cat,"
            " link = CAST(:link AS jsonb), doc_date = :date, notes = :notes, updated_by = :p,"
            " updated_at = now() WHERE id = :d"
        ),
        {
            "title": body.title.strip(),
            "cat": body.category,
            "link": _link_json(body.link),
            "date": body.date,
            "notes": (body.notes or "").strip() or None,
            "p": person_id,
            "d": document_id,
        },
    )
    return _require_document(conn, trip_id, document_id)


def remove_document(
    conn: Connection, person_id: uuid.UUID, trip_id: uuid.UUID, document_id: uuid.UUID
) -> None:
    """For everyone on the trip; the phones that kept a copy drop it at their next sync."""
    trips.require_trip(conn, person_id, trip_id)
    gone = conn.execute(
        text(
            "DELETE FROM app.trip_file WHERE id = :d AND trip_id = :t AND kind = 'document'"
            " RETURNING 1"
        ),
        {"d": document_id, "t": trip_id},
    ).first()
    if gone is None:
        raise not_found("document")


def get_document_file(
    conn: Connection,
    store: ImageStore | None,
    person_id: uuid.UUID,
    trip_id: uuid.UUID,
    document_id: uuid.UUID,
) -> tuple[str, bytes]:
    trips.require_trip(conn, person_id, trip_id)
    row = conn.execute(
        text(
            "SELECT storage_key, content_type FROM app.trip_file"
            " WHERE id = :d AND trip_id = :t AND kind = 'document'"
        ),
        {"d": document_id, "t": trip_id},
    ).first()
    if row is None:
        raise not_found("document")
    if store is None:
        raise ApiError(503, "storage_unavailable", "documents cannot be read on this server")
    try:
        data = store.get(row.storage_key)
    except StoreError as exc:
        raise ApiError(503, "storage_unavailable", "the document could not be read") from exc
    if data is None:
        raise not_found("document")
    return row.content_type, data
