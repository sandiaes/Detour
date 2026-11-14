"""Reading and writing names in the database (ADR 025).

Reads never call a provider: they combine the names the import holds (OpenStreetMap, GeoNames),
the stored Wikidata names (expired ones too: a cached name is better than none while Wikidata is
unreachable) and the caller's own override, and resolve them in Python. A place that was never
enriched still gets its best name from its own data.
"""

import uuid
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Connection, text

from detour_api.names import config
from detour_api.names.records import (
    NameRecord,
    geonames_records,
    osm_records,
    override_record,
    stored_record,
)
from detour_api.names.resolver import ResolvedName, resolve
from detour_api.textnorm import normalize_text

WIKIDATA_LICENCE = "CC0-1.0"

_STORED = """
    (SELECT coalesce(jsonb_agg(jsonb_build_object(
        'name', n.name, 'lang', n.lang, 'name_type', n.name_type, 'source', n.source,
        'step', n.step, 'source_ref', n.source_ref, 'confidence', n.confidence,
        'official', n.official) ORDER BY n.source DESC, n.lang, n.name_norm), '[]'::jsonb)
     FROM geo.place_name n WHERE n.entity_kind = '{kind}' AND n.entity_ref = {ref})
"""
_OVERRIDE = """
    (SELECT o.name FROM app.place_name_override o WHERE o.installation_id = CAST(:inst AS uuid)
     AND o.entity_kind = '{kind}' AND o.entity_ref = {ref})
"""


def stored_sql(kind: str, ref_sql: str) -> str:
    """A SQL expression: the stored names of one entity as a JSON array."""
    return _STORED.format(kind=kind, ref=ref_sql)


def override_sql(kind: str, ref_sql: str) -> str:
    """A SQL expression: the override of the installation bound as ``:inst`` (null if none)."""
    return _OVERRIDE.format(kind=kind, ref=ref_sql)


def _stored_records(stored: Any) -> list[NameRecord]:
    return [stored_record(row) for row in (stored or []) if isinstance(row, dict)]


def place_records(
    *,
    name: str | None,
    names_i18n: dict[str, str] | None,
    tags: dict[str, Any] | None,
    stored: Any,
    override: str | None,
    source_ref: str | None = None,
) -> list[NameRecord]:
    out: list[NameRecord] = []
    if override:
        out.append(override_record(override))
    out += _stored_records(stored)
    out += osm_records(name, names_i18n, tags, source_ref=source_ref)
    return out


def resolve_place_row(row: Any) -> ResolvedName:
    """Resolve a row that has ``id``, ``kind``, ``category``, ``name``, ``names_i18n`` and,
    optionally, ``tags``, ``stored`` and ``override`` (see ``PLACE_NAME_COLUMNS``)."""
    get = row._mapping.get if hasattr(row, "_mapping") else row.get
    records = place_records(
        name=get("name"),
        names_i18n=get("names_i18n"),
        tags=get("tags"),
        stored=get("stored"),
        override=get("override"),
    )
    return resolve(
        records,
        place_class=config.place_class(get("kind"), get("category")),
        place_ref=str(get("id")),
    )


# Columns to add to a query over ``geo.place p`` so that resolve_place_row can read the row. Bind
# ``:inst`` (an installation id, or None for no override).
PLACE_NAME_COLUMNS = (
    "(SELECT ps.tags FROM geo.place_source ps WHERE ps.place_id = p.id AND ps.source = 'osm'"
    " ORDER BY ps.source_ref LIMIT 1) AS tags, "
    + stored_sql("place", "p.id::text")
    + " AS stored, "
    + override_sql("place", "p.id::text")
    + " AS override"
)


def resolve_places(
    conn: Connection, place_ids: Iterable[uuid.UUID], installation_id: uuid.UUID | None = None
) -> dict[uuid.UUID, ResolvedName]:
    ids = sorted({str(i) for i in place_ids})
    if not ids:
        return {}
    rows = conn.execute(
        text(
            "SELECT p.id, p.kind, p.category, p.name, p.names_i18n, "
            + PLACE_NAME_COLUMNS
            + " FROM geo.place p WHERE p.id = ANY(CAST(:ids AS uuid[]))"
        ),
        {"ids": ids, "inst": _inst(installation_id)},
    ).all()
    return {r.id: resolve_place_row(r) for r in rows}


def resolve_cities(
    conn: Connection, city_ids: Iterable[int], installation_id: uuid.UUID | None = None
) -> dict[int, ResolvedName]:
    ids = sorted({int(i) for i in city_ids})
    if not ids:
        return {}
    rows = conn.execute(
        text(
            "SELECT c.id, c.name, c.ascii_name, "
            + stored_sql("city", "c.id::text")
            + " AS stored, "
            + override_sql("city", "c.id::text")
            + " AS override FROM geo.city c WHERE c.id = ANY(:ids)"
        ),
        {"ids": ids, "inst": _inst(installation_id)},
    ).all()
    out: dict[int, ResolvedName] = {}
    for r in rows:
        records: list[NameRecord] = [override_record(r.override)] if r.override else []
        records += _stored_records(r.stored) + geonames_records(r.name, r.ascii_name, r.id)
        out[r.id] = resolve(records, place_class="settlement", place_ref=f"city/{r.id}")
    return out


