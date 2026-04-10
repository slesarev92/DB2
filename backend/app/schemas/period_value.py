"""Pydantic-схемы для PeriodValue API.

Реализует трёхслойную модель данных (ADR-05) и приоритет слоёв
actual > finetuned > predict при чтении.
"""
from enum import Enum
from typing import Any

from pydantic import BaseModel

from app.models import SourceType


class ViewMode(str, Enum):
    """Режим отображения значений по периодам.

    - HYBRID    — эффективное значение на каждый период с приоритетом
                  actual > finetuned (latest version) > predict.
    - FACT_ONLY — только actual-слой; периоды без actual не возвращаются.
    - PLAN_ONLY — только plan: finetuned (если есть) или predict.
                  Исключает actual — для сценарного планирования.
    - COMPARE   — все три слоя в одной структуре, для UI сравнения.
    """

    HYBRID = "hybrid"
    FACT_ONLY = "fact_only"
    PLAN_ONLY = "plan_only"
    COMPARE = "compare"


class PeriodValueWrite(BaseModel):
    """Тело PATCH /api/project-sku-channels/{id}/values/{period_id}.

    JSONB-словарь произвольной формы. В MVP содержит входные показатели
    (nd, offtake, shelf_price). Computed downstream метрики (volume,
    net_revenue, cogs, gross_profit, contribution и т.д.) сюда не пишутся —
    они вычисляются расчётным ядром в Фазе 2.
    """

    values: dict[str, Any]


class HybridResponseItem(BaseModel):
    """Эффективное значение на один период (hybrid / fact_only / plan_only).

    source_type показывает какой слой "выиграл" приоритет:
      - actual    — фактические данные из импорта (B-02 в backlog)
      - finetuned — пользовательская правка (latest version)
      - predict   — predict-слой (создаётся в задаче 2.5)
    """

    period_id: int
    period_number: int
    source_type: SourceType
    values: dict[str, Any]
    is_overridden: bool


class CompareResponseItem(BaseModel):
    """Все три слоя для одного периода (view_mode=compare).

    Используется UI экраном "Сравнение слоёв". None означает что
    данных в этом слое нет.
    """

    period_id: int
    period_number: int
    predict: dict[str, Any] | None = None
    finetuned: dict[str, Any] | None = None
    actual: dict[str, Any] | None = None


class PatchPeriodValueResponse(BaseModel):
    """Ответ на PATCH — описание созданной finetuned-версии."""

    period_id: int
    scenario_id: int
    psk_channel_id: int
    source_type: SourceType
    version_id: int
    is_overridden: bool
    values: dict[str, Any]


class ResetOverrideResponse(BaseModel):
    """Ответ на DELETE override — сколько finetuned-строк удалено."""

    deleted_versions: int


# ============================================================
# Batch save (B-17)
# ============================================================


class BatchPeriodValueItem(BaseModel):
    """Один элемент batch save."""

    psk_channel_id: int
    period_id: int
    values: dict[str, Any]


class BatchPeriodValueRequest(BaseModel):
    """Тело PATCH .../period-values/batch."""

    items: list[BatchPeriodValueItem]


class BatchPeriodValueResponse(BaseModel):
    """Ответ batch save — сколько обновлено."""

    updated: int
    items: list[PatchPeriodValueResponse]
