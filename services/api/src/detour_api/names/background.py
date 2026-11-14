"""Names that resolve themselves: the Wikidata enrichment run by the API in the background
(ADR 025), after a trip is created, its itineraries are generated or the trips are read.

Like the photo resolver (``images/background.py``): single-flight under its own Postgres advisory
lock, resumable (every outcome is stored as each batch ends), at most ``MAX_ENTITIES`` a run,
through the same Wikimedia queue, budget and backoff. The response never waits for it, so trip
generation is never blocked: until it has run, places show the best name their own data gives.
"""

import uuid
from collections.abc import Sequence

import httpx
import structlog
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from detour_api.adapters.wikimedia import WikimediaClient
from detour_api.names import enrich
from detour_api.settings import Settings

log = structlog.get_logger("detour.names.background")

LOCK_KEY = 25_025_025  # "ADR 025"; one per database
MAX_ENTITIES = 100


def enrich_trips(
    engine: Engine,
    settings: Settings,
    trip_ids: Sequence[uuid.UUID],
    transport: httpx.BaseTransport | None = None,
) -> enrich.Report | None:
    """One background run for these trips. ``None`` when another run holds the lock, nothing is
    due or the adapter is off. Failures are logged, never raised."""
    client = WikimediaClient(settings, engine, transport)
    if not client.enabled:
        return None
    try:
        with engine.connect() as lock_conn:
            got = lock_conn.execute(
                text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_KEY}
            ).scalar()
            if not got:
                return None
            try:
                entities = enrich.trip_entities(engine, trip_ids, MAX_ENTITIES)
                if not entities:
                    return None
                report = enrich.enrich(engine, client, entities)
                log.info("background_names", trips=len(trip_ids), **report.as_dict(10))
                return report
            finally:
                lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_KEY})
                lock_conn.commit()
    except SQLAlchemyError as exc:
        log.warning("background_names_failed", error=type(exc).__name__)
        return None