def _inst(installation_id: uuid.UUID | None) -> str | None:
    return str(installation_id) if installation_id is not None else None


# -- writing ------------------------------------------------------------------------------------


def write_names(
    conn: Connection, kind: str, ref: str, records: Sequence[NameRecord], now: datetime
) -> int:
    """Replace the stored Wikidata and Wikipedia names of one entity. Dedupe follows the primary
    key (entity, language, source, normalised value); the first record of a key wins. The best
    stored display candidate is marked preferred."""
    conn.execute(
        text(
            "DELETE FROM geo.place_name WHERE entity_kind = :k AND entity_ref = :r"
            " AND source IN ('wikidata', 'enwiki')"
        ),
        {"k": kind, "r": ref},
    )
    rows: dict[tuple[str, str, str], dict[str, Any]] = {}
    for record in records:
        norm = record.name_norm[:300]
        key = (record.lang, record.source, norm)
        if not norm or key in rows:
            continue
        rows[key] = {
            "k": kind,
            "r": ref,
            "lang": record.lang,
            "script": record.script if record.script and len(record.script) == 4 else None,
            "name": record.name[:300],
            "norm": norm,
            "type": record.name_type,
            "source": record.source,
            "step": record.step,
            "ref": (record.source_ref or "")[:330] or None,
            "lic": WIKIDATA_LICENCE,
            "conf": round(record.confidence, 2),
            "official": record.official,
            "preferred": False,
            "retrieved": record.retrieved_at or now,
            "expires": record.expires_at,
        }
    display = sorted(
        (r for r in rows.values() if r["step"] in config.STEP_ORDER),
        key=lambda r: config.STEP_ORDER[r["step"]],
    )
    if display:
        display[0]["preferred"] = True
    if rows:
        conn.execute(
            text(
                "INSERT INTO geo.place_name (entity_kind, entity_ref, lang, script, name,"
                " name_norm, name_type, source, step, source_ref, licence_code, confidence,"
                " official, is_preferred, retrieved_at, expires_at) VALUES (:k, :r, :lang,"
                " :script, :name, :norm, :type, :source, :step, :ref, :lic, :conf, :official,"
                " :preferred, :retrieved, :expires)"
            ),
            list(rows.values()),
        )
    return len(rows)


def record_lookup(
    conn: Connection,
    kind: str,
    ref: str,
    *,
    qid: str | None,
    status: str,
    reason: str | None,
    now: datetime,
    retry_days: int = config.NEGATIVE_RETRY_DAYS,
) -> None:
    conn.execute(
        text(
            "INSERT INTO geo.place_name_lookup (entity_kind, entity_ref, source, qid, status,"
            " reason, checked_at, retry_after) VALUES (:k, :r, 'wikidata', :q, :s, :why, :now,"
            " :now + make_interval(days => :days))"
            " ON CONFLICT (entity_kind, entity_ref, source) DO UPDATE SET qid = EXCLUDED.qid,"
            " status = EXCLUDED.status, reason = EXCLUDED.reason, checked_at = EXCLUDED.checked_at,"
            " retry_after = EXCLUDED.retry_after"
        ),
        {"k": kind, "r": ref, "q": qid, "s": status, "why": reason, "now": now, "days": retry_days},
    )


# -- user overrides -----------------------------------------------------------------------------


def set_override(
    conn: Connection,
    installation_id: uuid.UUID,
    kind: str,
    ref: str,
    name: str,
    original_name: str | None,
) -> None:
    """Approve a display name for one place for this installation. Only the matched entity is
    affected; the original name is kept beside it. Item snapshots of the installation's plans that
    name the place are updated, as a user-place rename is."""
    clean = " ".join(name.split())
    conn.execute(
        text(
            "INSERT INTO app.place_name_override (installation_id, entity_kind, entity_ref, name,"
            " name_norm, original_name, approved_at) VALUES (:i, :k, :r, :n, :norm, :orig, now())"
            " ON CONFLICT (installation_id, entity_kind, entity_ref) DO UPDATE SET"
            " name = EXCLUDED.name, name_norm = EXCLUDED.name_norm, approved_at = now()"
        ),
        {
            "i": installation_id,
            "k": kind,
            "r": ref,
            "n": clean,
            "norm": normalize_text(clean),
            "orig": original_name[:300] if original_name else None,
        },
    )
    if kind == "place":
        _update_snapshots(conn, installation_id, uuid.UUID(ref), clean)


