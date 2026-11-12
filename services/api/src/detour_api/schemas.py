"""Request and response models: the API contract that packages/shared is generated from."""

import uuid
from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: Literal["detour-api"] = "detour-api"
    version: str
    release: str | None = Field(default=None, description="Commit identifier of the deployed build")


class DatabaseStatus(BaseModel):
    status: Literal["ok", "unavailable", "not_configured"]
    schemas: list[str] = Field(
        default_factory=list, description="Of 'app' and 'geo', those present"
    )
    postgis: str | None = Field(
        default=None, description="PostGIS version if the extension is enabled"
    )


class ReadinessResponse(BaseModel):
    status: Literal["ok", "unavailable"]
    database: DatabaseStatus


class AttributionLine(BaseModel):
    text: str
    url: str


class MapConfig(BaseModel):
    style_url: str
    attribution: list[AttributionLine]


class ClientConfig(BaseModel):
    config_version: str
    map: MapConfig


class InstallationRegistration(BaseModel):
    installation_id: uuid.UUID
    token: str = Field(description="Bearer token. Shown once; keep it in secure storage.")


class InstallationInfo(BaseModel):
    installation_id: uuid.UUID


class ErrorResponse(BaseModel):
    detail: str
