"""Pydantic схемы OBPPC — Price-Pack-Channel matrix (B-13)."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class OBPPCCreate(BaseModel):
    """POST /api/projects/{id}/obppc."""

    sku_id: int
    channel_id: int
    occasion: str | None = Field(default=None, max_length=200)
    price_tier: str = Field(
        default="mainstream", pattern="^(premium|mainstream|value)$"
    )
    pack_format: str = Field(default="bottle", min_length=1, max_length=100)
    pack_size_ml: int | None = Field(default=None, ge=1)
    price_point: Decimal | None = Field(default=None, ge=0)
    is_active: bool = True
    notes: str | None = None


class OBPPCUpdate(BaseModel):
    """PATCH /api/projects/{id}/obppc/{entry_id}."""

    occasion: str | None = Field(default=None, max_length=200)
    price_tier: str | None = Field(
        default=None, pattern="^(premium|mainstream|value)$"
    )
    pack_format: str | None = Field(default=None, min_length=1, max_length=100)
    pack_size_ml: int | None = Field(default=None, ge=1)
    price_point: Decimal | None = Field(default=None, ge=0)
    is_active: bool | None = None
    notes: str | None = None


class SKUBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    brand: str
    name: str


class ChannelBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str


class OBPPCRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    sku_id: int
    sku: SKUBrief
    channel_id: int
    channel: ChannelBrief
    occasion: str | None
    price_tier: str
    pack_format: str
    pack_size_ml: int | None
    price_point: Decimal | None
    is_active: bool
    notes: str | None
    created_at: datetime
