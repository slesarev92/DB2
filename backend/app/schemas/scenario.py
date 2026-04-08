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
    notes: str | None
    created_at: datetime


class ScenarioUpdate(BaseModel):
    """PATCH /api/scenarios/{id}.

    `type` и `project_id` НЕ могут быть изменены — поля отсутствуют
    в схеме (Pydantic v2 по умолчанию ignore unknown fields).
    Дельты могут быть отрицательными (Conservative обычно delta_nd<0).
    """

    delta_nd: Decimal | None = Field(default=None, ge=-1, le=1)
    delta_offtake: Decimal | None = Field(default=None, ge=-1, le=1)
    delta_opex: Decimal | None = Field(default=None, ge=-1, le=1)
    notes: str | None = Field(default=None, max_length=5000)


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
    calculated_at: datetime
