"""Pydantic-схемы для Scenario и ScenarioResult."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models import PeriodScope, ScenarioType


class ScenarioRead(BaseModel):
    """Сценарий проекта.

    `type` (Base/Conservative/Aggressive) идентифицирует сценарий и
    создаётся автоматически при POST /api/projects (3 сценария на
    проект). Менять тип нельзя — это часть identity сценария.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    type: ScenarioType
    delta_nd: Decimal
    delta_offtake: Decimal
    delta_opex: Decimal
    # 4.5 — project-wide мультипликативные дельты price/COGS/logistics
    delta_shelf_price: Decimal = Decimal("0")
    delta_bom_cost: Decimal = Decimal("0")
    delta_logistics: Decimal = Decimal("0")
    notes: str | None
    created_at: datetime


class ScenarioUpdate(BaseModel):
    """PATCH /api/scenarios/{id}.

    `type` и `project_id` НЕ могут быть изменены — поля отсутствуют
    в схеме (Pydantic v2 по умолчанию ignore unknown fields).
    Дельты могут быть отрицательными (Conservative обычно delta_nd<0).
    4.5: price/COGS/logistics дельты могут быть большими (до ±50%).
    """

    delta_nd: Decimal | None = Field(default=None, ge=-1, le=1)
    delta_offtake: Decimal | None = Field(default=None, ge=-1, le=1)
    delta_opex: Decimal | None = Field(default=None, ge=-1, le=1)
    delta_shelf_price: Decimal | None = Field(default=None, ge=-1, le=1)
    delta_bom_cost: Decimal | None = Field(default=None, ge=-1, le=1)
    delta_logistics: Decimal | None = Field(default=None, ge=-1, le=1)
    notes: str | None = Field(default=None, max_length=5000)


class ChannelDeltaItem(BaseModel):
    """Per-channel delta override (B-06)."""

    psk_channel_id: int
    delta_nd: Decimal = Field(default=Decimal("0"), ge=-1, le=1)
    delta_offtake: Decimal = Field(default=Decimal("0"), ge=-1, le=1)


class ChannelDeltaRequest(BaseModel):
    """PUT /api/scenarios/{id}/channel-deltas.

    Полная замена per-channel overrides. Items для psk_channel_id
    которых нет в списке → удаляются (fallback к scenario-level delta).
    """

    items: list[ChannelDeltaItem] = Field(default_factory=list)


class ScenarioResultRead(BaseModel):
    """Финансовые KPI сценария на одном горизонте (Y1-3 / Y1-5 / Y1-10).

    Заполняется расчётным ядром в задаче 2.4. До первого расчёта
    GET /api/scenarios/{id}/results вернёт 404.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    scenario_id: int
    period_scope: PeriodScope
    npv: Decimal | None
    irr: Decimal | None
    roi: Decimal | None
    payback_simple: Decimal | None
    payback_discounted: Decimal | None
    contribution_margin: Decimal | None
    ebitda_margin: Decimal | None
    go_no_go: bool | None

    # Per-unit метрики (Phase 8.3): scope-averaged
    nr_per_unit: Decimal | None = None
    gp_per_unit: Decimal | None = None
    cm_per_unit: Decimal | None = None
    ebitda_per_unit: Decimal | None = None
    nr_per_liter: Decimal | None = None
    gp_per_liter: Decimal | None = None
    cm_per_liter: Decimal | None = None
    ebitda_per_liter: Decimal | None = None
    nr_per_kg: Decimal | None = None
    gp_per_kg: Decimal | None = None
    cm_per_kg: Decimal | None = None
    ebitda_per_kg: Decimal | None = None

    calculated_at: datetime

    # F-01/F-02: True — данные проекта менялись после последнего пересчёта,
    # результаты устарели. UI показывает badge "⚠️ Расчёт устарел" с CTA
    # "Пересчитать". Сбрасывается в False при успешном recalculate.
    is_stale: bool = False
