"""Photos that load themselves: the resolver run by the API in the background (ADR 022 amendment,
decisions k and l).

When a destination is chosen, a trip is created or its itineraries are generated, the API queues a
resolve for that trip's cities and areas and its planned places that have a Wikidata item and no
current answer. The response does not wait. Reading the trips list queues one for every trip of the
installation that still has something to look up, so a run cut short heals itself.

It is made for Render Free (512 MB, asleep when idle, restarted at any time):

* **single-flight:** a Postgres advisory lock, taken without waiting; a second request that finds
  it held simply returns, so two resolvers never run at once, even across processes;
* **idempotent and resumable:** every outcome is written to ``geo.image_lookup`` as each batch
  ends, and the candidates are exactly what has no current answer, so a restart starts again from
  what is missing;
* **small:** at most ``MAX_LOOKUPS`` lookups a run, one image in memory at a time (the resolver),
  the adapter's queue, ``maxlag``, ``Retry-After``, daily budget and the stored-image cap.

Never part of plan generation: it runs after the response has been sent.
"""

import uuid
from collections.abc import Iterable, Sequence

import httpx
import structlog
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import SQLAlchemyError

from detour_api.adapters.wikimedia import WikimediaClient
from detour_api.images import resolver
from detour_api.images.store import ImageStore
from detour_api.settings import Settings

log = structlog.get_logger("detour.images.background")

# Postgres advisory lock key of the resolver ("ADR 022" as a number); one per database.
LOCK_KEY = 22_022_022
MAX_LOOKUPS = 100

_DUE = (
    "(l.ref_id IS NULL OR (l.status <> 'found' AND l.checked_date < current_date -"
    " CASE WHEN l.reason = ANY(:short) THEN :short_days ELSE :days END))"
)
_DUE_PARAMS = {
    "days": resolver.RETRY_AFTER_DAYS,
    "short": list(resolver.SHORT_RETRY_REASONS),
    "short_days": resolver.SHORT_RETRY_DAYS,
}


def trip_candidates(conn: Connection, trip_ids: Iterable[uuid.UUID]) -> list[resolver.Candidate]:
    """What the trips still need: their destinations (a city, an area, or the stops of a multi-city
    trip) and the places planned in any of their itineraries, destinations first."""
    ids = sorted({str(t) for t in trip_ids})
    if not ids:
        return []
    out: list[resolver.Candidate] = []
    cities = conn.execute(
        text(
            "SELECT DISTINCT c.ref FROM ("
            "  SELECT t.destination_ref AS ref FROM app.trip t"
            "  WHERE t.id = ANY(CAST(:ids AS uuid[])) AND t.destination_kind <> 'area'"
            "  UNION SELECT s.city_id::text FROM app.trip_stop s"
            "  WHERE s.trip_id = ANY(CAST(:ids AS uuid[]))"
            ") c LEFT JOIN geo.image_lookup l ON l.kind = 'city' AND l.ref_id = c.ref"
            f" WHERE {_DUE} ORDER BY c.ref"
        )
        if _has_stops(conn)
        else text(
            "SELECT DISTINCT t.destination_ref FROM app.trip t"
            " LEFT JOIN geo.image_lookup l ON l.kind = 'city' AND l.ref_id = t.destination_ref"
            " WHERE t.id = ANY(CAST(:ids AS uuid[])) AND t.destination_kind = 'city'"
            f" AND {_DUE} ORDER BY 1"
        ),
        {"ids": ids, **_DUE_PARAMS},
    ).all()
    out.extend(resolver.Candidate("city", r[0], None) for r in cities)
    areas = conn.execute(
        text(
            "SELECT DISTINCT a.id::text, a.wikidata_id FROM app.trip t"
            " JOIN geo.admin_area a ON a.id::text = t.destination_ref"
            " LEFT JOIN geo.image_lookup l ON l.kind = 'area' AND l.ref_id = a.id::text"
            " WHERE t.id = ANY(CAST(:ids AS uuid[])) AND t.destination_kind = 'area'"
            f" AND a.wikidata_id IS NOT NULL AND {_DUE} ORDER BY 1"
        ),
        {"ids": ids, **_DUE_PARAMS},
    ).all()
    out.extend(resolver.Candidate("area", r[0], r[1]) for r in areas)
    places = conn.execute(
        text(
            "SELECT p.id::text, s.wikidata_id FROM geo.place p"
            " JOIN geo.place_signal s ON s.place_id = p.id"
            " LEFT JOIN geo.image_lookup l ON l.kind = 'place' AND l.ref_id = p.id::text"
            " WHERE s.wikidata_id IS NOT NULL AND p.id IN ("
            "   SELECT i.place_id FROM app.itinerary it"
            "   JOIN app.itinerary_day d ON d.itinerary_id = it.id"
            "   JOIN app.itinerary_item i ON i.day_id = d.id"
            "   WHERE it.trip_id = ANY(CAST(:ids AS uuid[])) AND i.place_id IS NOT NULL)"
            f" AND {_DUE} ORDER BY s.score DESC NULLS LAST, p.id LIMIT :n"
        ),
        {"ids": ids, "n": MAX_LOOKUPS, **_DUE_PARAMS},
    ).all()
    out.extend(resolver.Candidate("place", r[0], r[1]) for r in places)
    return out[:MAX_LOOKUPS]


