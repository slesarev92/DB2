"""Pydantic схемы для ProjectFinancialPlan CRUD API.

UI работает по **годам** (Y1..Y10), backend хранит записи с `period_id`
на конкретные периоды справочника `periods`. Сервис-слой делает
маппинг year → первый period model_year (для Y1-Y3 это M1/M13/M25,
для Y4-Y10 — непосредственно Y4..Y10 period).

Pipeline аннуализирует все периоды по model_year в s10_discount,
поэтому важно только чтобы capex/opex попали в правильный
`model_year` — на какой именно period_id внутри года они лягут не
влияет на KPI.
"""
from decimal import Decimal

from pydantic import BaseModel, Field


class FinancialPlanItem(BaseModel):
    """Одна строка плана для одного модельного года."""

    year: int = Field(..., ge=1, le=10, description="model_year 1..10")
    capex: Decimal = Field(default=Decimal("0"), ge=0)
    opex: Decimal = Field(default=Decimal("0"), ge=0)


class FinancialPlanRequest(BaseModel):
    """Тело PUT /api/projects/{id}/financial-plan.

    Полная замена плана проекта: backend удаляет все существующие
    записи `project_financial_plans` для project_id и вставляет новые
    по переданному списку. Элементы с year'ами которых нет в списке
    трактуются как 0/0.
    """

    items: list[FinancialPlanItem] = Field(default_factory=list)
