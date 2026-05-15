"""Pydantic схемы для ProjectFinancialPlan CRUD API.

B.9b (2026-05-15): UI и API работают per-period. period_number 1..43
маппится на справочник `periods`: 1..36 = monthly Y1-Y3 (M1..M36,
model_year 1..3), 37..43 = yearly Y4-Y10 (model_year 4..10).

Pipeline аннуализирует все периоды по model_year в s10_discount,
поэтому CAPEX в M3 (period_number=3) или в M1 (period_number=1)
даёт одинаковый annual_capex[Y1] = их сумма.
"""
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

# Phase 8.8: стандартные категории маркетингового бюджета.
# Values — нижний регистр для БД, UI отображает labels из OPEX_CATEGORY_LABELS
# в frontend. "other" — default для backward compat старых записей.
OPEX_CATEGORIES: tuple[str, ...] = (
    "digital",
    "ecom",
    "ooh",
    "pr",
    "smm",
    "design",
    "research",
    "posm",
    "creative",
    "special",
    "merch",
    "tv",
    "listings",
    "other",
)

# B.9 / MEMO 2.1: стандартные категории CAPEX. Минимально достаточный
# набор; "other" — default для свободных статей.
CAPEX_CATEGORIES: tuple[str, ...] = (
    "molds",       # Молды и оснастка
    "line",        # Линия розлива / производственная линия
    "equipment",   # Оборудование (доп.)
    "it",          # IT (системы, лицензии)
    "rd",          # R&D / разработка рецептур
    "marketing",   # Запускной маркетинг (амортизируемый)
    "other",
)


class OpexItemSchema(BaseModel):
    """Одна статья OPEX в разбивке (B-19 + 8.8 category)."""

    category: str = Field(default="other", max_length=50)
    name: str = Field(..., min_length=1, max_length=200)
    amount: Decimal = Field(default=Decimal("0"), ge=0)


class CapexItemSchema(BaseModel):
    """Одна статья CAPEX в разбивке (B.9 / MEMO 2.1)."""

    category: str = Field(default="other", max_length=50)
    name: str = Field(..., min_length=1, max_length=200)
    amount: Decimal = Field(default=Decimal("0"), ge=0)


class FinancialPlanItem(BaseModel):
    """Одна строка плана для одного периода (M1..M36 + Y4..Y10).

    B.9b (2026-05-15): per-period вместо per-year. period_number — 1..43,
    маппится на справочник `periods` (1..36 = monthly Y1-Y3, 37..43 = yearly Y4-Y10).

    Логика автосуммирования:
    - opex_items не пустой → opex = sum(opex_items.amount).
    - capex_items не пустой → capex = sum(capex_items.amount).
    """

    period_number: int = Field(..., ge=1, le=43, description="period 1..43")
    capex: Decimal = Field(default=Decimal("0"), ge=0)
    opex: Decimal = Field(default=Decimal("0"), ge=0)
    opex_items: list[OpexItemSchema] = Field(default_factory=list)
    capex_items: list[CapexItemSchema] = Field(default_factory=list)


class FinancialPlanRequest(BaseModel):
    """Тело PUT /api/projects/{id}/financial-plan.

    Полная замена плана: backend удаляет все существующие записи
    `project_financial_plans` для project_id и вставляет новые по
    переданному списку. period_number'ы которых нет в списке → 0/0 в GET.

    Валидация: period_number уникальны в массиве.
    """

    items: list[FinancialPlanItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_period_uniqueness(self) -> "FinancialPlanRequest":
        seen: set[int] = set()
        for item in self.items:
            if item.period_number in seen:
                raise ValueError(
                    f"Duplicate period_number={item.period_number} in items"
                )
            seen.add(item.period_number)
        return self
