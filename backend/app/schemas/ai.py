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
    """То, что LLM возвращает как JSON — подмножество response."""

    model_config = ConfigDict(extra="ignore")

    summary: str
    key_drivers: list[str]
    risks: list[str]
    recommendation: Literal["go", "no-go", "review"]
    confidence: float = Field(ge=0, le=1)
    rationale: str


# ============================================================
# EXPLAIN SENSITIVITY (Phase 7.3)
# ============================================================


class AISensitivityExplanationRequest(BaseModel):
    """Request body для POST /api/projects/{id}/ai/explain-sensitivity."""

    scenario_id: int
    tier_override: AIModelTier | None = None


class AISensitivityExplanationResponse(BaseModel):
    """Structured ответ от explain-sensitivity."""

    model_config = ConfigDict(extra="forbid")

    most_sensitive_param: str
    most_sensitive_impact: str
    least_sensitive_param: str
    narrative: str
    actionable_levers: list[str] = Field(default_factory=list)
    warning_flags: list[str] = Field(default_factory=list)
    cost_rub: Decimal
    model: str
    cached: bool


class LLMSensitivityOutput(BaseModel):
    """LLM JSON output для sensitivity interpretation."""

    model_config = ConfigDict(extra="ignore")

    most_sensitive_param: str
    most_sensitive_impact: str
    least_sensitive_param: str
    narrative: str
    actionable_levers: list[str]
    warning_flags: list[str] = Field(default_factory=list)


# ============================================================
# FREEFORM CHAT (Phase 7.3)
# ============================================================


class AIChatRequest(BaseModel):
    """Request body для POST /api/projects/{id}/ai/chat."""

    question: str = Field(
        ..., min_length=1, max_length=2000,
        description="Вопрос пользователя.",
    )
    conversation_id: str | None = Field(
        default=None,
        description=(
            "ID разговора для продолжения. None = новый разговор. "
            "Redis TTL 1h, после timeout'а — новый."
        ),
    )
    tier_override: AIModelTier | None = None


# ============================================================
# EXECUTIVE SUMMARY (Phase 7.4)
# ============================================================


class AIExecutiveSummaryRequest(BaseModel):
    """Request body — пустой (project_id в path), но tier_override допустим."""
    tier_override: AIModelTier | None = None


class KeyNumber(BaseModel):
    label: str
    value: str


class AIExecutiveSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    bullets: list[str]
    key_numbers: list[KeyNumber]
    risks_section: list[str]
    one_line_summary: str
    recommendation: Literal["go", "no-go", "review"]
    confidence: float = Field(ge=0, le=1)
    cost_rub: Decimal
    model: str
    cached: bool


class LLMExecutiveSummaryOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str
    bullets: list[str]
    key_numbers: list[KeyNumber]
    risks_section: list[str]
    one_line_summary: str
    recommendation: Literal["go", "no-go", "review"]
    confidence: float = Field(ge=0, le=1)


class AIExecutiveSummarySaveRequest(BaseModel):
    """PATCH body для сохранения отредактированного executive summary."""
    ai_executive_summary: str = Field(..., min_length=1, max_length=10000)


# ============================================================
# USAGE + BUDGET (Phase 7.5)
# ============================================================


class AIUsageDailyEntry(BaseModel):
    """Один день в daily_history."""
    date: str  # ISO date "2026-04-09"
    spent_rub: Decimal
    calls: int


class AIUsageRecentCall(BaseModel):
    """Одна запись из recent_calls."""
    id: int
    timestamp: str  # ISO datetime
    endpoint: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_rub: Decimal | None
    latency_ms: int
    error: str | None
    cached: bool


class AIUsageResponse(BaseModel):
    """GET /api/projects/{id}/ai/usage — агрегированная статистика."""
    model_config = ConfigDict(extra="forbid")

    project_id: int
    month_start: str  # ISO date "2026-04-01"
    spent_rub: Decimal
    budget_rub: Decimal | None
    budget_remaining_rub: Decimal | None
    budget_percent_used: float  # 0..1, None-safe
    daily_history: list[AIUsageDailyEntry]
    recent_calls: list[AIUsageRecentCall]
    cache_hit_rate_24h: float  # 0..1


class AIBudgetUpdateRequest(BaseModel):
    """PATCH /api/projects/{id}/ai/budget."""
    ai_budget_rub_monthly: Decimal | None = Field(
        default=None,
        description="Новый лимит в рублях. null = unlimited.",
        ge=0,
    )


