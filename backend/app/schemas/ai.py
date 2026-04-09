"""Pydantic схемы AI endpoints (Phase 7.2..7.8).

Request/Response модели для `/api/projects/{id}/ai/*` endpoint'ов.
Строгая валидация: если LLM вернул что-то не по схеме,
`ai_service.complete_json` поднимет `AIServiceUnavailableError`, и
endpoint вернёт 503 с placeholder.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.base import PeriodScope
from app.services.ai_service import AIModelTier


# ============================================================
# EXPLAIN KPI (Phase 7.2)
# ============================================================


class AIKpiExplanationRequest(BaseModel):
    """Request body для POST /api/projects/{id}/ai/explain-kpi.

    project_id — в path; здесь только scenario + scope + опциональный
    tier_override для UI Standard/Deep toggle.
    """

    scenario_id: int = Field(
        ...,
        description="Фокусный сценарий (Base/Conservative/Aggressive).",
    )
    scope: PeriodScope = Field(
        ...,
        description="Фокусный горизонт (y1y3 | y1y5 | y1y10).",
    )
    tier_override: AIModelTier | None = Field(
        default=None,
        description=(
            "Override модели для этого вызова. None = default "
            "(FEATURE_DEFAULT_TIER[EXPLAIN_KPI] = BALANCED). "
            "HEAVY = Deep analysis через opus (дороже)."
        ),
    )


class AIKpiExplanationResponse(BaseModel):
    """Structured ответ от explain-kpi.

    `summary`, `key_drivers`, `risks`, `recommendation`, `confidence`,
    `rationale` — то, что генерит LLM по KPI_EXPLAIN_SYSTEM промпту.
    `cost_rub`, `model`, `cached` — метаданные вызова, заполняются
    endpoint'ом, не LLM'ом.
    """

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(
        ..., description="2-3 предложения executive-резюме."
    )
    key_drivers: list[str] = Field(
        default_factory=list,
        description="Топ-3 фактора влияющих на NPV фокусного сценария.",
    )
    risks: list[str] = Field(
        default_factory=list,
        description="2-3 риска: что может сломать кейс.",
    )
    recommendation: Literal["go", "no-go", "review"] = Field(
        ...,
        description="AI-рекомендация — предложение, не финальное решение.",
    )
    confidence: float = Field(
        ..., ge=0, le=1, description="Уверенность AI в рекомендации."
    )
    rationale: str = Field(
        ..., description="1-2 предложения — почему такая рекомендация."
    )
    # --- Метаданные вызова (заполняются endpoint'ом) ---
    cost_rub: Decimal = Field(
        ..., description="Фактическая стоимость вызова в рублях."
    )
    model: str = Field(
        ..., description="Использованная модель (для audit)."
    )
    cached: bool = Field(
        ..., description="True если результат из Redis cache."
    )


class LLMKpiOutput(BaseModel):
    """То, что LLM возвращает как JSON — подмножество response.

    Отдельная схема, потому что endpoint добавляет cost_rub/model/cached
    к LLM-ответу перед возвратом клиенту. LLM не должен ничего знать
    про стоимость своего вызова.
    """

    model_config = ConfigDict(extra="ignore")

    summary: str
    key_drivers: list[str]
    risks: list[str]
    recommendation: Literal["go", "no-go", "review"]
    confidence: float = Field(ge=0, le=1)
    rationale: str
