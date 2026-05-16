"""Pydantic-схемы справочника каналов сбыта.

B-05: добавлен region для региональной детализации + CRUD endpoints.
C #16: добавлены channel_group (enum 8 значений) и source_type
(enum 5 значений, nullable).
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ChannelGroup = Literal["HM", "SM", "MM", "TT", "E_COM", "HORECA", "QSR", "OTHER"]
ChannelSourceType = Literal["nielsen", "tsrpt", "gis2", "infoline", "custom"]


class ChannelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    channel_group: ChannelGroup
    source_type: ChannelSourceType | None = None
    region: str | None = None
    universe_outlets: int | None = None
    created_at: datetime


class ChannelCreate(BaseModel):
    """POST /api/channels."""

    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=255)
    channel_group: ChannelGroup
    source_type: ChannelSourceType | None = None
    region: str | None = Field(default=None, max_length=100)
    universe_outlets: int | None = Field(default=None, ge=0)


class ChannelUpdate(BaseModel):
    """PATCH /api/channels/{id}."""

    code: str | None = Field(default=None, min_length=1, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    channel_group: ChannelGroup | None = None
    source_type: ChannelSourceType | None = None  # patch-able to NULL via explicit "null"
    region: str | None = Field(default=None, max_length=100)
    universe_outlets: int | None = Field(default=None, ge=0)
