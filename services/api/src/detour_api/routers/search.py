"""Destination search and local place search. External search (Photon) only on request, only
when the local data has no answer, and never for a request that is not authenticated."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import text

from detour_api.adapters.photon import PhotonOutcome
from detour_api.deps import SessionDep
from detour_api.errors import ApiError, invalid, not_found
from detour_api.models.common import DisplayNameUpdate, PlaceName
from detour_api.models.search import (
    DestinationSearchResponse,
    ExternalPlace,
    ExternalStatus,
    PlaceDetail,
    PlaceSearchResponse,
)
from detour_api.names import store as names_store
from detour_api.names.api import to_api
from detour_api.repo import geo
from detour_api.routers.responses import AUTH, ERRORS

router = APIRouter(prefix="/v1", tags=["search"])

Q = Annotated[str, Query(min_length=2, max_length=100)]
Limit = Annotated[int, Query(ge=1, le=50)]
Lang = Annotated[
    str | None, Query(pattern="^[a-z]{2}$", description="Result language for external search")
]
DESTINATION_LAYERS = ("city", "locality", "county", "state")


def _external(outcome: PhotonOutcome) -> ExternalStatus:
    return ExternalStatus(
        state=outcome.state,
        provider="photon",
        results=[
            ExternalPlace(
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
            )
            for r in outcome.results
        ],
    )


@router.get(
    "/destinations/search",
    summary="Search cities and areas (provinces, regions) in the imported data.",
    responses=AUTH,
)
def search_destinations(
    session: SessionDep,
    q: Q,
    limit: Limit = 10,
    include_external: Annotated[
        bool,
        Query(description="If nothing is found locally, ask Photon (through the backend, cached)"),
    ] = False,
    lang: Lang = None,
) -> DestinationSearchResponse:
    with session.tx() as conn:
        results = geo.search_destinations(conn, q, limit)
    external = ExternalStatus(state="not_requested")
    if include_external:
        if results:
            external = ExternalStatus(state="not_needed")
        else:
            external = _external(
                session.photon.search(q, limit=min(limit, 10), lang=lang, layers=DESTINATION_LAYERS)
            )
    return DestinationSearchResponse(query=q, results=results, external=external)


@router.get(
    "/places/search",
    summary="Search places by name and/or around a point in the imported data.",
    responses=ERRORS,
)
def search_places(
    session: SessionDep,
    q: Annotated[str | None, Query(min_length=2, max_length=100)] = None,
    region: Annotated[str | None, Query(max_length=60)] = None,
    kind: Annotated[str | None, Query(pattern="^(attraction|transport_hub|other)$")] = None,
    category: Annotated[str | None, Query(max_length=60)] = None,
    lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    lon: Annotated[float | None, Query(ge=-180, le=180)] = None,
    radius_m: Annotated[float | None, Query(gt=0, le=50_000)] = None,
    limit: Limit = 10,
    include_external: Annotated[bool, Query()] = False,
    lang: Lang = None,
) -> PlaceSearchResponse:
    if (lat is None) != (lon is None):
        raise invalid("lat_lon_together", "lat and lon must be given together")
    if radius_m is not None and lat is None:
        raise invalid("radius_needs_point", "radius_m needs lat and lon")
    if q is None and lat is None:
        raise invalid("query_required", "give q, or lat and lon, or both")
    country_codes: tuple[str, ...] = ()
    with session.tx() as conn:
        if region is not None:
            row = conn.execute(
                text("SELECT country_codes FROM geo.region WHERE id = :r"), {"r": region}
            ).first()
            if row is None:
                raise not_found("region")
            country_codes = tuple(row.country_codes)
        results = geo.search_places(
            conn,
            query=q,
            region=region,
            kind=kind,
            category=category,
            lat=lat,
            lon=lon,
            radius_m=radius_m,
            limit=limit,
            installation_id=session.installation_id,
        )
    external = ExternalStatus(state="not_requested")
    if include_external:
        if q is None:
            raise invalid("query_required", "external search needs q")
        if results:
            external = ExternalStatus(state="not_needed")
        else:
            external = _external(
                session.photon.search(
                    q,
                    limit=min(limit, 10),
                    lang=lang,
                    country_codes=country_codes,
                    lat=lat,
                    lon=lon,
                )
            )
    return PlaceSearchResponse(query=q, results=results, external=external)


@router.get(
    "/places/{place_id}",
    summary="One imported place with its provenance (source records and licences).",
    responses=ERRORS,
)
def get_place(session: SessionDep, place_id: uuid.UUID) -> PlaceDetail:
    with session.tx() as conn:
        place = geo.get_place(conn, place_id, session.installation_id)
    if place is None:
        raise ApiError(404, "not_found", "place not found")
    return place


@router.put(
    "/places/{place_id}/display-name",
    summary="Approve a display name for this one place (Edit display name, ADR 025).",
    responses=ERRORS,
)
def set_display_name(
    session: SessionDep, place_id: uuid.UUID, body: DisplayNameUpdate
) -> PlaceName:
    """The name takes precedence over every provider name for this installation, for this place
    only (similarly named places are not affected). The original name is kept and shown beside
    it, and the itinerary items that name the place follow. Undo with DELETE."""
    with session.tx() as conn:
        place = geo.get_place(conn, place_id, session.installation_id)
        if place is None:
            raise ApiError(404, "not_found", "place not found")
        names_store.set_override(
            conn, session.installation_id, "place", str(place_id), body.name, place.name
        )
        resolved = names_store.resolve_places(conn, [place_id], session.installation_id)
    return to_api(resolved[place_id])


@router.delete(
    "/places/{place_id}/display-name",
    summary="Undo an approved display name: the resolved name comes back.",
    responses=ERRORS,
)
def delete_display_name(session: SessionDep, place_id: uuid.UUID) -> PlaceName:
    with session.tx() as conn:
        if not names_store.delete_override(conn, session.installation_id, "place", str(place_id)):
            raise not_found("display name")
        resolved = names_store.resolve_places(conn, [place_id], session.installation_id)
    if place_id not in resolved:
        raise ApiError(404, "not_found", "place not found")
    return to_api(resolved[place_id])
