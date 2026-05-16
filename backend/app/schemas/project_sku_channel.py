"""Pydantic-схемы для ProjectSKUChannel — параметры SKU в конкретном канале."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.channel import ChannelRead


class ProjectSKUChannelBase(BaseModel):
    """Параметры SKU × Channel: ND, offtake, цены, промо, логистика."""

    channel_id: int

    # Launch lag (D-13): по умолчанию канал активен с M1 проекта (Y1 Jan).
    # Если задан позже — pipeline обнуляет nd/offtake до launch периода.
    # Excel хранит per (SKU × Channel) — TT/E-COM запускаются раньше HM/SM/MM.
    launch_year: int = Field(default=1, ge=1, le=10)
    launch_month: int = Field(default=1, ge=1, le=12)

    nd_target: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    nd_ramp_months: int = Field(default=12, ge=1, le=36)
    offtake_target: Decimal = Field(default=Decimal("0"), ge=0)

    channel_margin: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    promo_discount: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    promo_share: Decimal = Field(default=Decimal("0"), ge=0, le=1)

    shelf_price_reg: Decimal = Field(default=Decimal("0"), ge=0)
    logistics_cost_per_kg: Decimal = Field(default=Decimal("0"), ge=0)

    # Q6 (CLIENT_FEEDBACK_v2_DECISIONS.md, 2026-05-15): CA&M и Marketing per-channel.
    ca_m_rate: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    marketing_rate: Decimal = Field(default=Decimal("0"), ge=0, le=1)

    seasonality_profile_id: int | None = None


class ProjectSKUChannelCreate(ProjectSKUChannelBase):
    """Тело POST /api/project-skus/{psk_id}/channels."""


class ProjectSKUChannelUpdate(BaseModel):
    """Тело PATCH /api/psk-channels/{id}. channel_id менять нельзя."""

    launch_year: int | None = Field(default=None, ge=1, le=10)
    launch_month: int | None = Field(default=None, ge=1, le=12)
    nd_target: Decimal | None = Field(default=None, ge=0, le=1)
    nd_ramp_months: int | None = Field(default=None, ge=1, le=36)
    offtake_target: Decimal | None = Field(default=None, ge=0)
    channel_margin: Decimal | None = Field(default=None, ge=0, le=1)
    promo_discount: Decimal | None = Field(default=None, ge=0, le=1)
    promo_share: Decimal | None = Field(default=None, ge=0, le=1)
    shelf_price_reg: Decimal | None = Field(default=None, ge=0)
    logistics_cost_per_kg: Decimal | None = Field(default=None, ge=0)
    ca_m_rate: Decimal | None = Field(default=None, ge=0, le=1)
    marketing_rate: Decimal | None = Field(default=None, ge=0, le=1)
    seasonality_profile_id: int | None = None


class ProjectSKUChannelDefaults(BaseModel):
    """Метрики применяемые ко всем bulk-привязываемым каналам.

    = ProjectSKUChannelCreate минус channel_id. Юзер потом редактирует
    каждый PSC по отдельности через PATCH /api/psk-channels/{id}.
    """

    launch_year: int = Field(default=1, ge=1, le=10)
    launch_month: int = Field(default=1, ge=1, le=12)
    nd_target: Decimal = Field(..., ge=0, le=1)
    nd_ramp_months: int = Field(default=12, ge=1, le=36)
    offtake_target: Decimal = Field(..., ge=0)
    channel_margin: Decimal = Field(..., ge=0, le=1)
    promo_discount: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    # Default 0 чтобы поведение bulk совпадало с single-channel
    # ProjectSKUChannelBase (line 27 в этом файле) — иначе bulk-каналы
    # стартуют в "100% promo" без явного указания. (План C #16 имел
    # ошибку — promo_share=1 был исправлен в T2 review.)
    promo_share: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    shelf_price_reg: Decimal = Field(..., ge=0)
    logistics_cost_per_kg: Decimal = Field(default=Decimal("0"), ge=0)
    ca_m_rate: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    marketing_rate: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    seasonality_profile_id: int | None = None


class BulkChannelLinkCreate(BaseModel):
    """Body для POST /api/project-skus/{psk_id}/channels/bulk."""

    channel_ids: list[int] = Field(..., min_length=1, max_length=50)
    defaults: ProjectSKUChannelDefaults


class ProjectSKUChannelRead(BaseModel):
    """Возвращается из list/get с явно загруженным channel (selectinload)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_sku_id: int
    channel_id: int
    channel: ChannelRead

    launch_year: int
    launch_month: int

    nd_target: Decimal
    nd_ramp_months: int
    offtake_target: Decimal
    channel_margin: Decimal
    promo_discount: Decimal
    promo_share: Decimal
    shelf_price_reg: Decimal
    logistics_cost_per_kg: Decimal
    ca_m_rate: Decimal
    marketing_rate: Decimal
    seasonality_profile_id: int | None
    created_at: datetime
