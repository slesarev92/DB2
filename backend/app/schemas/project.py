"""Pydantic-схемы для проекта."""
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# Допустимые значения для content fields (4.5.1)
# ============================================================

GateStage = Literal["G0", "G1", "G2", "G3", "G4", "G5"]
ProjectStatus = Literal["draft", "active", "paused", "cancelled", "completed", "archived"]


# C #30: типизированный элемент списка nielsen_benchmarks.
# Phase 8.9 ввела поле `Project.nielsen_benchmarks: JSONB` как
# free-form `list[Any]`. C #30 (MEMO 1.4) — заранее ввести
# Pydantic-модель элементов с обязательным `source_type`, чтобы
# при последующем UI/импорте (#16 Nielsen-интеграция) не мигрировать
# данные. `extra="allow"` оставляет любые дополнительные поля,
# которые UI кладёт сейчас (название бренда, метрика, значение,
# год и т.п.) — структура подполей не зашита.
NielsenBenchmarkSourceType = Literal["manual", "excel", "ai", "nielsen"]


class NielsenBenchmarkItem(BaseModel):
    """Элемент списка `Project.nielsen_benchmarks` (JSONB).

    Жёстко типизирован только `source_type` — позволяет аналитике
    различать ручной ввод vs импорт. Остальные поля принимаются
    как есть (`extra="allow"`) для backward-compat с уже сохранёнными
    бенчмарками и для гибкости UI.
    """

    model_config = ConfigDict(extra="allow")

    source_type: NielsenBenchmarkSourceType | None = None


# ============================================================
# Base / Create / Update / Read
# ============================================================


class ProjectBase(BaseModel):
    """Поля проекта, общие для Create и Read.

    Defaults совпадают с defaults в SQLAlchemy модели — чтобы клиент
    мог опустить параметры и получить разумные значения.

    Content fields (Фаза 4.5) — все Optional (для backward compat
    с проектами созданными до 4.5; заполняются позже через PATCH).
    """

    name: str = Field(..., min_length=1, max_length=500)
    start_date: date
    horizon_years: int = Field(default=10, ge=1, le=20)

    wacc: Decimal = Field(default=Decimal("0.19"), ge=0, le=1)
    tax_rate: Decimal = Field(default=Decimal("0.20"), ge=0, le=1)
    wc_rate: Decimal = Field(default=Decimal("0.12"), ge=0, le=1)
    vat_rate: Decimal = Field(default=Decimal("0.22"), ge=0, le=1)

    # Go/No-Go порог Contribution Margin (настраиваемый per-project).
    cm_threshold: Decimal = Field(default=Decimal("0.25"), ge=0, le=1)

    # 4.1 (ст.283 НК РФ): перенос убытков прошлых лет. Default False
    # сохраняет Excel-compat baseline; True — точнее для launch-проектов.
    tax_loss_carryforward: bool = False

    currency: str = Field(default="RUB", min_length=3, max_length=3)
    inflation_profile_id: int | None = None

    # C #21: lifecycle статус проекта.
    status: ProjectStatus = "active"

    # 4.5.1: контент паспорта (16 scalar полей, все Optional)
    description: str | None = None
    gate_stage: GateStage | None = None
    passport_date: date | None = None
    project_owner: str | None = Field(default=None, max_length=200)
    project_goal: str | None = None
    innovation_type: str | None = None
    geography: str | None = Field(default=None, max_length=200)
    production_type: str | None = None
    growth_opportunity: str | None = None
    concept_text: str | None = None
    rationale: str | None = None
    idea_short: str | None = None
    target_audience: str | None = None
    replacement_target: str | None = None
    technology: str | None = None
    rnd_progress: str | None = None
    executive_summary: str | None = None  # AI-generated в Phase 7.6

    # 4.5.1: 5 JSONB полей (все Optional). Используем dict[str, Any]
    # / list[Any] — без жёсткой schema на уровне Pydantic чтобы давать
    # frontend'у гибкость в составе подполей. Конкретные ключи зашиты
    # в UI.
    risks: list[Any] | None = None
    validation_tests: dict[str, Any] | None = None
    function_readiness: dict[str, Any] | None = None
    roadmap_tasks: list[Any] | None = None
    approvers: list[Any] | None = None
    nielsen_benchmarks: list[NielsenBenchmarkItem] | None = None  # Phase 8.9 + C #30 source_type
    supplier_quotes: list[Any] | None = None  # Phase 8.10

    # 7.x: AI cached commentaries (persisted for page reload survival)
    ai_executive_summary: str | None = None
    ai_kpi_commentary: dict[str, Any] | None = None
    ai_sensitivity_commentary: dict[str, Any] | None = None

    # 7.5: AI budget — месячный лимит расходов на AI в рублях.
    # None = server_default 500₽ при создании; явный None через PATCH =
    # unlimited (бюджет не ограничен).
    ai_budget_rub_monthly: Decimal | None = Field(
        default=Decimal("500.00"), ge=0
    )


class ProjectCreate(ProjectBase):
    """Тело POST /api/projects."""


class ProjectUpdate(BaseModel):
    """Тело PATCH /api/projects/{id}. Все поля Optional."""

    name: str | None = Field(default=None, min_length=1, max_length=500)
    start_date: date | None = None
    horizon_years: int | None = Field(default=None, ge=1, le=20)
    wacc: Decimal | None = Field(default=None, ge=0, le=1)
    tax_rate: Decimal | None = Field(default=None, ge=0, le=1)
    wc_rate: Decimal | None = Field(default=None, ge=0, le=1)
    vat_rate: Decimal | None = Field(default=None, ge=0, le=1)
    cm_threshold: Decimal | None = Field(default=None, ge=0, le=1)
    tax_loss_carryforward: bool | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    inflation_profile_id: int | None = None

    # C #21: lifecycle статус проекта (optional в PATCH).
    status: ProjectStatus | None = None

    # 4.5.1: контент паспорта (PATCH с любым подмножеством полей)
    description: str | None = None
    gate_stage: GateStage | None = None
    passport_date: date | None = None
    project_owner: str | None = Field(default=None, max_length=200)
    project_goal: str | None = None
    innovation_type: str | None = None
    geography: str | None = Field(default=None, max_length=200)
    production_type: str | None = None
    growth_opportunity: str | None = None
    concept_text: str | None = None
    rationale: str | None = None
    idea_short: str | None = None
    target_audience: str | None = None
    replacement_target: str | None = None
    technology: str | None = None
    rnd_progress: str | None = None
    executive_summary: str | None = None
    risks: list[Any] | None = None
    validation_tests: dict[str, Any] | None = None
    function_readiness: dict[str, Any] | None = None
    roadmap_tasks: list[Any] | None = None
    approvers: list[Any] | None = None
    nielsen_benchmarks: list[NielsenBenchmarkItem] | None = None  # Phase 8.9 + C #30 source_type
    supplier_quotes: list[Any] | None = None  # Phase 8.10
    ai_budget_rub_monthly: Decimal | None = None


class ProjectRead(ProjectBase):
    """Возвращается из GET /api/projects/{id}."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime | None = None
    created_by: int | None = None


class ProjectListItem(ProjectRead):
    """Строка в списке GET /api/projects: проект + базовые KPI.

    KPI берутся из ScenarioResult по сценарию Base, горизонт Y1Y10.
    Все поля = None пока расчёт не выполнен (Фаза 2). Frontend
    показывает "не рассчитан" в этом случае.
    """

    npv_y1y10: Decimal | None = None
    irr_y1y10: Decimal | None = None
    go_no_go: bool | None = None
