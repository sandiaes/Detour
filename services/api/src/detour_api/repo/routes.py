"""Checking the stops of a multi-city trip against the imported data (ADR 024, decisions 4 to 7).

Used when a trip is created and when its stops are edited. Every refusal is a fixed code:

* ``route_needs_two_stops`` / ``too_many_stops`` (422): 2 to 6 stops;
* ``stop_days_mismatch`` (422): the stops' days must add up to the trip's length;
* ``stop_repeated`` (422): two consecutive stops are the same city (it may come back later);
* ``destination_not_found`` (422): a stop is not a city of the gazetteer;
* ``region_not_available`` (409, as for a single destination): a stop is outside the regions that
  are available for planning. The message names the stop's position.
"""

from collections.abc import Sequence

from sqlalchemy import Connection, text

from detour_api.errors import ApiError, invalid
from detour_api.models.trips import MAX_STOPS, MIN_STOPS, StopIn
from detour_api.naming import route_name
from detour_api.repo import geo
from detour_api.repo.trips import ResolvedStop


def resolve_stops(
    conn: Connection, stops: Sequence[StopIn], duration_days: int | None
) -> tuple[list[ResolvedStop], str]:
    """The checked stops with their snapshots, and the trip's name. ``duration_days`` None: the
    trip's length becomes the sum of the stops' days (a stop edit)."""
    if len(stops) < MIN_STOPS:
        raise invalid(
            "route_needs_two_stops", "a multi-city trip has at least two cities; use a city trip"
        )
    if len(stops) > MAX_STOPS:
        raise invalid("too_many_stops", f"a multi-city trip has at most {MAX_STOPS} cities")
    total = sum(s.days for s in stops)
    if total > 30:
        raise invalid("stop_days_mismatch", "a trip has at most 30 days")
    if duration_days is not None and total != duration_days:
        raise invalid(
            "stop_days_mismatch",
            f"the cities' days add up to {total}, but the trip has {duration_days}",
        )
    for i in range(1, len(stops)):
        if stops[i].city_id == stops[i - 1].city_id:
            raise invalid(
                "stop_repeated",
                f"cities {i} and {i + 1} are the same; give that city more days instead",
            )
    out: list[ResolvedStop] = []
    for position, stop in enumerate(stops, start=1):
        dest = geo.resolve_destination(conn, "city", str(stop.city_id))
        if dest is None:
            raise invalid("destination_not_found", f"city {position} is not in the imported data")
        if dest.region_id is None or dest.region_status != "available":
            raise ApiError(
                409,
                "region_not_available",
                f"city {position} ({dest.name}) is outside the regions that are available for "
                "planning",
            )
        out.append(
            ResolvedStop(stop.city_id, dest.name, dest.country_iso2, dest.lat, dest.lon, stop.days)
        )
    return out, name_for(conn, out)


def name_for(conn: Connection, stops: Sequence[ResolvedStop]) -> str:
    codes = sorted({s.country_iso2 for s in stops if s.country_iso2})
    rows = conn.execute(
        text("SELECT iso2, name FROM geo.country WHERE iso2 = ANY(:c)"), {"c": codes}
    ).all()
    return route_name(
        [s.name for s in stops], [s.country_iso2 for s in stops], {r.iso2: r.name for r in rows}
    )
