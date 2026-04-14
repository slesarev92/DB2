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
    CheckConstraint,
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
    """Справочник каналов сбыта (HM, SM, MM, TT, E-COM_OZ, E-COM_OZ_Fresh).

    B-05: поле `region` для региональной детализации. Если NULL —
    канал общефедеральный. Если заполнено (напр. "Москва", "Урал") —
    региональная версия канала. UNIQUE(code) гарантирует уникальность
    кода (напр. "HM_MSK", "HM_URAL").
    """

    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
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

    # Go/No-Go порог Contribution Margin (настраиваемый, одобрено заказчиком 2026-04-13).
    cm_threshold: Mapped[Decimal] = mapped_column(
        Numeric(8, 6), nullable=False, default=Decimal("0.25"),
        server_default="0.250000",
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

    # ============================================================
    # Контент паспорта (Фаза 4.5)
    # ============================================================
    # 16 scalar text/varchar fields + 5 JSONB fields для всех текстовых
    # блоков паспорта в стиле PASSPORT_ELEKTRA. Заполняются вручную в
    # таб «Содержание» (4.5.3) и через AI генерацию (Phase 7.6).

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    gate_stage: Mapped[str | None] = mapped_column(
        String(10), nullable=True
    )  # G0..G5, CHECK constraint в __table_args__
    passport_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    project_owner: Mapped[str | None] = mapped_column(String(200), nullable=True)
    project_goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    innovation_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    geography: Mapped[str | None] = mapped_column(Text, nullable=True)
    production_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    growth_opportunity: Mapped[str | None] = mapped_column(Text, nullable=True)
    concept_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    idea_short: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_audience: Mapped[str | None] = mapped_column(Text, nullable=True)
    replacement_target: Mapped[str | None] = mapped_column(Text, nullable=True)
    technology: Mapped[str | None] = mapped_column(Text, nullable=True)
    rnd_progress: Mapped[str | None] = mapped_column(Text, nullable=True)
    executive_summary: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # AI-generated в Phase 7.6

    # JSONB fields для structured content
    risks: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    validation_tests: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    function_readiness: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    roadmap_tasks: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    approvers: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    # Phase 8.9: Nielsen бенчмарки рынка (per канал/регион).
    # Структура: list[dict] — channel, universe_outlets, offtake, nd_pct,
    # avg_price, category_value_share. Не валидируется, гибкая схема.
    nielsen_benchmarks: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    # Phase 8.10: КП на производство (детальные котировки копакеров).
    # Структура: list[dict] — supplier, item, unit, price_per_unit, moq,
    # lead_time_days, note. Гибкая схема, не валидируется.
    supplier_quotes: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)

    # ============================================================
    # AI-генерированный контент (Фаза 7.4, ADR-16 решение #5)
    # ============================================================
    # Экспорт НИКОГДА не вызывает AI live — читает из этих полей.
    # Flow: generate → draft → edit → save → export.

    # Текст executive summary от AI (может быть отредактирован аналитиком).
    # Если NULL — секция executive summary в PPT/PDF пропускается.
    ai_executive_summary: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )

    # Cached KPI commentary (structured JSON):
    # {"<scenario_id>": {"<scope>": {"summary","drivers","risks",...}}}
    # Переиспользуется при повторных экспортах без обращения к Polza.
    ai_kpi_commentary: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )

    # Cached sensitivity commentary (structured JSON):
    # {"<scenario_id>": {"narrative","most_sensitive_param",...}}
    ai_sensitivity_commentary: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )

    # Когда и кем последний раз обновлялся AI-контент (для audit).
    ai_commentary_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ai_commentary_updated_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # ============================================================
    # AI Budget (Фаза 7.5)
    # ============================================================
    # Месячный лимит AI-расходов проекта в рублях. NULL = без лимита.
    # Default 500₽ (ADR-16 решение #6). Обновляется через
    # PATCH /api/projects/{id}/ai/budget.
    ai_budget_rub_monthly: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True, server_default="500.00"
    )

    # ============================================================
    # AI Marketing Research (Фаза 7.7)
    # ============================================================
    # JSONB multi-topic storage:
    # {"competitive_analysis": {"text": "...", "sources": [...],
    #   "key_findings": [...], "generated_at": "...", "cost_rub": 15.4,
    #   "model": "..."}, "market_size": {...}, ...}
    # NULL = ни одного research не генерировалось.
    marketing_research: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )

    # Soft delete: устанавливается при DELETE /api/projects/{id}.
    # Все запросы фильтруют WHERE deleted_at IS NULL.
    # Финансовый продукт — данные не теряем при ошибочном удалении.
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        # 4.5.1: gate_stage ограничен G0..G5 (или NULL для проектов без
        # фиксированного гейта)
        CheckConstraint(
            "gate_stage IS NULL OR gate_stage IN ('G0', 'G1', 'G2', 'G3', 'G4', 'G5')",
            name="ck_projects_gate_stage",
        ),
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


