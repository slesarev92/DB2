/**
 * Справочные данные для HelpButton — описание каждого редактируемого
 * параметра в UI паспорта проекта.
 *
 * Источник истины формул: `PASSPORT_MODEL_GORJI_2025-09-05.xlsx` +
 * `docs/TZ_VS_EXCEL_DISCREPANCIES.md` (D-01..D-22 решения).
 *
 * Convention:
 * - `title` — человеческое название (русский).
 * - `description` — 1-2 предложения про смысл.
 * - `impact` — на какие downstream KPI/шаги pipeline влияет.
 * - `formula` — формула из Excel-эталона (краткая).
 * - `units` — единицы измерения (0-1, ₽, %, шт, кг).
 * - `range` — типичные границы или "0..1".
 * - `defaultValue` — значение по умолчанию.
 * - `excelRef` — где смотреть в PASSPORT_MODEL_GORJI (лист + строки).
 */

export interface ParameterHelp {
  title: string;
  description: string;
  impact?: string;
  formula?: string;
  units?: string;
  range?: string;
  defaultValue?: string;
  excelRef?: string;
}

export const PARAMETER_HELP: Record<string, ParameterHelp> = {
  // ============================================================
  // Project — финансовые параметры (Overview / Financial Plan)
  // ============================================================

  "project.wacc": {
    title: "WACC — ставка дисконтирования",
    description:
      "Средневзвешенная стоимость капитала. Используется как ставка для дисконтирования будущих денежных потоков (FCF) при расчёте NPV.",
    impact: "NPV на всех горизонтах (Y1-Y3 / Y1-Y5 / Y1-Y10), IRR сравнивается с WACC для Go/No-Go.",
    formula: "NPV = Σ FCF[t] / (1+WACC)^t",
    units: "доля (0-1)",
    range: "0.10 .. 0.30 (10-30%)",
    defaultValue: "0.19 (19%, GORJI эталон)",
    excelRef: "DATA, параметры проекта",
  },

  "project.tax_rate": {
    title: "Ставка налога на прибыль",
    description:
      "Налог на прибыль юрлица (в РФ — 20%). Применяется к Contribution Margin, а не к EBITDA (D-03).",
    impact: "OCF через Tax, NPV, ROI.",
    formula: "TAX[t] = IF(CONTRIBUTION[t] ≥ 0, CONTRIBUTION[t] × TAX_RATE, 0)",
    units: "доля (0-1)",
    range: "0.15 .. 0.25",
    defaultValue: "0.20 (20%)",
    excelRef: "DATA, раздел налоги",
  },

  "project.wc_rate": {
    title: "WC Rate — ставка оборотного капитала",
    description:
      "Доля Net Revenue которая замораживается в оборотном капитале (товар на складах + дебиторка − кредиторка). Используется для расчёта ΔWC — одного из компонентов OCF.",
    impact: "Δ Working Capital в OCF (D-01). На ранних периодах сильно уменьшает OCF, в зрелости стабилизируется.",
    formula: "WC[t] = NET_REVENUE[t] × WC_RATE\nΔWC[t] = WC[t-1] − WC[t]",
    units: "доля от NR",
    range: "0.08 .. 0.20",
    defaultValue: "0.12 (12%)",
    excelRef: "DATA, строки 38-41",
  },

  "project.vat_rate": {
    title: "Ставка НДС проекта",
    description:
      "Применяется только для пересчёта цены отгрузки (ex-factory) от полочной цены (с НДС). На себестоимость BOM не влияет — цены сырья и упаковки вводятся без НДС (Q7 от 2026-05-15).",
    impact: "Ex-factory цена → Net Revenue → весь P&L.",
    formula: "EX_FACTORY = SHELF_PRICE / (1 + VAT_RATE) × (1 − CHANNEL_MARGIN)",
    units: "доля (0-1)",
    range: "0.22 — стандартная с 01.01.2026; 0.20 — до 01.01.2026; 0.10 — льготная; 0.00 — экспорт",
    defaultValue: "0.22 (РФ с 01.01.2026)",
    excelRef: "DASH, строки 33-35",
  },

  "project.cm_threshold": {
    title: "Порог Contribution Margin для Go/No-Go",
    description:
      "Минимальный CM (в долях NR) для автоматического решения Go. Настраивается per-project — в разных категориях разные нормы (beverages 40%+, personal care 25-30%, food 15-20%). Исправлено в LOGIC-02 (было захардкожено 25%).",
    impact: "Go/No-Go флаг в ScenarioResult, gate decision.",
    formula: "GO = (CM ≥ CM_THRESHOLD) AND (NPV ≥ 0) AND (IRR ≥ WACC)",
    units: "доля (0-1)",
    range: "0.15 .. 0.40",
    defaultValue: "0.25 (25%)",
    excelRef: "s12_gonogo в engine/",
  },

  "project.tax_loss_carryforward": {
    title: "Перенос налоговых убытков (ст.283 НК РФ)",
    description:
      "Если включён — убыточные годы Y1-Y2 уменьшают налоговую базу прибыльных Y3-Y5 (cap 50% прибыли года). Реалистично для launch-проектов. Выкл — Excel-compat baseline (налог=0 при убытке, без переноса).",
    impact: "Annual tax → OCF → FCF → NPV/IRR/Payback. Для типичных launch-проектов NPV выше на 2-5%.",
    formula:
      "С флагом: taxable[t] = CM[t] − min(cumulative_loss, 0.5×CM[t])\ntax[t] = −taxable × tax_rate",
    units: "boolean",
    defaultValue: "false (Excel-compat)",
    excelRef: "D-24 в TZ_VS_EXCEL_DISCREPANCIES.md",
  },

  "project.horizon_years": {
    title: "Горизонт планирования",
    description:
      "Сколько лет моделируем. Стандарт FMCG — 10 лет (до Y10). Первые 3 года помесячно (M1-M36), остальные годами (Y4-Y10).",
    impact: "Длина pipeline (43 периода = 36 мес + 7 лет), расчёт Terminal Value.",
    units: "лет",
    range: "5 .. 10",
    defaultValue: "10",
  },

  "project.start_date": {
    title: "Дата старта проекта",
    description:
      "Первый месяц модели (M1). От неё отсчитываются launch lag каналов и CAPEX timeline. Не обязательно 1 января.",
    units: "дата",
    defaultValue: "текущий квартал",
  },

  "project.currency": {
    title: "Валюта проекта",
    description:
      "Валюта всех денежных значений. Для РФ-проектов — RUB. Экспорт в Excel/PDF использует её для форматирования (₽ / $ / €).",
    range: "RUB / USD / EUR",
    defaultValue: "RUB",
  },

  // ============================================================
  // ProjectSKU — параметры SKU в проекте
  // ============================================================

  "project_sku.production_cost_rate": {
    title: "Ставка себестоимости производства (own)",
    description:
      "Процент от ex-factory цены на производственные затраты (амортизация линии, труд, электричество). Применяется только при production_mode=own (собственное).",
    impact: "COGS через Production Cost в s03_cogs.",
    formula: "PRODUCTION_COST = EX_FACTORY × PRODUCTION_COST_RATE (per unit)",
    units: "доля (0-1)",
    range: "0.10 .. 0.40",
    defaultValue: "0.25 (25%)",
    excelRef: "DATA production cost column",
  },

  "project_sku.production_mode": {
    title: "Тип производства — собственное или копакинг",
    description:
      "«Собственное» — линия компании, себестоимость считается как % от ex-factory. «Копакинг» — контрактное производство, фиксированная ставка ₽/единица (copacking_rate). Добавлено в LOGIC-01.",
    impact: "Формула COGS в s03_cogs: own vs copacking.",
    range: "own / copacking",
    defaultValue: "own",
  },

  "project_sku.copacking_rate": {
    title: "Ставка копакинга (₽/ед)",
    description:
      "Фиксированная плата контрактному производителю за единицу. Используется только при production_mode=copacking.",
    impact: "COGS через copacking cost в s03_cogs.",
    formula: "COGS += UNITS × COPACKING_RATE",
    units: "₽ / ед",
    range: "5 .. 50 ₽/ед",
    defaultValue: "0 (если own)",
  },

  "project_sku.ca_m_rate": {
    title: "CA&M — Customer Activation & Marketing (% от NR)",
    description:
      "Маркетинговые активности направленные на ритейлера и полку (trade marketing, listing fees, POS materials). Процент от Net Revenue.",
    impact: "Contribution через CA&M cost в s06_ebitda.",
    formula: "CA&M = NET_REVENUE × CA_M_RATE",
    units: "доля от NR",
    range: "0.02 .. 0.15",
    defaultValue: "0.05 (5%)",
    excelRef: "OPEX, CA&M row",
  },

  "project_sku.marketing_rate": {
    title: "Marketing — бренд-маркетинг (% от NR)",
    description:
      "Бренд-маркетинг: ТВ, цифра, PR, креатив. В отличие от CA&M направлен на потребителя, не на ритейл. Процент от Net Revenue.",
    impact: "EBITDA через Marketing cost в s06_ebitda.",
    formula: "MARKETING = NET_REVENUE × MARKETING_RATE",
    units: "доля от NR",
    range: "0.03 .. 0.20",
    defaultValue: "0.08 (8%)",
    excelRef: "OPEX, Marketing row",
  },

  // ============================================================
  // Channel (ProjectSKUChannel) — параметры канала для SKU
  // ============================================================

  "channel.nd_target": {
    title: "ND Target — целевая численная дистрибуция",
    description:
      "Доля розничных точек канала которые будут листинговать SKU к стабильному состоянию. 0.6 = 60% точек. Взвешиваем по объёму (больше магазины = больший вклад).",
    impact: "Volume в s01_volume. ND × OFFTAKE × UNIVERSE = объём продаж.",
    formula: "UNITS = UNIVERSE × ND[t] × OFFTAKE[t]",
    units: "доля (0-1)",
    range: "0.05 .. 0.95",
    defaultValue: "зависит от канала",
    excelRef: "VOLUME, ND ramp-up",
  },

  "channel.nd_ramp_months": {
    title: "Период рамп-апа ND",
    description:
      "Сколько месяцев нужно чтобы дистрибуция выросла от 0 до ND Target. Линейный рост. Первые месяцы — низкое ND, к концу ramp периода — target.",
    impact: "Volume на старте проекта (launch curve).",
    formula: "ND[t] = min(t / RAMP_MONTHS, 1) × ND_TARGET",
    units: "месяцев",
    range: "3 .. 18",
    defaultValue: "6",
    excelRef: "VOLUME",
  },

  "channel.offtake_target": {
    title: "Offtake — продажи с полки (ед/точка/период)",
    description:
      "Сколько единиц в среднем продаётся на одной листингованной точке за период. Зависит от активации, цены, промо.",
    impact: "Volume. ND × OFFTAKE × UNIVERSE.",
    units: "ед/точка/мес",
    range: "1 .. 200",
    defaultValue: "зависит от SKU и канала",
    excelRef: "VOLUME, Offtake rows",
  },

  "channel.shelf_price_reg": {
    title: "Цена полки (регулярная)",
    description:
      "Розничная цена с НДС в обычные недели (без промо). Для расчёта ex-factory делится на (1+VAT) и умножается на (1-channel_margin). См. D-02.",
    impact: "Net Revenue, Ex-Factory, COGS margins.",
    formula: "EX_FACTORY = SHELF / (1+VAT) × (1−CHANNEL_MARGIN)",
    units: "₽ (с НДС)",
    range: "50 .. 500 ₽",
    defaultValue: "зависит от tier",
    excelRef: "DASH, shelf price rows",
  },

  "channel.shelf_price_promo": {
    title: "Цена полки (промо)",
    description:
      "Розничная цена в недели промо-акций. Обычно 15-40% ниже регулярной. Взвешивается через promo_share.",
    impact: "Weighted shipping price.",
    formula: "SHIPPING_W = SHIPPING_REG × (1−PROMO_SHARE) + SHIPPING_PROMO × PROMO_SHARE",
    units: "₽ (с НДС)",
    range: "50 .. 500 ₽",
  },

  "channel.channel_margin": {
    title: "Маржа канала (ритейла)",
    description:
      "Процент который ритейлер закладывает между ex-factory ценой и полкой. X5 / Магнит — 25-30%, маркетплейсы — 15-25%, HoReCa — 100%+.",
    impact: "Ex-factory цена → Net Revenue.",
    formula: "EX_FACTORY = SHELF / (1+VAT) × (1 − CHANNEL_MARGIN)",
    units: "доля (0-1)",
    range: "0.10 .. 0.40",
    defaultValue: "0.25 (25%)",
  },

  "channel.promo_discount": {
    title: "Глубина промо-скидки",
    description:
      "Процент снижения цены в недели промо относительно регулярной. 0.30 = 30% off.",
    impact: "Weighted price в недели промо.",
    formula: "SHELF_PROMO = SHELF_REG × (1 − PROMO_DISCOUNT)",
    units: "доля (0-1)",
    range: "0 .. 0.50",
    defaultValue: "0.20 (20%)",
  },

  "channel.promo_share": {
    title: "Доля недель промо",
    description:
      "Какая доля периодов в году идёт с промо-ценой. 0.25 = каждая 4-я неделя промо.",
    impact: "Взвешенная shipping price (mix regular + promo).",
    formula: "SHIPPING_W = SHIPPING_REG × (1−PROMO_SHARE) + SHIPPING_PROMO × PROMO_SHARE",
    units: "доля (0-1)",
    range: "0 .. 0.50",
    defaultValue: "0.15 (15%)",
  },

  "channel.universe_outlets": {
    title: "Universe — общее количество точек канала",
    description:
      "Сколько всего розничных точек в канале (без учёта листинга). X5 ≈ 20000, Магнит ≈ 25000, Wildberries — точки выдачи. Multipl на ND даёт фактическое число листинговых точек.",
    impact: "Volume: UNIVERSE × ND × OFFTAKE.",
    units: "шт",
    range: "100 .. 50000",
    defaultValue: "зависит от канала",
    excelRef: "VOLUME, universe row",
  },

  "channel.launch_month": {
    title: "Месяц запуска в канале",
    description:
      "С какого месяца начинается продажи в канале (может быть позже старта проекта — например HoReCa через 3 месяца после retail). D-13.",
    impact: "Volume до launch = 0, ND ramp начинается с launch_month.",
    units: "номер месяца",
    range: "1 .. 36",
    defaultValue: "1",
  },

  // ============================================================
  // BOMItem — компоненты рецептуры SKU
  // ============================================================

  "bom.quantity_per_unit": {
    title: "Количество на единицу SKU",
    description:
      "Сколько этого ингредиента уходит на одну единицу готовой продукции (бутылку / упаковку).",
    impact: "BOM unit cost.",
    formula: "UNIT_COST = Σ (QUANTITY × PRICE) × (1 + LOSS_PCT) × (1 + VAT_RATE)",
    units: "кг / мл / шт",
  },

  "bom.loss_pct": {
    title: "Процент потерь / отходов",
    description:
      "Запланированные технологические потери при производстве. 5% = реально расходуется 1.05× от расчётного quantity.",
    impact: "BOM unit cost (увеличивает).",
    units: "доля (0-1)",
    range: "0 .. 0.10",
    defaultValue: "0.03 (3%)",
  },

  "bom.price_per_unit": {
    title: "Цена закупки (за единицу)",
    description:
      "Стоимость 1 кг/мл/шт сырья у поставщика. Без НДС (НДС добавляется через vat_rate).",
    impact: "BOM unit cost → COGS.",
    units: "₽ / ед",
  },

  "bom.vat_rate": {
    title: "НДС на ингредиент",
    description:
      "Ставка НДС для конкретного ингредиента. Продукты питания — 10%, лекарства — 0%, остальное — 20%. Переопределяет общий Project.vat_rate для этого BOM item (LOGIC-07).",
    impact: "BOM unit cost.",
    units: "доля (0-1)",
    range: "0.00 / 0.10 / 0.20",
    defaultValue: "Project.vat_rate",
  },

  // ============================================================
  // Scenario — дельты сценариев
  // ============================================================

  "scenario.delta_nd": {
    title: "Дельта ND (Conservative/Aggressive)",
    description:
      "Множитель к ND_TARGET для сценария. Conservative: 0.85 (-15%), Base: 1.0, Aggressive: 1.10 (+10%).",
    impact: "Volume через ND в sensitivity.",
    formula: "ND_SCENARIO = ND_BASE × (1 + DELTA_ND)",
    units: "доля (0-1)",
    range: "-0.30 .. +0.30",
    defaultValue: "Base: 0, Cons: -0.15, Aggr: +0.10",
  },

  "scenario.delta_offtake": {
    title: "Дельта Offtake",
    description:
      "Множитель к OFFTAKE для сценария.",
    impact: "Volume через offtake.",
    formula: "OFFTAKE_SCENARIO = OFFTAKE_BASE × (1 + DELTA_OFFTAKE)",
    units: "доля (0-1)",
    range: "-0.30 .. +0.30",
    defaultValue: "Base: 0, Cons: -0.10, Aggr: +0.05",
  },

  "scenario.delta_opex": {
    title: "Дельта OPEX",
    description:
      "Множитель к маркетинговым и операционным расходам для сценария.",
    impact: "Marketing + CA&M + logistics.",
    units: "доля",
    range: "-0.30 .. +0.30",
  },

  "scenario.delta_shelf_price": {
    title: "Дельта цены полки (4.5)",
    description:
      "Project-wide сдвиг shelf_price_reg в сценарии. Моделирует риск ценовых переговоров с ритейлом (-10% на давление сетей) или премиум-позиционирование (+15%).",
    impact: "Net Revenue → GP → CM → EBITDA → FCF → NPV/IRR.",
    formula: "SHELF[t] = SHELF_BASE[t] × (1 + DELTA_SHELF)",
    units: "% к Base",
    range: "-50 .. +50%",
    defaultValue: "0%",
    excelRef: "нет (новое в 4.5 engine audit)",
  },

  "scenario.delta_bom_cost": {
    title: "Дельта себестоимости BOM (4.5)",
    description:
      "Project-wide сдвиг BOM unit cost (сырьё + упаковка). Моделирует инфляцию сырья (+15%) или снижение через локализацию поставщика (-10%).",
    impact: "COGS материалов → GP → CM → EBITDA → FCF → NPV/IRR.",
    formula: "BOM[t] = BOM_BASE[t] × (1 + DELTA_BOM)",
    units: "% к Base",
    range: "-50 .. +50%",
    defaultValue: "0%",
    excelRef: "нет (новое в 4.5 engine audit)",
  },

  "scenario.delta_logistics": {
    title: "Дельта логистики (4.5)",
    description:
      "Project-wide сдвиг logistics_cost_per_kg. Моделирует рост тарифов перевозчиков (+20%) или оптимизацию маршрутов (-10%).",
    impact: "Logistics cost → CM → EBITDA → FCF → NPV/IRR.",
    formula: "LOG[t] = LOG_BASE[t] × (1 + DELTA_LOG)",
    units: "% к Base",
    range: "-30 .. +50%",
    defaultValue: "0%",
    excelRef: "нет (новое в 4.5 engine audit)",
  },

  // ============================================================
  // FinancialPlan — CAPEX / OPEX per year
  // ============================================================

  "financial_plan.capex": {
    title: "CAPEX — капитальные затраты",
    description:
      "Инвестиции в оборудование, линии, запуск. Распределяются по годам. Вычитаются из FCF при расчёте NPV.",
    impact: "FCF = OCF − CAPEX. NPV.",
    formula: "FCF[t] = OCF[t] − CAPEX[t]",
    units: "₽",
    range: "0 .. 1 000 000 000",
    defaultValue: "0 (если нет инвестиций в год)",
    excelRef: "DATA, CAPEX row",
  },

  "financial_plan.opex": {
    title: "OPEX — операционные расходы",
    description:
      "Фиксированные операционные расходы не связанные с объёмом (ЗП АУП, аренда, IT). Отличается от переменного OPEX (CA&M, marketing) который считается как % от NR.",
    impact: "Contribution через OPEX cost в s05_contribution.",
    units: "₽",
    range: "0 .. 100 000 000",
  },

  // ============================================================
  // PeriodValue — fine-tuning помесячно
  // ============================================================

  "period_value.nd": {
    title: "ND в периоде (fine-tune)",
    description:
      "Ручная корректировка ND для конкретного (SKU × канал × период). Применяется поверх predict/scenario значения (три слоя: Predict > Finetuned > Actual).",
    impact: "Volume этого месяца.",
    units: "доля (0-1)",
    range: "0 .. 1",
  },

  "period_value.offtake": {
    title: "Offtake в периоде (fine-tune)",
    description:
      "Ручная корректировка offtake для конкретного (SKU × канал × период). Полезно для учёта сезонности сверху автоматики.",
    impact: "Volume этого месяца.",
    units: "ед/точка/мес",
  },

  "period_value.shelf_price": {
    title: "Цена полки в периоде (fine-tune)",
    description:
      "Ручная корректировка розничной цены в конкретном периоде. Учитывает инфляцию, локальные акции, переоценки.",
    impact: "Net Revenue этого месяца.",
    units: "₽ (с НДС)",
  },
};
