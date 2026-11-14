import uuid
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Request, Response
from sqlalchemy import text

from detour_api.adapters.wikimedia import WikimediaClient
from detour_api.deps import DatabaseDep, SessionDep
from detour_api.errors import ApiError
from detour_api.images.candidates import CandidatesUnavailable, candidates_for
from detour_api.images.queue import queue_resolve
from detour_api.images.store import StoreError
from detour_api.models.images import CoverCandidate, PhotoCredit
from detour_api.repo import geo
from detour_api.repo.images import credit_text
from detour_api.routers.responses import ERRORS

router = APIRouter(prefix="/v1", tags=["images"])

# The stored file never changes under its id, so it may be cached for a year (ADR 022, decision 8).
CACHE_CONTROL = "public, max-age=31536000, immutable"


@router.get(
    "/images/{image_id}",
    summary="The stored photo, streamed by the backend so the app never calls Supabase.",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}}}},
)
def get_image(image_id: uuid.UUID, db: DatabaseDep, request: Request) -> Response:
    with db.tx() as conn:
        row = conn.execute(
            text("SELECT storage_key FROM geo.image WHERE id = :id AND NOT hidden"),
            {"id": image_id},
        ).first()
    store = request.app.state.image_store
    if row is None:
        raise ApiError(404, "image_not_found", "no such image")
    if store is None:
        raise ApiError(503, "images_unavailable", "photo storage is not configured")
    try:
        data = store.get(row[0])
    except StoreError as exc:
        raise ApiError(503, "images_unavailable", "photo storage is unavailable") from exc
    if data is None:
        raise ApiError(404, "image_not_found", "no such image")
    return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": CACHE_CONTROL})


@router.get(
    "/cover-previews/{preview_id}",
    summary="A small preview of a cover candidate, streamed by the backend.",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}}}},
)
def get_cover_preview(preview_id: uuid.UUID, db: DatabaseDep, request: Request) -> Response:
    with db.tx() as conn:
        row = conn.execute(
            text("SELECT storage_key FROM geo.cover_preview WHERE id = :id"), {"id": preview_id}
        ).first()
    store = request.app.state.image_store
    if row is None:
        raise ApiError(404, "image_not_found", "no such preview")
    if store is None:
        raise ApiError(503, "images_unavailable", "photo storage is not configured")
    try:
        data = store.get(row[0])
    except StoreError as exc:
        raise ApiError(503, "images_unavailable", "photo storage is unavailable") from exc
    if data is None:
        raise ApiError(404, "image_not_found", "no such preview")
    # A preview lives a week at most; it is never changed under its id.
    return Response(
        content=data, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"}
    )


@router.get(
    "/destinations/{kind}/{ref}/cover-candidates",
    summary="Up to 12 freely licensed photos of a destination to choose a cover from "
    "(Wikimedia Commons, through the backend). Also starts looking up its automatic photo.",
    responses=ERRORS,
)
def list_cover_candidates(
    session: SessionDep,
    request: Request,
    background: BackgroundTasks,
    kind: Literal["city", "area"],
    ref: str,
) -> list[CoverCandidate]:
    with session.tx() as conn:
        dest = geo.resolve_destination(conn, kind, ref)
    if dest is None:
        raise ApiError(404, "destination_not_found", "no such city or area in the imported data")
    state = request.app.state
    if state.image_store is None or state.engine is None:
        raise ApiError(503, "images_unavailable", "photo storage is not configured")
    client = WikimediaClient(state.settings, state.engine, state.wikimedia_transport)
    if not client.enabled:
        raise ApiError(503, "images_unavailable", "the photo source is switched off")
    try:
        found = candidates_for(state.engine, client, state.image_store, kind, ref)
    except (CandidatesUnavailable, StoreError) as exc:
        raise ApiError(503, "images_unavailable", "the photo source cannot be reached") from exc
    queue_resolve(request, background, destinations=[(kind, ref)])
    return [
        CoverCandidate(
            commons_file=c.commons_file,
            preview_url=f"/v1/cover-previews/{c.preview_id}",
            width=c.width,
            height=c.height,
            credit=PhotoCredit(
                author=c.author,
                licence=c.licence,
                licence_url=c.licence_url,
                source_url=c.source_url,
                text=credit_text(c.author, c.licence),
            ),
        )
        for c in found
    ]
