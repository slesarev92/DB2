"""Pydantic-схемы для BOM-позиций (Bill of Materials)."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


COST_LEVEL_PATTERN = "^(max|normal|optimal)$"


class BOMItemBase(BaseModel):
    ingredient_name: str = Field(..., min_length=1, max_length=500)
    quantity_per_unit: Decimal = Field(..., ge=0)
    loss_pct: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    price_per_unit: Decimal = Field(default=Decimal("0"), ge=0)
    # LOGIC-07: НДС ингредиента (справочная, не влияет на расчёты).
    vat_rate: Decimal = Field(default=Decimal("0.20"), ge=0, le=1)
    # Q5 (2026-05-15): уровень себестоимости BOM. Три значения:
    # "max" (малые объёмы), "normal" (средние, дефолт), "optimal" (высокие).
    cost_level: str = Field(default="normal", pattern=COST_LEVEL_PATTERN)


class BOMItemCreate(BOMItemBase):
    """Тело POST /api/project-skus/{psk_id}/bom.

    Если ingredient_id указан — ingredient_name и price_per_unit
    могут быть опущены (backend подтянет из каталога).
    """

    ingredient_id: int | None = None


class BOMItemUpdate(BaseModel):
    """Тело PATCH /api/bom-items/{id}. Все поля Optional."""

    ingredient_name: str | None = Field(default=None, min_length=1, max_length=500)
    quantity_per_unit: Decimal | None = Field(default=None, ge=0)
    loss_pct: Decimal | None = Field(default=None, ge=0, le=1)
    price_per_unit: Decimal | None = Field(default=None, ge=0)
    vat_rate: Decimal | None = Field(default=None, ge=0, le=1)
    cost_level: str | None = Field(default=None, pattern=COST_LEVEL_PATTERN)
    ingredient_id: int | None = None


class BOMItemRead(BOMItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_sku_id: int
    ingredient_id: int | None = None
    ingredient_category: str | None = None
    created_at: datetime
