"""Pydantic-схемы для ProjectSKUChannel — параметры SKU в конкретном канале."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.channel import ChannelRead


class ProjectSKUChannelBase(BaseModel):
    """Параметры SKU × Channel: ND, offtake, цены, промо, логистика."""

    channel_id: int

    nd_target: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    nd_ramp_months: int = Field(default=12, ge=1, le=36)
    offtake_target: Decimal = Field(default=Decimal("0"), ge=0)

    channel_margin: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    promo_discount: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    promo_share: Decimal = Field(default=Decimal("0"), ge=0, le=1)

    shelf_price_reg: Decimal = Field(default=Decimal("0"), ge=0)
    logistics_cost_per_kg: Decimal = Field(default=Decimal("0"), ge=0)

    seasonality_profile_id: int | None = None


class ProjectSKUChannelCreate(ProjectSKUChannelBase):
    """Тело POST /api/project-skus/{psk_id}/channels."""


class ProjectSKUChannelUpdate(BaseModel):
    """Тело PATCH /api/psk-channels/{id}. channel_id менять нельзя."""

    nd_target: Decimal | None = Field(default=None, ge=0, le=1)
    nd_ramp_months: int | None = Field(default=None, ge=1, le=36)
    offtake_target: Decimal | None = Field(default=None, ge=0)
    channel_margin: Decimal | None = Field(default=None, ge=0, le=1)
    promo_discount: Decimal | None = Field(default=None, ge=0, le=1)
    promo_share: Decimal | None = Field(default=None, ge=0, le=1)
    shelf_price_reg: Decimal | None = Field(default=None, ge=0)
    logistics_cost_per_kg: Decimal | None = Field(default=None, ge=0)
    seasonality_profile_id: int | None = None


class ProjectSKUChannelRead(BaseModel):
    """Возвращается из list/get с явно загруженным channel (selectinload)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_sku_id: int
    channel_id: int
    channel: ChannelRead

    nd_target: Decimal
    nd_ramp_months: int
    offtake_target: Decimal
    channel_margin: Decimal
    promo_discount: Decimal
    promo_share: Decimal
    shelf_price_reg: Decimal
    logistics_cost_per_kg: Decimal
    seasonality_profile_id: int | None
    created_at: datetime
