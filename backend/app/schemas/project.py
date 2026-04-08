"""Pydantic-схемы для проекта."""
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# Base / Create / Update / Read
# ============================================================


class ProjectBase(BaseModel):
    """Поля проекта, общие для Create и Read.

    Defaults совпадают с defaults в SQLAlchemy модели — чтобы клиент
    мог опустить параметры и получить разумные значения.
    """

    name: str = Field(..., min_length=1, max_length=500)
    start_date: date
    horizon_years: int = Field(default=10, ge=1, le=20)

    wacc: Decimal = Field(default=Decimal("0.19"), ge=0, le=1)
    tax_rate: Decimal = Field(default=Decimal("0.20"), ge=0, le=1)
    wc_rate: Decimal = Field(default=Decimal("0.12"), ge=0, le=1)
    vat_rate: Decimal = Field(default=Decimal("0.20"), ge=0, le=1)

    currency: str = Field(default="RUB", min_length=3, max_length=3)
    inflation_profile_id: int | None = None


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
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    inflation_profile_id: int | None = None


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
