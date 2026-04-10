"""Pydantic-схемы справочника каналов сбыта.

B-05: добавлен region для региональной детализации + CRUD endpoints.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ChannelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    region: str | None = None
    universe_outlets: int | None = None
    created_at: datetime


class ChannelCreate(BaseModel):
    """POST /api/channels."""

    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=255)
    region: str | None = Field(default=None, max_length=100)
    universe_outlets: int | None = Field(default=None, ge=0)


class ChannelUpdate(BaseModel):
    """PATCH /api/channels/{id}."""

    code: str | None = Field(default=None, min_length=1, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    region: str | None = Field(default=None, max_length=100)
    universe_outlets: int | None = Field(default=None, ge=0)
