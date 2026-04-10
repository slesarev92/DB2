"""Pydantic схемы AKB — план дистрибуции (B-12)."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class AKBCreate(BaseModel):
    """POST /api/projects/{id}/akb."""

    channel_id: int
    universe_outlets: int | None = Field(default=None, ge=0)
    target_outlets: int | None = Field(default=None, ge=0)
    coverage_pct: Decimal | None = Field(default=None, ge=0, le=1)
    weighted_distribution: Decimal | None = Field(default=None, ge=0, le=1)
    notes: str | None = None


class AKBUpdate(BaseModel):
    """PATCH /api/projects/{id}/akb/{akb_id}."""

    universe_outlets: int | None = Field(default=None, ge=0)
    target_outlets: int | None = Field(default=None, ge=0)
    coverage_pct: Decimal | None = Field(default=None, ge=0, le=1)
    weighted_distribution: Decimal | None = Field(default=None, ge=0, le=1)
    notes: str | None = None


class ChannelBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str


class AKBRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    channel_id: int
    channel: ChannelBrief
    universe_outlets: int | None
    target_outlets: int | None
    coverage_pct: Decimal | None
    weighted_distribution: Decimal | None
    notes: str | None
    created_at: datetime
