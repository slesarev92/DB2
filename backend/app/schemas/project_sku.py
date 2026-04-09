"""Pydantic-схемы для ProjectSKU (включение SKU в проект с rates)."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.sku import SKURead


class ProjectSKUBase(BaseModel):
    sku_id: int
    include: bool = True
    production_cost_rate: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    ca_m_rate: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    marketing_rate: Decimal = Field(default=Decimal("0"), ge=0, le=1)


class ProjectSKUCreate(ProjectSKUBase):
    """Тело POST /api/projects/{project_id}/skus."""


class ProjectSKUUpdate(BaseModel):
    """Тело PATCH /api/project-skus/{id}. sku_id менять нельзя."""

    include: bool | None = None
    production_cost_rate: Decimal | None = Field(default=None, ge=0, le=1)
    ca_m_rate: Decimal | None = Field(default=None, ge=0, le=1)
    marketing_rate: Decimal | None = Field(default=None, ge=0, le=1)


class ProjectSKURead(BaseModel):
    """Возвращается из list endpoint'а. Без COGS preview."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    sku_id: int
    sku: SKURead
    include: bool
    production_cost_rate: Decimal
    ca_m_rate: Decimal
    marketing_rate: Decimal
    created_at: datetime


class ProjectSKUDetail(ProjectSKURead):
    """Single GET: дополнительно содержит preview-расчёт COGS_PER_UNIT.

    cogs_per_unit_estimated = Σ(bom.quantity_per_unit × bom.price_per_unit
                                × (1 + bom.loss_pct)).

    Это упрощённая preview-формула для UI. Реальная формула COGS из
    эталонной модели GORJI (включая copacking, production rate, и т.п.)
    реализуется в задаче 2.1 расчётного ядра.
    """

    cogs_per_unit_estimated: Decimal | None = None
