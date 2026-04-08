"""Pydantic-схемы для BOM-позиций (Bill of Materials)."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class BOMItemBase(BaseModel):
    ingredient_name: str = Field(..., min_length=1, max_length=500)
    quantity_per_unit: Decimal = Field(..., ge=0)
    loss_pct: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    price_per_unit: Decimal = Field(default=Decimal("0"), ge=0)


class BOMItemCreate(BOMItemBase):
    """Тело POST /api/project-skus/{psk_id}/bom."""


class BOMItemUpdate(BaseModel):
    """Тело PATCH /api/bom-items/{id}. Все поля Optional."""

    ingredient_name: str | None = Field(default=None, min_length=1, max_length=500)
    quantity_per_unit: Decimal | None = Field(default=None, ge=0)
    loss_pct: Decimal | None = Field(default=None, ge=0, le=1)
    price_per_unit: Decimal | None = Field(default=None, ge=0)


class BOMItemRead(BOMItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_sku_id: int
    created_at: datetime
