"""SQLAlchemy ORM-модели цифрового паспорта проекта.

Соответствует ADR-04 (PeriodValue как JSONB), ADR-05 (трёхслойная модель
данных) и схеме из IMPLEMENTATION_PLAN.md задача 0.3.

Дизайн:
- Все денежные/процентные поля — Numeric (не Float), точность критична.
- Enums реализованы как SAEnum(native_enum=False) → VARCHAR + CHECK.
  Type-safety в Python, легко расширяется в БД без ALTER TYPE.
- Relationships не объявлены — будут добавлены в задаче 1.x по мере
  написания API. Сейчас — только ForeignKey колонки.
- TimestampMixin везде кроме Period (статичный справочник).
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    Base,
    PeriodScope,
    PeriodType,
    ScenarioType,
    SourceType,
    TimestampMixin,
    UserRole,
    varchar_enum,
)


# ============================================================
# Users
# ============================================================


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        varchar_enum(UserRole, "user_role"),
        nullable=False,
        default=UserRole.ANALYST,
    )


# ============================================================
# Reference catalogs
# ============================================================


class RefInflation(Base, TimestampMixin):
    """Профили инфляции (например, 'Апрель/Октябрь +7%')."""

    __tablename__ = "ref_inflation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    # JSONB-структура: список ступенек инфляции по месяцам года, формат
    # уточняется в задаче 0.4 (seed reference data).
    month_coefficients: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class RefSeasonality(Base, TimestampMixin):
    """Профили сезонности (Water, Energy drinks и т.д.)."""

    __tablename__ = "ref_seasonality"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    # 12 коэффициентов помесячно. Сумма обычно нормализована к 12.0.
    month_coefficients: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class SKU(Base, TimestampMixin):
    """Справочник SKU. Не привязан к проекту."""

    __tablename__ = "skus"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brand: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    format: Mapped[str | None] = mapped_column(String(100), nullable=True)
    volume_l: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    package_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    segment: Mapped[str | None] = mapped_column(String(100), nullable=True)


class Channel(Base, TimestampMixin):
    """Справочник каналов сбыта (HM, SM, MM, TT, E-COM_OZ, E-COM_OZ_Fresh)."""

    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    universe_outlets: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Period(Base):
    """Справочник периодов: M1..M36 (помесячно) + Y4..Y10 (годами).

    Заполняется один раз seed-скриптом в задаче 0.4. Содержит ровно 43 строки.
    Без TimestampMixin — статичный справочник, не редактируется.
    """

    __tablename__ = "periods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[PeriodType] = mapped_column(
        varchar_enum(PeriodType, "period_type"),
        nullable=False,
    )
    period_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..43
    model_year: Mapped[int] = mapped_column(Integer, nullable=False)     # 1..10
    month_num: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1..12 для monthly
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)

    __table_args__ = (
        UniqueConstraint("period_number", name="uq_periods_period_number"),
    )


# ============================================================
# Projects core
# ============================================================


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    horizon_years: Mapped[int] = mapped_column(Integer, nullable=False, default=10)

    # Параметры проекта (ADR-CE-02..04). Defaults — типичные значения GORJI+.
    wacc: Mapped[Decimal] = mapped_column(
        Numeric(8, 6), nullable=False, default=Decimal("0.19")
    )
    tax_rate: Mapped[Decimal] = mapped_column(
        Numeric(8, 6), nullable=False, default=Decimal("0.20")
    )
    wc_rate: Mapped[Decimal] = mapped_column(
        Numeric(8, 6), nullable=False, default=Decimal("0.12")
    )
    vat_rate: Mapped[Decimal] = mapped_column(
        Numeric(8, 6), nullable=False, default=Decimal("0.20")
    )

    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="RUB")

    inflation_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("ref_inflation.id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Soft delete: устанавливается при DELETE /api/projects/{id}.
    # Все запросы фильтруют WHERE deleted_at IS NULL.
    # Финансовый продукт — данные не теряем при ошибочном удалении.
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class Scenario(Base, TimestampMixin):
    """Сценарий проекта: Base / Conservative / Aggressive (раздел 8.6 ТЗ)."""

    __tablename__ = "scenarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[ScenarioType] = mapped_column(
        varchar_enum(ScenarioType, "scenario_type"),
        nullable=False,
    )

    # Дельты к Base — в долях единицы (0.10 = +10%).
    delta_nd: Mapped[Decimal] = mapped_column(
        Numeric(8, 6), nullable=False, default=Decimal("0")
    )
    delta_offtake: Mapped[Decimal] = mapped_column(
        Numeric(8, 6), nullable=False, default=Decimal("0")
    )
    delta_opex: Mapped[Decimal] = mapped_column(
        Numeric(8, 6), nullable=False, default=Decimal("0")
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("project_id", "type", name="uq_scenarios_project_type"),
    )


class ProjectSKU(Base, TimestampMixin):
    """SKU включённый в проект, со специфичными для проекта параметрами."""

    __tablename__ = "project_skus"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    sku_id: Mapped[int] = mapped_column(
        ForeignKey("skus.id", ondelete="RESTRICT"),
        nullable=False,
    )
    include: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Launch lag (D-13): SKU может быть запущен не в M1 проекта, а позже.
    # Excel хранит ND/offtake в DASH относительно launch month каждого SKU,
    # а в NET REVENUE/etc применяет absolute lag (нули до launch). Наша
    # модель: launch_year (1..10) + launch_month (1..12) — относительно
    # project.start_date. По умолчанию SKU активен с M1 (Y1 Jan).
    # Сервис `_build_line_input` обнуляет nd[t] и offtake[t] для periods
    # до launch, downstream pipeline автоматически даёт ноль на этих
    # периодах.
    launch_year: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1", default=1
    )
    launch_month: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1", default=1
    )

    # Rate-параметры SKU как % от выручки (D-04 в TZ_VS_EXCEL_DISCREPANCIES).
    production_cost_rate: Mapped[Decimal] = mapped_column(
        Numeric(8, 6), nullable=False, default=Decimal("0")
    )
    ca_m_rate: Mapped[Decimal] = mapped_column(
        Numeric(8, 6), nullable=False, default=Decimal("0")
    )
    marketing_rate: Mapped[Decimal] = mapped_column(
        Numeric(8, 6), nullable=False, default=Decimal("0")
    )

    # Async-safe relationship: lazy='raise_on_sql' запрещает случайные
    # неявные загрузки. Service всегда должен явно использовать
    # selectinload(ProjectSKU.sku) при чтении.
    sku: Mapped["SKU"] = relationship(lazy="raise_on_sql")

    __table_args__ = (
        UniqueConstraint("project_id", "sku_id", name="uq_project_skus_project_sku"),
    )


class ProjectSKUChannel(Base, TimestampMixin):
    """Параметры SKU в конкретном канале сбыта."""

    __tablename__ = "project_sku_channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_sku_id: Mapped[int] = mapped_column(
        ForeignKey("project_skus.id", ondelete="CASCADE"),
        nullable=False,
    )
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="RESTRICT"),
        nullable=False,
    )

    nd_target: Mapped[Decimal] = mapped_column(
        Numeric(8, 6), nullable=False, default=Decimal("0")
    )
    nd_ramp_months: Mapped[int] = mapped_column(Integer, nullable=False, default=12)
    offtake_target: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), nullable=False, default=Decimal("0")
    )

    channel_margin: Mapped[Decimal] = mapped_column(
        Numeric(8, 6), nullable=False, default=Decimal("0")
    )
    promo_discount: Mapped[Decimal] = mapped_column(
        Numeric(8, 6), nullable=False, default=Decimal("0")
    )
    promo_share: Mapped[Decimal] = mapped_column(
        Numeric(8, 6), nullable=False, default=Decimal("0")
    )

    shelf_price_reg: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), nullable=False, default=Decimal("0")
    )
    logistics_cost_per_kg: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), nullable=False, default=Decimal("0")
    )

    seasonality_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("ref_seasonality.id", ondelete="RESTRICT"),
        nullable=True,
    )

    # Async-safe: lazy='raise_on_sql' заставляет всегда явно использовать
    # selectinload(ProjectSKUChannel.channel) при чтении.
    channel: Mapped["Channel"] = relationship(lazy="raise_on_sql")

    __table_args__ = (
        UniqueConstraint(
            "project_sku_id", "channel_id",
            name="uq_psk_channels_project_sku_channel",
        ),
    )


class BOMItem(Base, TimestampMixin):
    """Bill of Materials — компонент SKU (сырьё, упаковка)."""

    __tablename__ = "bom_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_sku_id: Mapped[int] = mapped_column(
        ForeignKey("project_skus.id", ondelete="CASCADE"),
        nullable=False,
    )
    ingredient_name: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity_per_unit: Mapped[Decimal] = mapped_column(Numeric(15, 6), nullable=False)
    loss_pct: Mapped[Decimal] = mapped_column(
        Numeric(8, 6), nullable=False, default=Decimal("0")
    )
    price_per_unit: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), nullable=False, default=Decimal("0")
    )


# ============================================================
# Period values (JSONB-based, ADR-04 + ADR-05)
# ============================================================


class PeriodValue(Base, TimestampMixin):
    """Помесячные/годовые значения показателей.

    Гранулярность: (project_sku_channel × scenario × period × source × version).
    Все показатели хранятся в JSONB-колонке `values` одной строкой:
        {"nd": 0.45, "offtake": 12.3, "shelf_price": 89.50,
         "volume_units": 12345.6, "net_revenue": 1234567.89, ...}

    Это решение из ADR-04 (≈7 740 строк вместо 387 000 при EAV).

    Слой данных в `source_type` (predict/finetuned/actual). Приоритет
    при отображении: actual > finetuned > predict (ADR-05).
    """

    __tablename__ = "period_values"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    psk_channel_id: Mapped[int] = mapped_column(
        ForeignKey("project_sku_channels.id", ondelete="CASCADE"),
        nullable=False,
    )
    scenario_id: Mapped[int] = mapped_column(
        ForeignKey("scenarios.id", ondelete="CASCADE"),
        nullable=False,
    )
    period_id: Mapped[int] = mapped_column(
        ForeignKey("periods.id", ondelete="RESTRICT"),
        nullable=False,
    )

    values: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    source_type: Mapped[SourceType] = mapped_column(
        varchar_enum(SourceType, "source_type"),
        nullable=False,
        default=SourceType.PREDICT,
    )
    version_id: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_overridden: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    __table_args__ = (
        UniqueConstraint(
            "psk_channel_id", "scenario_id", "period_id", "source_type", "version_id",
            name="uq_period_values_unique_layer",
        ),
    )


class ProjectFinancialPlan(Base, TimestampMixin):
    """Project-level CAPEX и periodic OPEX по периодам.

    Хранит инвестиционные затраты (CAPEX) и дискретные операционные
    затраты проекта (project_opex — листинги, запускной маркетинг и т.п.,
    Excel DATA row 26/33) на уровне всего проекта, привязанные к
    конкретному period_id.

    Эти величины не зависят от ProjectSKU/Channel — это затраты
    проекта целиком. В оркестраторе (`engine/pipeline.run_project_pipeline`)
    они применяются на уровне агрегата по линиям, не суммируются с
    per-line capex/opex.

    Если для какого-то period_id записи нет — capex и opex трактуются
    как 0. UNIQUE(project_id, period_id) гарантирует не более одной
    записи на (проект × период).
    """

    __tablename__ = "project_financial_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    period_id: Mapped[int] = mapped_column(
        ForeignKey("periods.id", ondelete="RESTRICT"),
        nullable=False,
    )
    capex: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), nullable=False, default=Decimal("0")
    )
    opex: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), nullable=False, default=Decimal("0")
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id", "period_id",
            name="uq_project_financial_plans_project_period",
        ),
    )


class ScenarioResult(Base):
    """Финансовые KPI последнего расчёта сценария на заданном горизонте."""

    __tablename__ = "scenario_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scenario_id: Mapped[int] = mapped_column(
        ForeignKey("scenarios.id", ondelete="CASCADE"),
        nullable=False,
    )
    period_scope: Mapped[PeriodScope] = mapped_column(
        varchar_enum(PeriodScope, "period_scope", length=10),
        nullable=False,
    )

    # Денежные значения — Numeric(20, 2): до 18 цифр целой части, 2 копейки.
    npv: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    irr: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    # ROI расширен до Numeric(20, 6) из-за Excel D-06 quirk:
    # при всех положительных FCF формула ROI вырождается в `SUM(FCF) / N`
    # — абсолютное среднее в рублях, а не ratio. Это может давать числа
    # порядка миллионов при проектах без CAPEX Y0. См. ERRORS_AND_ISSUES
    # запись "ROI numeric overflow" и TZ_VS_EXCEL_DISCREPANCIES.md D-06.
    roi: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    payback_simple: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    payback_discounted: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    contribution_margin: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 6), nullable=True
    )
    ebitda_margin: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)

    go_no_go: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "scenario_id", "period_scope",
            name="uq_scenario_results_scenario_scope",
        ),
    )
