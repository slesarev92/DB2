"""Dataclass-контейнеры для расчётного pipeline.

Структура:
- `PipelineInput` — иммутабельный вход, который service формирует из БД
  (ProjectSKU × ProjectSKUChannel × 43 PeriodValue + настройки проекта).
  Pipeline сам в БД не ходит.
- `PipelineContext` — мутабельный контейнер, через который шаги передают
  промежуточные результаты. Каждый шаг читает нужные поля из ctx и пишет
  свои. `ctx.input` — константа, её никто не меняет.

Все числовые данные — float (не Decimal). Обоснование — CLAUDE.md раздел
"Архитектурные паттерны", пункт 6: Excel работает в float (double),
~15 знаков точности для NPV в миллионах рублей более чем достаточно.
Decimal используется только на границе БД ↔ memory (при формировании
PipelineInput service конвертирует Decimal → float).

Один экземпляр PipelineInput описывает **одну линию** расчёта — конкретный
(ProjectSKU × Channel × Scenario). Аггрегация по SKU/каналам выполняется
в оркестраторе (задача 2.4), не внутри шагов.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PipelineInput:
    """Иммутабельный вход pipeline для одной (ProjectSKU × Channel × Scenario).

    Все списки индексированы по `period_index` в диапазоне [0, period_count).
    Порядок периодов — как в справочнике `periods` (M1..M36, Y4..Y10 = 43 шт).
    """

    # --- Метаданные (для логов и сохранения результатов, не для расчёта) ---
    project_sku_channel_id: int
    scenario_id: int

    # --- Временная ось ---
    period_count: int
    # True для M1..M36, False для Y4..Y10. Сезонность применяется только
    # к monthly; для годовых периодов seasonality[t] = 1.0 по соглашению.
    period_is_monthly: tuple[bool, ...]
    # Номер месяца 1..12 для monthly, None для yearly.
    period_month_num: tuple[int | None, ...]
    # Модельный год 1..10 (нужен для дисконтирования в s10, сейчас не используется).
    period_model_year: tuple[int, ...]

    # --- Помесячные/годовые показатели (effective значения после применения
    #     scenario-дельт и приоритета слоёв actual > finetuned > predict) ---
    nd: tuple[float, ...]              # Numeric Distribution, доли (0..1)
    offtake: tuple[float, ...]         # units per outlet per period
    shelf_price_reg: tuple[float, ...] # регулярная цена полки, ₽/unit, с инфляцией
    seasonality: tuple[float, ...]     # коэффициент сезонности для monthly, 1.0 для yearly

    # --- Статические параметры канала/SKU ---
    universe_outlets: int           # Channel.universe_outlets
    channel_margin: float           # ProjectSKUChannel.channel_margin (доля, 0..1)
    promo_discount: float           # ProjectSKUChannel.promo_discount (доля, 0..1)
    promo_share: float              # ProjectSKUChannel.promo_share (доля 0..1)

    vat_rate: float                 # Project.vat_rate (доля)

    # --- COGS-компоненты на единицу продукции ---
    # Σ BOMItem.quantity_per_unit × price_per_unit × (1 + loss_pct).
    # В текущей модели BOMItem не разделяет material/package — это
    # лампованная сумма. Позже можно разделить без изменения pipeline.
    bom_unit_cost: float            # ₽/unit, постоянная на горизонте (в MVP)
    production_cost_rate: float     # ProjectSKU.production_cost_rate (доля от ex_factory)
    copacking_per_unit: float       # ₽/unit. В MVP всегда 0.0 (нет поля в схеме).

    # --- Логистика ---
    logistics_cost_per_kg: float    # ProjectSKUChannel.logistics_cost_per_kg, ₽/кг
    sku_volume_l: float             # SKU.volume_l, литров на единицу

    # --- EBITDA-компоненты (% от Net Revenue, ProjectSKU level) ---
    ca_m_rate: float                # КАиУР % (Excel: DASH row 41 СА&М)
    marketing_rate: float           # Маркетинг % (Excel: DASH row 42)

    # --- Project-level финансовые параметры (Project model) ---
    wc_rate: float                  # Working Capital ratio (default 0.12). D-01.
    tax_rate: float                 # Profit tax rate (default 0.20). D-03.

    product_density: float = 1.0    # кг/л. Для напитков ≈ 1.0 (D-09).

    # --- Project OPEX ---
    # Дискретные периодические затраты проекта (листинги, запускной маркетинг).
    # В Excel — DATA row 26 "PROJECT_OPEX". В MVP источник данных ещё не
    # реализован — дефолт нули по всему горизонту.
    project_opex: tuple[float, ...] = ()

    # --- Инвестиции (CAPEX) ---
    # Per-period CAPEX. В Excel — DATA row 33. На уровне (SKU × Channel)
    # capex обычно 0 — это project-level затраты, которые добавляются
    # оркестратором (задача 2.4). Если пусто, трактуется как нули по всему
    # горизонту.
    capex: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        # Валидация длин массивов. Падаем рано и с понятной ошибкой —
        # легче дебажить чем молчаливый IndexError глубоко в шагах.
        n = self.period_count
        for name, seq in [
            ("period_is_monthly", self.period_is_monthly),
            ("period_month_num", self.period_month_num),
            ("period_model_year", self.period_model_year),
            ("nd", self.nd),
            ("offtake", self.offtake),
            ("shelf_price_reg", self.shelf_price_reg),
            ("seasonality", self.seasonality),
        ]:
            if len(seq) != n:
                raise ValueError(
                    f"PipelineInput.{name} has length {len(seq)}, expected {n}"
                )
        if self.project_opex and len(self.project_opex) != n:
            raise ValueError(
                f"PipelineInput.project_opex has length {len(self.project_opex)}, "
                f"expected {n} or 0 (empty = zeros)"
            )
        if self.capex and len(self.capex) != n:
            raise ValueError(
                f"PipelineInput.capex has length {len(self.capex)}, "
                f"expected {n} or 0 (empty = zeros)"
            )


@dataclass
class PipelineContext:
    """Мутабельный контейнер промежуточных результатов шагов 1..N.

    Каждый шаг проверяет в начале своих pre-conditions (нужные поля
    предыдущих шагов должны быть заполнены) и записывает свои поля.
    Все списки — длины `input.period_count`.
    """

    input: PipelineInput

    # --- После s01_volume ---
    active_outlets: list[float] = field(default_factory=list)  # universe_outlets × nd
    volume_units: list[float] = field(default_factory=list)    # active × offtake × seasonality
    volume_liters: list[float] = field(default_factory=list)   # volume_units × sku_volume_l

    # --- После s02_price ---
    shelf_price_promo: list[float] = field(default_factory=list)
    shelf_price_weighted: list[float] = field(default_factory=list)
    ex_factory_price: list[float] = field(default_factory=list)
    net_revenue: list[float] = field(default_factory=list)

    # --- После s03_cogs (компоненты и сумма) ---
    cogs_material: list[float] = field(default_factory=list)    # bom_unit_cost × volume
    cogs_production: list[float] = field(default_factory=list)  # ex_factory × rate × volume
    cogs_copacking: list[float] = field(default_factory=list)   # copacking × volume
    cogs_total: list[float] = field(default_factory=list)

    # --- После s04_gross_profit ---
    # GP = NET_REVENUE − COGS (без логистики — соответствует Excel DATA!row 23).
    gross_profit: list[float] = field(default_factory=list)

    # --- После s05_contribution ---
    logistics_cost: list[float] = field(default_factory=list)   # logistics_cost_per_kg × kg
    contribution: list[float] = field(default_factory=list)     # GP − LOGISTICS − PROJECT_OPEX

    # --- После s06_ebitda ---
    ca_m_cost: list[float] = field(default_factory=list)        # NR × ca_m_rate
    marketing_cost: list[float] = field(default_factory=list)   # NR × marketing_rate
    ebitda: list[float] = field(default_factory=list)           # CM − ca_m − marketing

    # --- После s07_working_capital (D-01 / ADR-CE-02) ---
    working_capital: list[float] = field(default_factory=list)  # NR × wc_rate
    delta_working_capital: list[float] = field(default_factory=list)  # wc[t-1] − wc[t]

    # --- После s08_tax (D-03 / ADR-CE-04) ---
    # Знак отрицательный (отток) — складывается с CM напрямую в OCF.
    tax: list[float] = field(default_factory=list)              # -(CM × tax_rate) если CM≥0, иначе 0

    # --- После s09_cash_flow ---
    operating_cash_flow: list[float] = field(default_factory=list)    # CM + ΔWC + tax
    investing_cash_flow: list[float] = field(default_factory=list)    # -capex
    free_cash_flow: list[float] = field(default_factory=list)         # OCF + ICF