class ScenarioChannelDelta(Base, TimestampMixin):
    """Per-SKU/Channel дельты сценария (B-06).

    Позволяет задать отдельные delta_nd/delta_offtake для конкретного
    (scenario × psk_channel). Если записи нет — используется delta
    уровня сценария (Scenario.delta_nd/delta_offtake) как fallback.
    """

    __tablename__ = "scenario_channel_deltas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scenario_id: Mapped[int] = mapped_column(
        ForeignKey("scenarios.id", ondelete="CASCADE"),
        nullable=False,
    )
    psk_channel_id: Mapped[int] = mapped_column(
        ForeignKey("project_sku_channels.id", ondelete="CASCADE"),
        nullable=False,
    )
    delta_nd: Mapped[Decimal] = mapped_column(
        Numeric(8, 6), nullable=False, default=Decimal("0")
    )
    delta_offtake: Mapped[Decimal] = mapped_column(
        Numeric(8, 6), nullable=False, default=Decimal("0")
    )

    __table_args__ = (
        UniqueConstraint(
            "scenario_id", "psk_channel_id",
            name="uq_scenario_channel_deltas_scenario_psc",
        ),
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

    # Режим производства: own (собственное) или copacking (контрактное).
    # Определяет структуру COGS в pipeline (s03_cogs):
    # - own: production_cost = ex_factory × production_cost_rate × volume; copacking = 0
    # - copacking: copacking = copacking_rate × volume; production_cost = 0
    production_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="own"
    )
    copacking_rate: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), nullable=False, default=Decimal("0")
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

    # 4.5.1: изображение упаковки SKU. Загружается через media upload
    # в `bom-panel.tsx` (4.5.3) или генерируется AI в Phase 7.8.
    # ON DELETE SET NULL — если пользователь удалит файл, FK обнуляется,
    # row ProjectSKU остаётся.
    package_image_id: Mapped[int | None] = mapped_column(
        ForeignKey("media_assets.id", ondelete="SET NULL"),
        nullable=True,
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

    # Launch lag (D-13): канал может быть запущен не в M1 проекта, а позже.
    # Excel хранит launch_year/launch_month per (SKU × Channel), не per SKU.
    # TT/E-COM каналы запускаются раньше HM/SM/MM для одного SKU
    # (классические каналы дают первичную дистрибуцию для тестирования
    # рынка, modern trade подключаются позже). По умолчанию канал активен
    # с M1 проекта (Y1 Jan). Сервис `_build_line_input` обнуляет nd[t] и
    # offtake[t] для periods до launch периода — downstream pipeline
    # автоматически даёт ноль через volume = active × offtake × seasonality.
    launch_year: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1", default=1
    )
    launch_month: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1", default=1
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


# ============================================================
# Ingredients catalog (B-04)
# ============================================================


class Ingredient(Base, TimestampMixin):
    """Справочник ингредиентов (сырьё, упаковка, прочее).

    Глобальный каталог — не привязан к проекту. BOMItem может ссылаться
    на ingredient через FK для auto-fill имени и цены.
    """

    __tablename__ = "ingredients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    unit: Mapped[str] = mapped_column(
        String(50), nullable=False, default="kg"
    )
    category: Mapped[str] = mapped_column(
        String(100), nullable=False, default="raw_material"
    )

    prices: Mapped[list["IngredientPrice"]] = relationship(
        "IngredientPrice",
        back_populates="ingredient",
        cascade="all, delete-orphan",
        lazy="raise_on_sql",
    )

    __table_args__ = (
        CheckConstraint(
            "category IN ('raw_material', 'packaging', 'other')",
            name="ck_ingredients_category",
        ),
    )


