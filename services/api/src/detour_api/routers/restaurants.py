"""Adding a restaurant (Phase 8, ADR 019): search (local data, then Photon through the backend).
Manual entry is a user place of kind restaurant (``POST /v1/user-places``); the user chooses its day
and time (``POST /v1/itineraries/{id}/days/{n}/items``). The slot suggestions of Phase 8 were
retired by ADR 026; the local-data search goes with the imported restaurants (ADR 026, step 3)."""

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import text

from detour_api.adapters.photon import PhotonOutcome
from detour_api.deps import SessionDep
from detour_api.errors import invalid, not_found
from detour_api.importer.derive import MEAL_TYPES_BY_VENUE
from detour_api.models.restaurants import (
    ExternalRestaurant,
    ExternalRestaurantStatus,
    RestaurantResult,
    RestaurantSearchResponse,
)
from detour_api.repo import geo, user_places
from detour_api.routers.responses import ERRORS

router = APIRouter(prefix="/v1", tags=["restaurants"])

Q = Annotated[str, Query(min_length=2, max_length=100)]
# The venue types the import knows, and the OSM tags Photon is asked for.
PHOTON_VENUES = ("restaurant", "cafe")
PHOTON_TAGS = tuple(f"amenity:{v}" for v in PHOTON_VENUES)
MAX_OWN = 20


def _external(outcome: PhotonOutcome) -> ExternalRestaurantStatus:
    results: list[ExternalRestaurant] = []
    for r in outcome.results:
        # The tag filter may be ignored by the server: keep only restaurants and cafés.
        if r.osm_key != "amenity" or r.osm_value not in PHOTON_VENUES:
            continue
        results.append(
            ExternalRestaurant(
                ref=r.ref,
                name=r.name,
                lat=r.lat,
                lon=r.lon,
                osm_key=r.osm_key,
                osm_value=r.osm_value,
                country_code=r.country_code,
                country=r.country,
                state=r.state,
                city=r.city,
                street=r.street,
                housenumber=r.housenumber,
                postcode=r.postcode,
                venue_type=r.osm_value,
                meal_types=list(MEAL_TYPES_BY_VENUE[r.osm_value]),
            )
        )
    return ExternalRestaurantStatus(state=outcome.state, provider="photon", results=results)


@router.get(
    "/restaurants/search",
    summary="Search restaurants: imported places first, then your saved restaurants and, when "
    "nothing matches and asked for, Photon through the backend (cached, budgeted).",
    responses=ERRORS,
)
def search_restaurants(
    session: SessionDep,
    q: Q,
    region: Annotated[str | None, Query(max_length=60)] = None,
    lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    lon: Annotated[float | None, Query(ge=-180, le=180)] = None,
    radius_m: Annotated[float | None, Query(gt=0, le=50_000)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    include_external: Annotated[bool, Query()] = False,
    lang: Annotated[str | None, Query(pattern="^[a-z]{2}$")] = None,
) -> RestaurantSearchResponse:
    if (lat is None) != (lon is None):
        raise invalid("lat_lon_together", "lat and lon must be given together")
    if radius_m is not None and lat is None:
        raise invalid("radius_needs_point", "radius_m needs lat and lon")
    country_codes: tuple[str, ...] = ()
    with session.tx() as conn:
        if region is not None:
            row = conn.execute(
                text("SELECT country_codes FROM geo.region WHERE id = :r"), {"r": region}
            ).first()
            if row is None:
                raise not_found("region")
            country_codes = tuple(row.country_codes)
        found = geo.search_places(
            conn,
            query=q,
            region=region,
            kind="restaurant",
            category=None,
            lat=lat,
            lon=lon,
            radius_m=radius_m,
            limit=limit,
            installation_id=session.installation_id,
        )
        meals = {
            str(r.place_id): list(r.meal_types)
            for r in conn.execute(
                text(
                    "SELECT place_id, meal_types FROM geo.restaurant_profile"
                    " WHERE place_id = ANY(CAST(:ids AS uuid[])) AND meal_types IS NOT NULL"
                ),
                {"ids": [str(f.id) for f in found]},
            )
        }
        needle = " ".join(q.casefold().split())
        own = [
            p
            for p in user_places.list_all(conn, session.installation_id, kind="restaurant")
            if needle in p.name.casefold()
        ][:MAX_OWN]
    results = [RestaurantResult(**f.model_dump(), meal_types=meals.get(str(f.id))) for f in found]
    if found or own:
        external = ExternalRestaurantStatus(
            state="not_needed" if include_external else "not_requested"
        )
    elif include_external:
        external = _external(
            session.photon.search(
                q,
                limit=min(limit, 10),
                lang=lang,
                country_codes=country_codes,
                lat=lat,
                lon=lon,
                osm_tags=PHOTON_TAGS,
            )
        )
    else:
        external = ExternalRestaurantStatus(state="not_requested")
    return RestaurantSearchResponse(query=q, results=results, your_places=own, external=external)
