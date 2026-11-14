"""Reading stored photos for trips and places (ADR 022). Only reads; the resolver writes."""

import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import Connection, text

from detour_api.models.images import Photo, PhotoCredit

_COLUMNS = ("id", "color", "width", "height", "author", "licence", "licence_url", "source_url")


def _select(table: str, prefix: str) -> str:
    """The photo columns of ``table`` under the aliases ``<prefix><column>``."""
    return ", ".join(f"{table}.{c} AS {prefix}{c}" for c in _COLUMNS)


def credit_text(author: str, licence: str) -> str:
    """The credit line, from one fixed template (no generated text)."""
    return f"Photo: {author}, {licence}, Wikimedia Commons (resized)"


def photo(row: Any, prefix: str = "") -> Photo:
    def col(name: str) -> Any:
        return getattr(row, f"{prefix}{name}")

    return Photo(
        id=col("id"),
        url=f"/v1/images/{col('id')}",
        color=col("color"),
        width=col("width"),
        height=col("height"),
        credit=PhotoCredit(
            author=col("author"),
            licence=col("licence"),
            licence_url=col("licence_url"),
            source_url=col("source_url"),
            text=credit_text(col("author"), col("licence")),
        ),
    )


def trip_covers(conn: Connection, trip_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, Photo]:
    """The cover of each trip: the photo the user chose (``app.trip.cover_image_id``), else the
    photo found for its destination city. A hidden photo is never used; a trip with neither has no
    entry. Area destinations have no automatic photo yet (the areas carry no Wikidata item)."""
    ids = list(trip_ids)
    if not ids:
        return {}
    rows = conn.execute(
        text(
            f"SELECT t.id AS trip_id, {_select('ce', 'c_')}, {_select('ca', 'a_')}"
            " FROM app.trip t"
            " LEFT JOIN geo.image ce ON ce.id = t.cover_image_id AND NOT ce.hidden"
            " LEFT JOIN geo.image_lookup l ON l.kind = 'city' AND t.destination_kind = 'city'"
            "   AND l.ref_id = t.destination_ref AND l.status = 'found'"
            " LEFT JOIN geo.image ca ON ca.id = l.image_id AND NOT ca.hidden"
            " WHERE t.id = ANY(:ids)"
        ),
        {"ids": ids},
    ).all()
    out: dict[uuid.UUID, Photo] = {}
    for r in rows:
        if r.c_id is not None:
            out[r.trip_id] = photo(r, "c_")
        elif r.a_id is not None:
            out[r.trip_id] = photo(r, "a_")
    return out


def place_photos(conn: Connection, place_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, Photo]:
    """The photo found for each imported place, if any (hidden photos are left out)."""
    ids = sorted({str(p) for p in place_ids})
    if not ids:
        return {}
    rows = conn.execute(
        text(
            f"SELECT l.ref_id, {_select('i', '')} FROM geo.image_lookup l"
            " JOIN geo.image i ON i.id = l.image_id AND NOT i.hidden"
            " WHERE l.kind = 'place' AND l.status = 'found' AND l.ref_id = ANY(:ids)"
        ),
        {"ids": ids},
    ).all()
    return {uuid.UUID(r.ref_id): photo(r) for r in rows}
