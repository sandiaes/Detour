"""People and their devices (ADR 034, step 1)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DeviceInfo(BaseModel):
    id: uuid.UUID
    added_at: datetime = Field(description="When the phone became one of the person's")
    last_seen_at: datetime
    this_device: bool


class LinkedPerson(BaseModel):
    person_id: uuid.UUID
    name: str | None = Field(description="Their display name; null when they set none")
    linked_at: datetime


class PersonInfo(BaseModel):
    person_id: uuid.UUID
    display_name: str | None = Field(description="Your name as others see it; null when none")
    people: list[LinkedPerson] = Field(
        description="People you may share trips with (ADR 034), in the order you linked them"
    )
    device_id: uuid.UUID = Field(description="The phone that asked")
    devices: list[DeviceInfo] = Field(description="The person's phones, oldest first")
    recovery_code_created_at: datetime | None = Field(
        description="When the current recovery code was made; null when there is none"
    )


class LinkCode(BaseModel):
    code: str = Field(description="Eight letters in two groups, e.g. 'K7MQ-R4XT'. Works once.")
    expires_at: datetime


class RecoveryCode(BaseModel):
    code: str = Field(
        description="26 letters in groups of four. Shown once; the earlier code stops working."
    )
    created_at: datetime


class JoinRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(
        min_length=1,
        max_length=64,
        description="A link code from another phone (8 letters) or the recovery code (26 letters); "
        "spaces and hyphens are ignored",
    )


class JoinResult(BaseModel):
    person: PersonInfo
    recovered: bool = Field(
        description="The recovery code was used: every other phone of the person was signed out"
    )
    moved_trips: int = Field(description="Trips of this phone that moved to the person")


class PersonUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str | None = Field(
        default=None, max_length=40, description="Your name as others see it; null or blank clears"
    )


class InviteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(
        min_length=1, max_length=64, description="The invite code shown by the other person"
    )
