"""Pydantic схемы для Ingredient catalog (B-04)."""
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class IngredientCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=500)
    unit: str = Field(default="kg", max_length=50)
    category: str = Field(default="raw_material", pattern="^(raw_material|packaging|other)$")


class IngredientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=500)
    unit: str | None = Field(default=None, max_length=50)
    category: str | None = Field(
        default=None, pattern="^(raw_material|packaging|other)$"
    )


class IngredientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    unit: str
    category: str
    latest_price: Decimal | None = None
    created_at: datetime


class IngredientPriceCreate(BaseModel):
    price_per_unit: Decimal = Field(..., ge=0)
    effective_date: date
    notes: str | None = Field(default=None, max_length=500)


class IngredientPriceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ingredient_id: int
    price_per_unit: Decimal
    effective_date: date
    notes: str | None
    created_at: datetime