class IngredientPrice(Base, TimestampMixin):
    """История цен ингредиента.

    Каждая запись = цена за единицу, действующая с effective_date.
    Актуальная цена = MAX(effective_date) WHERE effective_date <= today.
    """

    __tablename__ = "ingredient_prices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ingredient_id: Mapped[int] = mapped_column(
        ForeignKey("ingredients.id", ondelete="CASCADE"),
        nullable=False,
    )
    price_per_unit: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), nullable=False
    )
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    ingredient: Mapped["Ingredient"] = relationship(
        "Ingredient",
        back_populates="prices",
        lazy="raise_on_sql",
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
    # LOGIC-07: НДС ингредиента (справочная информация, не влияет на COGS).
    # Типичные значения: 0.00 (нулевая), 0.10 (льготная для продуктов),
    # 0.20 (стандартная в РФ). Используется только для закупочной справки.
    vat_rate: Mapped[Decimal] = mapped_column(
        Numeric(8, 6), nullable=False, default=Decimal("0.20")
    )
    # B-04: optional link to ingredient catalog for auto-pricing
    ingredient_id: Mapped[int | None] = mapped_column(
        ForeignKey("ingredients.id", ondelete="SET NULL"),
        nullable=True,
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

    # relationship для selectinload в service
    opex_items: Mapped[list["OpexItem"]] = relationship(
        "OpexItem",
        back_populates="financial_plan",
        cascade="all, delete-orphan",
        lazy="raise_on_sql",
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id", "period_id",
            name="uq_project_financial_plans_project_period",
        ),
    )


class OpexItem(Base, TimestampMixin):
    """Статья OPEX в разбивке ProjectFinancialPlan.

    Каждая запись — одна статья расходов (листинги, запускной маркетинг,
    и т.п.) для конкретного (проект × период). Сумма всех items =
    ProjectFinancialPlan.opex (backend автоматически пересчитывает
    при наличии items). CASCADE DELETE через FK: удаление
    ProjectFinancialPlan удаляет все его items.
    """

    __tablename__ = "opex_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    financial_plan_id: Mapped[int] = mapped_column(
        ForeignKey("project_financial_plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Phase 8.8: категория OPEX (Digital, TV, OOH, PR, SMM, ...).
    # Non-null с server_default="other" для backward compat старых записей.
    category: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="other", default="other"
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    amount: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), nullable=False, default=Decimal("0")
    )

    financial_plan: Mapped["ProjectFinancialPlan"] = relationship(
        "ProjectFinancialPlan",
        back_populates="opex_items",
        lazy="raise_on_sql",
    )

    __table_args__ = (
        # 8.8: UNIQUE расширен до (plan, category, name) — одно имя может
        # встречаться в разных категориях (напр. "Тесты" в Research и Product).
        UniqueConstraint(
            "financial_plan_id", "category", "name",
            name="uq_opex_items_plan_category_name",
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

    # Per-unit метрики (Phase 8.3): scope-averaged NR/GP/CM/EBITDA
    # делённые на total_units / total_liters / total_kg за scope.
    # Numeric(15,4) — до 11 цифр целой части + 4 дробных. Для ₽/шт достаточно.
    nr_per_unit: Mapped[Decimal | None] = mapped_column(Numeric(15, 4), nullable=True)
    gp_per_unit: Mapped[Decimal | None] = mapped_column(Numeric(15, 4), nullable=True)
    cm_per_unit: Mapped[Decimal | None] = mapped_column(Numeric(15, 4), nullable=True)
    ebitda_per_unit: Mapped[Decimal | None] = mapped_column(Numeric(15, 4), nullable=True)

    nr_per_liter: Mapped[Decimal | None] = mapped_column(Numeric(15, 4), nullable=True)
    gp_per_liter: Mapped[Decimal | None] = mapped_column(Numeric(15, 4), nullable=True)
    cm_per_liter: Mapped[Decimal | None] = mapped_column(Numeric(15, 4), nullable=True)
    ebitda_per_liter: Mapped[Decimal | None] = mapped_column(Numeric(15, 4), nullable=True)

    nr_per_kg: Mapped[Decimal | None] = mapped_column(Numeric(15, 4), nullable=True)
    gp_per_kg: Mapped[Decimal | None] = mapped_column(Numeric(15, 4), nullable=True)
    cm_per_kg: Mapped[Decimal | None] = mapped_column(Numeric(15, 4), nullable=True)
    ebitda_per_kg: Mapped[Decimal | None] = mapped_column(Numeric(15, 4), nullable=True)

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


# ============================================================
# Media assets (Фаза 4.5 — file storage для package images, concept designs)
# ============================================================


class MediaAsset(Base):
    """Загруженный файл (изображение упаковки, концепт-дизайн, и т.д.).

    Связан с проектом (CASCADE при удалении проекта). Может быть связан
    с конкретным ProjectSKU через `ProjectSKU.package_image_id`
    (ON DELETE SET NULL).

    Файлы хранятся в Docker volume `media_storage:/media` (4.5.2),
    путь `/media/{project_id}/{kind}/{uuid}_{filename}` записывается
    в `storage_path`. Чтение через `media_service.read_media_file()`,
    отдача через `GET /api/media/{id}` с правильным MIME.

    Без TimestampMixin — у нас отдельная `created_at` колонка с
    server_default (нет updated_at, asset immutable после upload).
    """

    __tablename__ = "media_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Тип контента: package_image (упаковка SKU), concept_design (mockup
    # от AI), other (прочие attachments). Расширяется при необходимости.
    kind: Mapped[str] = mapped_column(String(32), nullable=False)

    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    uploaded_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        # 4.5.1 + 7.8: kind whitelist расширен для AI reference и generated
        CheckConstraint(
            "kind IN ('package_image', 'concept_design', 'ai_reference', "
            "'ai_generated', 'other')",
            name="ck_media_assets_kind",
        ),
    )


# ============================================================
# AI generated images (Фаза 7.8 — package mockup gallery)
# ============================================================


class AIGeneratedImage(Base):
    """Сгенерированное AI-изображение упаковки (Phase 7.8).

    Хранит все генерации для SKU — аналитик листает галерею и выбирает
    лучший вариант через "Сделать основным" (→ ProjectSKU.package_image_id).

    Pipeline: reference image → Claude vision (art direction) → flux (image).
    Оба шага логируются: art_direction (текст от Claude) и media_asset
    (результат flux). cost_rub = сумма обоих вызовов.
    """

    __tablename__ = "ai_generated_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_sku_id: Mapped[int] = mapped_column(
        ForeignKey("project_skus.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Сгенерированное изображение (flux output, сохранённое как MediaAsset)
    media_asset_id: Mapped[int] = mapped_column(
        ForeignKey("media_assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Reference-изображение (логотип, бренд-гайд), nullable — генерация
    # без reference допустима
    reference_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("media_assets.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Пользовательский промпт (что попросил аналитик)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Art direction от Claude vision (детальное описание для flux)
    art_direction: Mapped[str] = mapped_column(Text, nullable=False)
    # Суммарная стоимость (vision + generation)
    cost_rub: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    model: Mapped[str] = mapped_column(String(100), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )


# ============================================================
# AI usage log (Фаза 7.1, ADR-16)
# ============================================================


# ============================================================
# AKB — Active retail base / distribution plan (B-12)
# ============================================================


class AKBEntry(Base, TimestampMixin):
    """План дистрибуции по каналам (B-12).

    Одна строка = один канал в проекте с метриками покрытия:
    universe (сколько ТТ в канале), target (сколько планируем охватить),
    coverage % и weighted distribution. Дополняет ProjectSKUChannel.nd_target
    данными о физической базе торговых точек.

    UNIQUE(project_id, channel_id): один канал — одна запись.
    """

    __tablename__ = "akb_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="RESTRICT"),
        nullable=False,
    )

    universe_outlets: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    target_outlets: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    coverage_pct: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 6), nullable=True
    )
    weighted_distribution: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 6), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    channel: Mapped["Channel"] = relationship(lazy="raise_on_sql")

    __table_args__ = (
        UniqueConstraint(
            "project_id", "channel_id",
            name="uq_akb_entries_project_channel",
        ),
    )


# ============================================================
# OBPPC — Price-Pack-Channel matrix (B-13)
# ============================================================


class OBPPCEntry(Base, TimestampMixin):
    """Стратегическая матрица Price-Pack-Channel (B-13).

    Одна строка = одна комбинация (SKU × канал × pack format)
    с ценовым позиционированием и стратегическими параметрами.

    UNIQUE(project_id, sku_id, channel_id, pack_format): одна уникальная
    комбинация per project.
    """

    __tablename__ = "obppc_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    sku_id: Mapped[int] = mapped_column(
        ForeignKey("skus.id", ondelete="RESTRICT"),
        nullable=False,
    )
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="RESTRICT"),
        nullable=False,
    )

    occasion: Mapped[str | None] = mapped_column(String(200), nullable=True)
    price_tier: Mapped[str] = mapped_column(
        String(50), nullable=False, default="mainstream"
    )
    pack_format: Mapped[str] = mapped_column(
        String(100), nullable=False, default="bottle"
    )
    pack_size_ml: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_point: Mapped[Decimal | None] = mapped_column(
        Numeric(15, 4), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    sku: Mapped["SKU"] = relationship(lazy="raise_on_sql")
    channel: Mapped["Channel"] = relationship(lazy="raise_on_sql")

    __table_args__ = (
        UniqueConstraint(
            "project_id", "sku_id", "channel_id", "pack_format",
            name="uq_obppc_entries_project_sku_channel_pack",
        ),
        CheckConstraint(
            "price_tier IN ('premium', 'mainstream', 'value')",
            name="ck_obppc_entries_price_tier",
        ),
    )


class AIUsageLog(Base):
    """Журнал вызовов Polza AI — для cost monitoring и debugging.

    Таблица создаётся в Phase 7.1 (базовая инфра), но активное
    логирование включается в Phase 7.5 — endpoint'ы из 7.2..7.4
    будут писать сюда после каждого вызова `ai_service.complete_json`.
    Phase 7.5 добавляет budget enforcement: перед вызовом проверяется
    SUM(cost_rub) WHERE project_id=X AND created_at >= start_of_month
    против Project.ai_budget_rub_monthly (поле добавляется в 7.5).

    `project_id` — nullable: часть AI-вызовов может быть не привязана
    к конкретному проекту (например, будущие admin-операции). Для 7.2..7.8
    заполняется всегда.

    `error` — nullable text: при успехе NULL, при failure сохраняем
    message+type (без stack trace — не нужно в audit log).

    `cost_rub` — nullable Decimal(12, 6): калькулируется в 7.5 по
    токенам × Polza pricing. В 7.1 NULL, так как ничего не логируется
    активно — таблица пустая.

    Без TimestampMixin: updated_at бессмыслен (лог-запись immutable),
    created_at с server_default достаточно.
    """

    __tablename__ = "ai_usage_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Phase 7.5: кто выполнил вызов — для per-user daily budget.
    # Nullable для backward compat со старыми записями (до 7.5).
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Какой сервис-метод / endpoint выполнил вызов — для агрегации
    # расходов по фичам в 7.5 (например, 'explain_kpi', 'marketing_research').
    endpoint: Mapped[str] = mapped_column(String(100), nullable=False)
    # Модель в Polza-формате "<provider>/<model_id>", например
    # "anthropic/claude-sonnet-4.6" (с точкой — формат Polza, см.
    # reference_polza_ai_gotchas memory + ERRORS_AND_ISSUES запись).
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    # Рубли с точностью до 6 знаков: Polza pricing per 1k tokens может
    # быть дробным (например, 0.000003 ₽ за токен).
    cost_rub: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 6), nullable=True
    )
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


# ============================================================
# Chat Conversations (Phase 7.3 — persistence)
# ============================================================


class ChatConversation(Base):
    """Разговор в AI-чате. Связывает серию сообщений с проектом и юзером.

    title — автоматически из первых ~80 символов первого вопроса.
    deleted_at — soft delete (паттерн #4 из CLAUDE.md).
    """

    __tablename__ = "chat_conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="conversation",
        lazy="raise_on_sql",
        order_by="ChatMessage.created_at",
    )


class ChatMessage(Base):
    """Одно сообщение в AI-чате (user или assistant).

    model / cost_rub / prompt_tokens / completion_tokens — заполняются
    только для role=assistant после завершения streaming.
    """

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("chat_conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(
        String(20), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cost_rub: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 6), nullable=True
    )
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    conversation: Mapped["ChatConversation"] = relationship(
        back_populates="messages", lazy="raise_on_sql"
    )

    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant')",
            name="ck_chat_messages_role",
        ),
    )
