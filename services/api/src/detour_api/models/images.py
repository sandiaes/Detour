"""Photo fields shared by trips and itinerary items (ADR 022)."""

import uuid

from pydantic import BaseModel, Field


class PhotoCredit(BaseModel):
    """What the licence requires the app to show next to a photo."""

    author: str
    licence: str = Field(description="Short licence name, for example CC BY-SA 4.0")
    licence_url: str | None
    source_url: str = Field(description="The file's page on Wikimedia Commons")
    text: str = Field(description="The credit line, from a fixed template")


class Photo(BaseModel):
    id: uuid.UUID
    url: str = Field(
        description="Path on this API (GET /v1/images/{id}): a JPEG, at most 1080 px on its "
        "longest side. The app prefixes its API base URL; it never calls the photo's origin"
    )
    color: str = Field(description="Average colour, #rrggbb: the placeholder while it loads")
    width: int
    height: int
    credit: PhotoCredit
