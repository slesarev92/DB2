"""C #14 Fine Tuning per-period overrides — Pydantic schemas.

Все 4 override-поля — JSONB-массивы длины ровно 43 (M1..M36 + Y4..Y10),
элементы Decimal | None. None в элементе → pipeline берёт скаляр.
None во всём поле → нет override.
"""
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

PERIOD_COUNT = 43


def _validate_length(arr: list[Decimal | None] | None) -> list[Decimal | None] | None:
    if arr is None:
        return None
    if len(arr) != PERIOD_COUNT:
        raise ValueError(f"Array must have exactly {PERIOD_COUNT} elements, got {len(arr)}")
    return arr


def _validate_non_negative(arr: list[Decimal | None] | None) -> list[Decimal | None] | None:
    if arr is None:
        return None
    for i, v in enumerate(arr):
        if v is not None and v < 0:
            raise ValueError(f"Element [{i}]={v} must be >= 0")
    return arr


def _validate_rate(arr: list[Decimal | None] | None) -> list[Decimal | None] | None:
    if arr is None:
        return None
    for i, v in enumerate(arr):
        if v is not None and (v < 0 or v > 1):
            raise ValueError(f"Element [{i}]={v} must be in [0, 1]")
    return arr


class SkuOverridesPayload(BaseModel):
    """PUT payload для SKU-уровня override (copacking_rate)."""

    copacking_rate_by_period: list[Decimal | None] | None = Field(default=None)

    @field_validator("copacking_rate_by_period")
    @classmethod
    def _check_copacking(cls, v: list[Decimal | None] | None) -> list[Decimal | None] | None:
        return _validate_non_negative(_validate_length(v))


class SkuOverridesResponse(SkuOverridesPayload):
    """GET response — те же поля."""


class ChannelOverridesPayload(BaseModel):
    """PUT payload для Channel-уровня override (3 поля)."""

    logistics_cost_per_kg_by_period: list[Decimal | None] | None = Field(default=None)
    ca_m_rate_by_period: list[Decimal | None] | None = Field(default=None)
    marketing_rate_by_period: list[Decimal | None] | None = Field(default=None)

    @field_validator("logistics_cost_per_kg_by_period")
    @classmethod
    def _check_logistics(cls, v: list[Decimal | None] | None) -> list[Decimal | None] | None:
        return _validate_non_negative(_validate_length(v))

    @field_validator("ca_m_rate_by_period")
    @classmethod
    def _check_ca_m(cls, v: list[Decimal | None] | None) -> list[Decimal | None] | None:
        return _validate_rate(_validate_length(v))

    @field_validator("marketing_rate_by_period")
    @classmethod
    def _check_marketing(cls, v: list[Decimal | None] | None) -> list[Decimal | None] | None:
        return _validate_rate(_validate_length(v))


class ChannelOverridesResponse(ChannelOverridesPayload):
    """GET response — те же поля."""
