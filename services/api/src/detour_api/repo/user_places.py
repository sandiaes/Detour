"""User places: places the user added that are not in ``geo.place``."""

import uuid
from typing import Any

from sqlalchemy import Connection, text

from detour_api.errors import conflict, not_found
from detour_api.models.trips import UserPlace, UserPlaceCreate, UserPlaceUpdate

MAX_USER_PLACES = 500
_COLUMNS = (
    "id, kind, name, ST_Y(geom) AS lat, ST_X(geom) AS lon, cuisines, meal_types, source,"
    " search_provider, search_ref, created_at, updated_at"
)


def _place(row: Any) -> UserPlace:
    return UserPlace(
        id=row.id,
        kind=row.kind,
        name=row.name,
        lat=row.lat,
        lon=row.lon,
        cuisines=None if row.cuisines is None else list(row.cuisines),
        meal_types=None if row.meal_types is None else list(row.meal_types),
        source=row.source,
        search_provider=row.search_provider,
        search_ref=row.search_ref,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def get(conn: Connection, installation_id: uuid.UUID, place_id: uuid.UUID) -> UserPlace | None:
    row = conn.execute(
        text(f"SELECT {_COLUMNS} FROM app.user_place WHERE id = :i AND installation_id = :n"),
        {"i": place_id, "n": installation_id},
    ).first()
    return None if row is None else _place(row)


def require(conn: Connection, installation_id: uuid.UUID, place_id: uuid.UUID) -> UserPlace:
    place = get(conn, installation_id, place_id)
    if place is None:
        raise not_found("user place")
    return place


def list_all(
    conn: Connection, installation_id: uuid.UUID, kind: str | None = None
) -> list[UserPlace]:
    rows = conn.execute(
        text(
            f"SELECT {_COLUMNS} FROM app.user_place WHERE installation_id = :n"
            " AND (CAST(:k AS text) IS NULL OR kind = :k) ORDER BY created_at, id"
        ),
        {"n": installation_id, "k": kind},
    ).all()
    return [_place(r) for r in rows]


def create(conn: Connection, installation_id: uuid.UUID, body: UserPlaceCreate) -> UserPlace:
    count = conn.execute(
        text("SELECT count(*) FROM app.user_place WHERE installation_id = :n"),
        {"n": installation_id},
    ).scalar_one()
    if count >= MAX_USER_PLACES:
        raise conflict("limit_reached", f"at most {MAX_USER_PLACES} user places per installation")
    place_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO app.user_place (id, installation_id, kind, name, geom, cuisines,"
            " meal_types, source, search_provider, search_ref) VALUES (:id, :n, :kind, :name,"
            " ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), :cuisines, :meals, :source, :prov, :ref)"
        ),
        {
            "id": place_id,
            "n": installation_id,
            "kind": body.kind,
            "name": body.name,
            "lon": body.lon,
            "lat": body.lat,
            "cuisines": body.cuisines,
            "meals": body.meal_types,
            "source": body.source,
            "prov": body.search_provider,
            "ref": body.search_ref,
        },
    )
    return require(conn, installation_id, place_id)


def update(
    conn: Connection, installation_id: uuid.UUID, place_id: uuid.UUID, body: UserPlaceUpdate
) -> UserPlace:
    current = require(conn, installation_id, place_id)
    changed = body.model_fields_set
    if (
        current.kind != "restaurant"
        and ({"cuisines", "meal_types"} & changed)
        and (body.cuisines or body.meal_types)
    ):
        raise conflict("not_a_restaurant", "cuisines and meal_types are only for restaurants")
    sets: list[str] = []
    params: dict[str, Any] = {"i": place_id, "n": installation_id}
    if "name" in changed and body.name is not None:
        sets.append("name = :name")
        params["name"] = body.name
    if body.lat is not None and body.lon is not None:
        sets.append("geom = ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)")
        params.update(lat=body.lat, lon=body.lon)
    if "cuisines" in changed:
        sets.append("cuisines = :cuisines")
        params["cuisines"] = body.cuisines
    if "meal_types" in changed:
        sets.append("meal_types = :meals")
        params["meals"] = body.meal_types
    if sets:
        conn.execute(
            text(
                f"UPDATE app.user_place SET {', '.join(sets)}, updated_at = now() WHERE id = :i AND installation_id = :n"
            ),
            params,
        )
        # Items keep a snapshot of the name and point; keep it in step with the user's own place.
        conn.execute(
            text(
                "UPDATE app.itinerary_item i SET display_name = up.name, display_point = up.geom,"
                " updated_at = now() FROM app.user_place up WHERE up.id = i.user_place_id"
                " AND up.id = :i"
            ),
            {"i": place_id},
        )
    return require(conn, installation_id, place_id)


def delete(conn: Connection, installation_id: uuid.UUID, place_id: uuid.UUID) -> None:
    require(conn, installation_id, place_id)
    used = conn.execute(
        text("SELECT 1 FROM app.itinerary_item WHERE user_place_id = :i LIMIT 1"), {"i": place_id}
    ).first()
    if used:
        raise conflict("in_use", "the place is used by an itinerary item; remove the item first")
    conn.execute(
        text("DELETE FROM app.user_place WHERE id = :i AND installation_id = :n"),
        {"i": place_id, "n": installation_id},
    )
