"""Pydantic-схемы для ProjectSKU (включение SKU в проект с rates)."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.sku import SKURead


class ProjectSKUBase(BaseModel):
    sku_id: int
    include: bool = True
    production_mode: str = Field(default="own", pattern="^(own|copacking)$")
    copacking_rate: Decimal = Field(default=Decimal("0"), ge=0)
    production_cost_rate: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    # Q1 (2026-05-15): годовой override режима производства. Ключи —
    # model_year ("1".."10"), значения "own"|"copacking". Пустой dict
    # = override нет, используется скаляр production_mode.
    production_mode_by_year: dict[str, str] = Field(default_factory=dict)
    # Q5 (2026-05-15): уровень себестоимости BOM. Скаляр + годовой override
    # (ключи "1".."10", значения "max"|"normal"|"optimal").
    bom_cost_level: str = Field(default="normal", pattern="^(max|normal|optimal)$")
    bom_cost_level_by_year: dict[str, str] = Field(default_factory=dict)
    package_image_id: int | None = None


class ProjectSKUCreate(ProjectSKUBase):
    """Тело POST /api/projects/{project_id}/skus."""


class ProjectSKUUpdate(BaseModel):
    """Тело PATCH /api/project-skus/{id}. sku_id менять нельзя."""

    include: bool | None = None
    production_mode: str | None = Field(default=None, pattern="^(own|copacking)$")
    copacking_rate: Decimal | None = Field(default=None, ge=0)
    production_cost_rate: Decimal | None = Field(default=None, ge=0, le=1)
    production_mode_by_year: dict[str, str] | None = None
    bom_cost_level: str | None = Field(
        default=None, pattern="^(max|normal|optimal)$"
    )
    bom_cost_level_by_year: dict[str, str] | None = None
    package_image_id: int | None = None


class ProjectSKURead(BaseModel):
    """Возвращается из list endpoint'а. Без COGS preview."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    sku_id: int
    sku: SKURead
    include: bool
    production_mode: str
    copacking_rate: Decimal
    production_cost_rate: Decimal
    production_mode_by_year: dict[str, str] = Field(default_factory=dict)
    bom_cost_level: str = Field(default="normal")
    bom_cost_level_by_year: dict[str, str] = Field(default_factory=dict)
    package_image_id: int | None = None
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