def delete_override(conn: Connection, installation_id: uuid.UUID, kind: str, ref: str) -> bool:
    """Undo an override; the item snapshots go back to the resolved name."""
    deleted = conn.execute(
        text(
            "DELETE FROM app.place_name_override WHERE installation_id = :i AND entity_kind = :k"
            " AND entity_ref = :r"
        ),
        {"i": installation_id, "k": kind, "r": ref},
    ).rowcount
    if deleted and kind == "place":
        resolved = resolve_places(conn, [uuid.UUID(ref)], installation_id).get(uuid.UUID(ref))
        if resolved is not None and resolved.display:
            _update_snapshots(conn, installation_id, uuid.UUID(ref), resolved.display)
    return bool(deleted)


def _update_snapshots(
    conn: Connection, installation_id: uuid.UUID, place_id: uuid.UUID, name: str
) -> None:
    conn.execute(
        text(
            "UPDATE app.itinerary_item i SET display_name = :n FROM app.itinerary_day d,"
            " app.itinerary it, app.trip t WHERE i.day_id = d.id AND d.itinerary_id = it.id"
            " AND it.trip_id = t.id AND t.installation_id = :inst AND i.place_id = :p"
            " AND i.display_name IS DISTINCT FROM :n"
        ),
        {"n": name[:200], "inst": installation_id, "p": place_id},
    )
    conn.execute(
        text(
            "UPDATE app.trip_visit v SET name = :n FROM app.trip t WHERE v.trip_id = t.id"
            " AND t.installation_id = :inst AND v.geo_place_ref = :p AND v.name IS DISTINCT FROM :n"
        ),
        {"n": name[:200], "inst": installation_id, "p": str(place_id)},
    )


def apply_overrides_to_trip(
    conn: Connection, installation_id: uuid.UUID, trip_id: uuid.UUID
) -> None:
    """Write the installation's approved display names into a trip's item snapshots."""
    conn.execute(
        text(
            "UPDATE app.itinerary_item i SET display_name = o.name FROM app.itinerary_day d,"
            " app.itinerary it, app.place_name_override o WHERE i.day_id = d.id"
            " AND d.itinerary_id = it.id AND it.trip_id = :t AND o.installation_id = :inst"
            " AND o.entity_kind = 'place' AND o.entity_ref = i.place_id::text"
            " AND i.display_name IS DISTINCT FROM o.name"
        ),
        {"t": trip_id, "inst": installation_id},
    )


# -- retention ----------------------------------------------------------------------------------

# What in ``app`` keeps an entity's stored names: itinerary items (proposals and selected plans),
# past-trip visits, and a trip's cities and areas.
_REFERENCED = {
    "place": (
        "EXISTS (SELECT 1 FROM app.itinerary_item i WHERE i.place_id::text = n.entity_ref)"
        " OR EXISTS (SELECT 1 FROM app.trip_visit v WHERE v.geo_place_ref = n.entity_ref)"
        " OR EXISTS (SELECT 1 FROM app.place_name_override o WHERE o.entity_kind = 'place'"
        "   AND o.entity_ref = n.entity_ref)"
    ),
    "city": (
        "EXISTS (SELECT 1 FROM app.trip t WHERE t.destination_kind IN ('city', 'route')"
        "   AND t.destination_ref = n.entity_ref)"
        " OR EXISTS (SELECT 1 FROM app.trip_stop s WHERE s.city_id::text = n.entity_ref)"
        " OR EXISTS (SELECT 1 FROM app.itinerary_day d WHERE d.base_city_id::text = n.entity_ref)"
    ),
    "area": (
        "EXISTS (SELECT 1 FROM app.trip t WHERE t.destination_kind = 'area'"
        "   AND t.destination_ref = n.entity_ref)"
    ),
}
_EXISTS = {
    "place": "EXISTS (SELECT 1 FROM geo.place p WHERE p.id::text = n.entity_ref)",
    "city": "EXISTS (SELECT 1 FROM geo.city c WHERE c.id::text = n.entity_ref)",
    "area": "EXISTS (SELECT 1 FROM geo.admin_area a WHERE a.id::text = n.entity_ref)",
}


def prune(conn: Connection, now: datetime | None = None) -> dict[str, int]:
    """Delete stored names that expired and that nothing in the app names any more, and the names
    and lookups of entities that are gone from ``geo``. Referenced names are kept for good (until
    the reference goes) and refreshed when their lookup is due."""
    moment = now or datetime.now(UTC)
    removed = {"expired": 0, "orphaned_names": 0, "orphaned_lookups": 0}
    for kind in ("place", "city", "area"):
        removed["expired"] += conn.execute(
            text(
                f"DELETE FROM geo.place_name n WHERE n.entity_kind = :k AND n.expires_at < :now"
                f" AND NOT ({_REFERENCED[kind]})"
            ),
            {"k": kind, "now": moment},
        ).rowcount
        removed["orphaned_names"] += conn.execute(
            text(f"DELETE FROM geo.place_name n WHERE n.entity_kind = :k AND NOT {_EXISTS[kind]}"),
            {"k": kind},
        ).rowcount
        removed["orphaned_lookups"] += conn.execute(
            text(
                f"DELETE FROM geo.place_name_lookup n WHERE n.entity_kind = :k"
                f" AND NOT {_EXISTS[kind]}"
            ),
            {"k": kind},
        ).rowcount
    return removed
