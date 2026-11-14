"""Adding a restaurant or cafe (ADR 019, ADR 026): search the user's saved places, then Photon
through the backend. Restaurants and cafes are not imported. Manual entry is a user place of kind
restaurant or cafe (``POST /v1/user-places``); the user chooses its day and time
(``POST /v1/itineraries/{id}/days/{n}/items``)."""

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import text

from detour_api.adapters.photon import PhotonOutcome
from detour_api.deps import SessionDep
from detour_api.errors import invalid, not_found
from detour_api.models.restaurants import (
    ExternalRestaurant,
    ExternalRestaurantStatus,
    RestaurantSearchResponse,
)
from detour_api.repo import user_places
from detour_api.routers.responses import ERRORS

router = APIRouter(prefix="/v1", tags=["restaurants"])

Q = Annotated[str, Query(min_length=2, max_length=100)]
# The OSM tags Photon is asked for.
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
            )
        )
    return ExternalRestaurantStatus(state=outcome.state, provider="photon", results=results)


@router.get(
    "/restaurants/search",
    summary="Search restaurants and cafes: your saved places first and, when nothing matches and "
    "asked for, Photon through the backend (cached, budgeted).",
    responses=ERRORS,
)
def search_restaurants(
    session: SessionDep,
    q: Q,
    region: Annotated[str | None, Query(max_length=60)] = None,
    lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    lon: Annotated[float | None, Query(ge=-180, le=180)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    include_external: Annotated[bool, Query()] = False,
    lang: Annotated[str | None, Query(pattern="^[a-z]{2}$")] = None,
) -> RestaurantSearchResponse:
    if (lat is None) != (lon is None):
        raise invalid("lat_lon_together", "lat and lon must be given together")
    country_codes: tuple[str, ...] = ()
    with session.tx() as conn:
        if region is not None:
            row = conn.execute(
                text("SELECT country_codes FROM geo.region WHERE id = :r"), {"r": region}
            ).first()
            if row is None:
                raise not_found("region")
            country_codes = tuple(row.country_codes)
        needle = " ".join(q.casefold().split())
        own = [
            p
            for p in user_places.list_all(conn, session.installation_id)
            if p.kind in PHOTON_VENUES and needle in p.name.casefold()
        ][:MAX_OWN]
    if own:
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
    return RestaurantSearchResponse(query=q, your_places=own, external=external)
