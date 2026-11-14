"""The trip file (ADR 028): what a trip looks like outside the app.

Everything here is the user's own record, as snapshots: names, points, times and lengths. No
identifier of ours is exported, so a file imports into any installation after any re-import of the
data. ``format_version`` is a promise: version 1 keeps importing.
"""

from datetime import date, datetime, time
from typing import Literal

from pydantic import Field

from detour_api.models.common import Latitude, Longitude, StrictModel

FORMAT: Literal["detour-trip"] = "detour-trip"
FORMAT_VERSION = 1
MAX_TRIPS_PER_FILE = 100
MAX_DAYS = 30
MAX_ITEMS_PER_DAY = 40
MAX_VISITS = 1500

StopKind = Literal["sight", "city", "place", "restaurant", "cafe"]
VisitKind = Literal["city", "attraction", "restaurant", "cafe"]
DestinationKind = Literal["city", "area", "route", "place"]


class FileDestination(StrictModel):
    kind: DestinationKind = Field(description="What it was in the app; it imports as a place")
    ref: str | None = Field(
        default=None,
        max_length=64,
        description="A provider reference (photon:N123, geonames:123, area:<uuid>) when known",
    )
    name: str = Field(min_length=1, max_length=200)
    lat: Latitude
    lon: Longitude
    country_iso2: str | None = Field(default=None, pattern="^[A-Za-z]{2}$")


class FileStop(StrictModel):
    """A city of a multi-city trip, kept for reference (it imports as a single place trip)."""

    name: str = Field(min_length=1, max_length=200)
    lat: Latitude
    lon: Longitude
    days: int = Field(ge=1, le=30)
    country_iso2: str | None = Field(default=None, pattern="^[A-Za-z]{2}$")


class FileItem(StrictModel):
    position: int = Field(ge=1, le=MAX_ITEMS_PER_DAY)
    kind: StopKind
    name: str = Field(min_length=1, max_length=200)
    lat: Latitude
    lon: Longitude
    start_time: time | None = None
    duration_minutes: int = Field(ge=1, le=1440)
    duration_is_user: bool = False
    locked: bool = False


class FileDay(StrictModel):
    day_index: int = Field(ge=1, le=MAX_DAYS)
    base_city_name: str | None = Field(default=None, max_length=200)
    items: list[FileItem] = Field(default_factory=list, max_length=MAX_ITEMS_PER_DAY)


class FileVisit(StrictModel):
    """One row of a past trip's day record."""

    kind: VisitKind
    name: str = Field(min_length=1, max_length=200)
    lat: Latitude
    lon: Longitude
    day_number: int = Field(ge=1, le=MAX_DAYS)
    position: int | None = Field(default=None, ge=1)
    start_time: time | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    confirmed: bool = True


class FileTrip(StrictModel):
    title: str = Field(min_length=1, max_length=120)
    destination: FileDestination
    duration_days: int = Field(ge=1, le=MAX_DAYS)
    start_date: date | None = None
    status: Literal["active", "past"] = "active"
    archived_at: datetime | None = None
    stops: list[FileStop] = Field(default_factory=list, max_length=6)
    days: list[FileDay] = Field(
        default_factory=list, max_length=MAX_DAYS, description="The chosen plan; empty if none"
    )
    visits: list[FileVisit] = Field(default_factory=list, max_length=MAX_VISITS)


class TripFile(StrictModel):
    """The contents of ``trip.json`` inside a ``.detour`` file."""

    format: Literal["detour-trip"] = FORMAT
    format_version: int = Field(ge=1, description="Refused when higher than the server knows")
    exported_at: datetime | None = None
    trips: list[FileTrip] = Field(max_length=MAX_TRIPS_PER_FILE)


class ImportedTrip(StrictModel):
    index: int = Field(description="Position of the trip in the file, from 0")
    trip_id: str
    title: str
    days: int = Field(description="Days with at least one stop")
    stops: int


class ImportResult(StrictModel):
    trips: list[ImportedTrip]
