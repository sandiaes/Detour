"""Photo fields in the API (ADR 022, step 3): a trip's cover and an item's image."""

import uuid
from typing import Any

import psycopg
import pytest

from detour_api.images.resolver import image_id_for
from tests.conftest import ApiEnv
from tests.test_api_trips import add_item, find_place, make_itinerary, make_trip

pytestmark = pytest.mark.db

CITY_REF = "900101"  # the fixture city every test trip uses


def _sql(env: ApiEnv, query: str, *params: Any) -> list[tuple[Any, ...]]:
    with psycopg.connect(env.database_url, autocommit=True) as conn:
        cur = conn.execute(query, params)
        return cur.fetchall() if cur.description else []


def _image(env: ApiEnv, name: str, **over: Any) -> uuid.UUID:
    image_id = image_id_for(name)
    row = {
        "author": "Jane Doe",
        "licence": "CC BY-SA 4.0",
        "licence_url": "https://creativecommons.org/licenses/by-sa/4.0",
        **over,
    }
    _sql(
        env,
        "INSERT INTO geo.image (id, source, commons_file, source_url, author, licence, licence_url,"
        " width, height, bytes, color, storage_key, fetched_date) VALUES (%s, 'wikimedia_commons',"
        " %s, %s, %s, %s, %s, 1080, 720, 150000, '#336699', %s, current_date)",
        image_id,
        name,
        f"https://commons.wikimedia.org/wiki/File:{name}",
        row["author"],
        row["licence"],
        row["licence_url"],
        f"{image_id}.jpg",
    )
    return image_id


def _found(env: ApiEnv, kind: str, ref: str, image_id: uuid.UUID) -> None:
    _sql(
        env,
        "INSERT INTO geo.image_lookup (kind, ref_id, status, image_id, checked_date)"
        " VALUES (%s, %s, 'found', %s, current_date)",
        kind,
        ref,
        image_id,
    )


def _trip(env: ApiEnv) -> dict[str, Any]:
    r = env.client.get("/v1/trips", headers=env.headers)
    return next(t for t in r.json() if t["destination"]["ref"] == CITY_REF)


def test_a_trip_has_no_cover_until_a_photo_is_found_for_its_city(api_env: ApiEnv) -> None:
    trip = make_trip(api_env)
    assert trip["cover_image"] is None
    assert _trip(api_env)["cover_image"] is None


def test_the_cover_is_the_photo_found_for_the_destination_city(api_env: ApiEnv) -> None:
    trip = make_trip(api_env)
    image_id = _image(api_env, "City.jpg")
    _found(api_env, "city", CITY_REF, image_id)
    for body in (
        api_env.client.get(f"/v1/trips/{trip['id']}", headers=api_env.headers).json(),
        _trip(api_env),
    ):
        cover = body["cover_image"]
        assert cover["id"] == str(image_id)
        assert cover["url"] == f"/v1/images/{image_id}"  # a path on this API, never Wikimedia's
        assert (cover["color"], cover["width"], cover["height"]) == ("#336699", 1080, 720)
        assert cover["credit"] == {
            "author": "Jane Doe",
            "licence": "CC BY-SA 4.0",
            "licence_url": "https://creativecommons.org/licenses/by-sa/4.0",
            "source_url": "https://commons.wikimedia.org/wiki/File:City.jpg",
            "text": "Photo: Jane Doe, CC BY-SA 4.0, Wikimedia Commons (resized)",
        }


def test_the_chosen_photo_wins_and_a_hidden_one_is_never_shown(api_env: ApiEnv) -> None:
    trip = make_trip(api_env)
    automatic = _image(api_env, "Auto.jpg")
    chosen = _image(api_env, "Chosen.jpg")
    _found(api_env, "city", CITY_REF, automatic)
    _sql(api_env, "UPDATE app.trip SET cover_image_id = %s WHERE id = %s", chosen, trip["id"])

    def cover() -> Any:
        return _trip(api_env)["cover_image"]

    assert cover()["id"] == str(chosen)
    _sql(api_env, "UPDATE geo.image SET hidden = true WHERE id = %s", chosen)
    assert cover()["id"] == str(automatic)  # the chosen one is gone: back to the automatic photo
    _sql(api_env, "UPDATE geo.image SET hidden = true WHERE id = %s", automatic)
    assert cover() is None


def test_a_trip_to_an_area_has_no_automatic_photo(api_env: ApiEnv) -> None:
    image_id = _image(api_env, "Area.jpg")
    _found(api_env, "city", CITY_REF, image_id)
    area = _sql(api_env, "SELECT id FROM geo.admin_area LIMIT 1")
    if not area:
        pytest.skip("the fixture region has no area")
    body = {"title": "Area", "destination_kind": "area", "destination_ref": str(area[0][0])}
    r = api_env.client.post("/v1/trips", json={**body, "duration_days": 2}, headers=api_env.headers)
    assert r.status_code == 201, r.text
    assert r.json()["cover_image"] is None


def test_an_item_of_an_imported_place_carries_its_photo(api_env: ApiEnv) -> None:
    it = make_itinerary(api_env, make_trip(api_env))
    museum = find_place(api_env, "testburg museum")
    image_id = _image(api_env, "Museum.jpg")
    _found(api_env, "place", museum["id"], image_id)
    added = add_item(
        api_env,
        it,
        1,
        type="visit",
        place_id=museum["id"],
        duration_minutes=60,
        start_time="10:00:00",
    )
    assert added.status_code == 201, added.text
    assert added.json()["image"]["id"] == str(image_id)  # the response to adding has it too
    item_id = added.json()["id"]

    day_items = api_env.client.get(f"/v1/itineraries/{it['id']}", headers=api_env.headers).json()[
        "days"
    ][0]["items"]
    shown = next(i for i in day_items if i["id"] == item_id)
    assert shown["image"]["id"] == str(image_id)
    assert shown["image"]["credit"]["text"].startswith("Photo: Jane Doe, CC BY-SA 4.0")

    single = api_env.client.get(f"/v1/items/{item_id}", headers=api_env.headers)
    assert single.status_code == 200
    assert single.json()["image"]["id"] == str(image_id)

    _sql(api_env, "UPDATE geo.image SET hidden = true WHERE id = %s", image_id)
    again = api_env.client.get(f"/v1/itineraries/{it['id']}", headers=api_env.headers).json()
    assert next(i for i in again["days"][0]["items"] if i["id"] == item_id)["image"] is None
