"""Pydantic-схемы справочника SKU (не привязан к проекту)."""
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# C #19: enum типа упаковки. См. spec docs/superpowers/specs/
# 2026-05-16-c19-pack-format-enum-design.md §4.1.
PackFormat = Literal[
    "ПЭТ",
    "Стекло",
    "Банка",
    "Сашет",
    "Стик",
    "Пауч",
]

# C #23: единица измерения объёма/массы SKU.
SkuUnitOfMeasure = Literal["л", "кг"]


class SKUBase(BaseModel):
    brand: str = Field(..., min_length=1, max_length=255)
    name: str = Field(..., min_length=1, max_length=500)
    format: PackFormat | None = Field(default=None)
    volume_l: Decimal | None = Field(default=None, ge=0)
    package_type: str | None = Field(default=None, max_length=100)
    segment: str | None = Field(default=None, max_length=100)
    unit_of_measure: SkuUnitOfMeasure = "л"


class SKUCreate(SKUBase):
    """Тело POST /api/skus."""


class SKUUpdate(BaseModel):
    """Тело PATCH /api/skus/{id}. Все поля Optional."""

    brand: str | None = Field(default=None, min_length=1, max_length=255)
    name: str | None = Field(default=None, min_length=1, max_length=500)
    format: PackFormat | None = Field(default=None)
    volume_l: Decimal | None = Field(default=None, ge=0)
    package_type: str | None = Field(default=None, max_length=100)
    segment: str | None = Field(default=None, max_length=100)
    unit_of_measure: SkuUnitOfMeasure | None = None


class SKURead(SKUBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