# ============================================================
# CONTENT FIELD GENERATION (Phase 7.6)
# ============================================================

# Поля для которых доступна AI-генерация. Синхронизировано с
# AIContextBuilder.CONTENT_FIELDS.
ContentFieldName = Literal[
    "project_goal", "target_audience", "concept_text", "rationale",
    "growth_opportunity", "idea_short", "technology", "rnd_progress",
    "replacement_target", "description", "innovation_type",
    "geography", "production_type",
]


class AIContentFieldRequest(BaseModel):
    """POST /api/projects/{id}/ai/generate-content."""
    field: ContentFieldName
    user_hint: str | None = Field(
        default=None,
        max_length=1000,
        description="Подсказка для AI — что учесть при генерации.",
    )
    tier_override: AIModelTier | None = Field(
        default=None,
        description="Override: null=FAST_CHEAP (haiku), balanced=sonnet.",
    )


class AIContentFieldResponse(BaseModel):
    """Ответ генерации content field."""
    model_config = ConfigDict(extra="forbid")

    field: str
    generated_text: str
    cost_rub: Decimal
    model: str
    cached: bool


class LLMContentFieldOutput(BaseModel):
    """То что LLM возвращает как JSON."""
    model_config = ConfigDict(extra="ignore")

    generated_text: str


# ============================================================
# MARKETING RESEARCH (Phase 7.7)
# ============================================================

ResearchTopic = Literal[
    "competitive_analysis", "market_size", "consumer_trends",
    "category_benchmarks", "custom",
]


class ResearchSource(BaseModel):
    url: str
    title: str
    snippet: str = ""


class AIMarketingResearchRequest(BaseModel):
    """POST /api/projects/{id}/ai/marketing-research."""
    topic: ResearchTopic
    custom_query: str | None = Field(
        default=None,
        max_length=1000,
        description="Свободный запрос для topic=custom.",
    )


class AIMarketingResearchResponse(BaseModel):
    """Ответ marketing research."""
    model_config = ConfigDict(extra="forbid")

    topic: str
    research_text: str
    sources: list[ResearchSource]
    key_findings: list[str]
    confidence_notes: str
    generated_at: str  # ISO datetime
    cost_rub: Decimal
    model: str
    web_sources_used: bool  # False до верификации Polza web search API


class LLMMarketingResearchOutput(BaseModel):
    """LLM JSON output."""
    model_config = ConfigDict(extra="ignore")

    research_text: str
    sources: list[ResearchSource] = Field(default_factory=list)
    key_findings: list[str] = Field(default_factory=list)
    confidence_notes: str = ""


class AIMarketingResearchEditRequest(BaseModel):
    """PATCH body для редактирования research text."""
    topic: ResearchTopic
    edited_text: str = Field(..., min_length=1, max_length=20000)


# ============================================================
# PACKAGE MOCKUP (Phase 7.8)
# ============================================================


class AIPackageMockupRequest(BaseModel):
    """POST /api/projects/{project_id}/ai/generate-mockup."""
    project_sku_id: int
    prompt: str = Field(
        ..., min_length=1, max_length=2000,
        description="Описание желаемого mockup'а.",
    )
    reference_asset_id: int | None = Field(
        default=None,
        description="MediaAsset ID reference-изображения (логотип).",
    )
    tier_override: AIModelTier | None = Field(
        default=None,
        description=(
            "Override модели для vision-шага. None = BALANCED (sonnet, ~3-5₽). "
            "HEAVY = opus (~15-25₽, лучше art direction)."
        ),
    )


class AIPackageMockupResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int  # AIGeneratedImage.id
    media_asset_id: int
    media_url: str  # /api/media/{id}
    art_direction: str
    prompt: str
    cost_rub: Decimal
    model: str


class LLMVisionArtDirectionOutput(BaseModel):
    """Vision step output: art direction text."""
    model_config = ConfigDict(extra="ignore")

    art_direction: str


class AIGeneratedImageRead(BaseModel):
    """Gallery item for GET /ai/mockups."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_sku_id: int
    media_asset_id: int
    media_url: str
    reference_asset_id: int | None
    prompt_text: str
    art_direction: str
    cost_rub: Decimal | None
    model: str
    created_at: str
