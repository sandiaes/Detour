"""Shared validated types."""

import re
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

Latitude = Annotated[float, Field(ge=-90, le=90, description="WGS 84 latitude")]
Longitude = Annotated[float, Field(ge=-180, le=180, description="WGS 84 longitude")]

_CURRENCY = re.compile(r"^[A-Z]{3}$")


def _currency(value: str) -> str:
    value = value.strip().upper()
    if not _CURRENCY.match(value):
        raise ValueError("currency code must be three letters (ISO 4217)")
    return value


CurrencyCode = Annotated[str, AfterValidator(_currency), Field(description="ISO 4217 code")]


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
