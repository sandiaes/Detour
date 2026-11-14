"""Shared validated types."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Latitude = Annotated[float, Field(ge=-90, le=90, description="WGS 84 latitude")]
Longitude = Annotated[float, Field(ge=-180, le=180, description="WGS 84 longitude")]


class StrictModel(BaseModel):
    """Request bodies reject unknown fields, so a typo is an error and not a silent no-op."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ErrorBody(BaseModel):
    detail: str
    code: str | None = Field(
        default=None, description="Stable machine-readable reason, for example region_not_available"
    )


class IssueBody(BaseModel):
    code: str
    text: str


class PlanningErrorBody(ErrorBody):
    issues: list[IssueBody] = Field(
        default_factory=list,
        description="With code planning_impossible: each reason no plan can be made",
    )


NameType = Literal[
    "original",
    "official_english",
    "established_english",
    "localized_brand",
    "official_romanization",
    "automatic_transliteration",
    "machine_translation",
    "search_alias",
    "user_override",
]


class PlaceName(BaseModel):
    """How a place is named in an English interface (ADR 025). Show ``display``; show ``local``
    under it when set; say "Automatically romanized" when ``auto_generated``."""

    display: str | None = Field(description="The name to show; null only for an unnamed place")
    local: str | None = Field(
        description="The original local name, when it differs from the display name"
    )
    local_lang: str | None = Field(description="BCP 47 tag of the local name; null if unknown")
    type: NameType = Field(description="What kind of name the display name is")
    source: str = Field(
        description="Where it came from: user, provider, wikidata, enwiki, osm, geonames, detour"
    )
    confidence: float = Field(ge=0, le=1)
    auto_generated: bool = Field(
        description="True for a transliteration Detour made; never presented as official"
    )
    user_override: bool = Field(description="The user approved this name for this place")


class DisplayNameUpdate(StrictModel):
    name: str = Field(min_length=1, max_length=120)
