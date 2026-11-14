import uuid

from fastapi import APIRouter, Request, Response
from sqlalchemy import text

from detour_api.deps import DatabaseDep
from detour_api.errors import ApiError
from detour_api.images.store import StoreError

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
