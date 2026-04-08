"""Pydantic-схемы справочника SKU (не привязан к проекту)."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class SKUBase(BaseModel):
    brand: str = Field(..., min_length=1, max_length=255)
    name: str = Field(..., min_length=1, max_length=500)
    format: str | None = Field(default=None, max_length=100)
    volume_l: Decimal | None = Field(default=None, ge=0)
    package_type: str | None = Field(default=None, max_length=100)
    segment: str | None = Field(default=None, max_length=100)


class SKUCreate(SKUBase):
    """Тело POST /api/skus."""


class SKUUpdate(BaseModel):
    """Тело PATCH /api/skus/{id}. Все поля Optional."""

    brand: str | None = Field(default=None, min_length=1, max_length=255)
    name: str | None = Field(default=None, min_length=1, max_length=500)
    format: str | None = Field(default=None, max_length=100)
    volume_l: Decimal | None = Field(default=None, ge=0)
    package_type: str | None = Field(default=None, max_length=100)
    segment: str | None = Field(default=None, max_length=100)


class SKURead(SKUBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