def due(conn: Connection, wanted: Sequence[resolver.Candidate]) -> list[resolver.Candidate]:
    """The destinations asked for directly (a destination just chosen) that have no current
    answer. An area's Wikidata item is read from its row; an area without one is skipped."""
    out: list[resolver.Candidate] = []
    for cand in wanted:
        row = conn.execute(
            text(
                "SELECT 1 FROM (SELECT 1) x LEFT JOIN geo.image_lookup l"
                " ON l.kind = :kind AND l.ref_id = :ref"
                f" WHERE {_DUE}"
            ),
            {"kind": cand.kind, "ref": cand.ref_id, **_DUE_PARAMS},
        ).first()
        if row is None:
            continue
        if cand.kind == "area":
            qid = conn.execute(
                text("SELECT wikidata_id FROM geo.admin_area WHERE id::text = :r"),
                {"r": cand.ref_id},
            ).scalar()
            if qid is None:
                continue
            cand = resolver.Candidate("area", cand.ref_id, str(qid))
        out.append(cand)
    return out


def _has_stops(conn: Connection) -> bool:
    """Whether the multi-city table exists yet (ADR 024, migration 0012)."""
    return bool(conn.execute(text("SELECT to_regclass('app.trip_stop') IS NOT NULL")).scalar())


def installation_trips(conn: Connection, installation_id: uuid.UUID) -> list[uuid.UUID]:
    rows = conn.execute(
        text(
            "SELECT id FROM app.trip WHERE installation_id = :i AND status = 'active' ORDER BY id"
        ),
        {"i": installation_id},
    ).all()
    return [r[0] for r in rows]


def resolve_trips(
    engine: Engine,
    settings: Settings,
    store: ImageStore,
    trip_ids: Sequence[uuid.UUID],
    transport: httpx.BaseTransport | None = None,
    extra: Sequence[resolver.Candidate] = (),
) -> resolver.Report | None:
    """One background run for these trips. ``None`` when another run holds the lock, when nothing
    is due, or when the adapter is off; failures are logged, never raised (the caller's response
    has already been sent)."""
    try:
        with engine.connect() as lock_conn:
            got = lock_conn.execute(
                text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_KEY}
            ).scalar()
            if not got:
                return None
            try:
                with engine.begin() as conn:
                    both = due(conn, extra) + trip_candidates(conn, trip_ids)
                    seen: set[tuple[str, str]] = set()
                    candidates = []
                    for c in both:
                        if (c.kind, c.ref_id) not in seen:
                            seen.add((c.kind, c.ref_id))
                            candidates.append(c)
                if not candidates:
                    return None
                client = WikimediaClient(settings, engine, transport)
                if not client.enabled:
                    return None
                report = resolver.resolve(engine, client, store, settings, candidates)
                log.info("background_resolve", trips=len(trip_ids), **report.as_dict())
                return report
            finally:
                lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_KEY})
                lock_conn.commit()
    except SQLAlchemyError as exc:
        log.warning("background_resolve_failed", error=type(exc).__name__)
        return None
