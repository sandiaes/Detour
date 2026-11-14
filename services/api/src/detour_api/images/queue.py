"""Queueing the background photo resolve (ADR 022 amendment, decision k) and the background name
enrichment (ADR 025) from a request.

A queued run starts after the response has been sent (FastAPI background tasks run in a worker
thread). Nothing is queued when storage or the adapter is off, or in tests without a recorded
transport (the adapter itself refuses then).
"""

import uuid
from collections.abc import Iterable

from fastapi import BackgroundTasks, Request

from detour_api.images import background as bg
from detour_api.images import resolver
from detour_api.names import background as names_bg


def queue_resolve(
    request: Request,
    tasks: BackgroundTasks,
    *,
    trip_ids: Iterable[uuid.UUID] = (),
    destinations: Iterable[tuple[str, str]] = (),
) -> None:
    state = request.app.state
    trips = list(trip_ids)
    if state.engine is None or not state.settings.wikimedia_enabled:
        return
    if trips:
        # English names first: they are a few small requests, independent of photo storage.
        tasks.add_task(
            names_bg.enrich_trips, state.engine, state.settings, trips, state.wikimedia_transport
        )
    if state.image_store is None:
        return
    extra = [_destination(kind, ref) for kind, ref in destinations]
    tasks.add_task(
        bg.resolve_trips,
        state.engine,
        state.settings,
        state.image_store,
        trips,
        state.wikimedia_transport,
        [c for c in extra if c is not None],
    )


def _destination(kind: str, ref: str) -> resolver.Candidate | None:
    if kind == "city" and ref.isdigit():
        return resolver.Candidate("city", ref, None)
    if kind == "area":
        return resolver.Candidate("area", ref, None)  # its item is read from the area row
    return None
