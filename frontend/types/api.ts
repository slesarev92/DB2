/**
 * TypeScript типы для backend API ответов.
 *
 * Синхронизированы с Pydantic схемами backend/app/schemas/. При изменении
 * схем обновлять здесь вручную (нет генерации типов из FastAPI OpenAPI
 * в MVP — добавим позже если будут расхождения).
 *
 * Decimal поля приходят с backend как строки (Pydantic v2 → JSON для
 * Numeric колонок). Используем `string` тип, парсим в `Number()` или
 * `parseFloat()` при отображении.
 */

// ============================================================
// Auth (синхронизировано с lib/api.ts типами)
// ============================================================

export interface UserMe {
  id: number;
  email: string;
  role: string;
}

// ============================================================
// Project
// ============================================================

/** Gate-стадия процесса Stage-Gate (синхронизировано с backend CHECK). */
export type GateStage = "G0" | "G1" | "G2" | "G3" | "G4" | "G5";

/** Статус готовности функции. */
export type FunctionReadinessStatus = "green" | "yellow" | "red";

/** 8 фиксированных департаментов для блока «Готовность функций» (4.5). */
export const FUNCTION_DEPARTMENTS = [
  "R&D",
  "Marketing",
  "Sales",
  "Supply Chain",
  "Production",
  "Finance",
  "Legal",
  "Quality",
] as const;

export type FunctionDepartment = (typeof FUNCTION_DEPARTMENTS)[number];

/** Value в JSONB function_readiness: {department: {status, notes}}. */
export interface FunctionReadinessEntry {
  status: FunctionReadinessStatus;
  notes: string;
}

export type FunctionReadinessMap = Partial<
  Record<FunctionDepartment, FunctionReadinessEntry>
>;

/** Элемент validation_tests: 5 подтестов с score/notes. */
export interface ValidationTestEntry {
  score: number | null;
  notes: string;
}

export interface ValidationTests {
  concept_test?: ValidationTestEntry;
  naming?: ValidationTestEntry;
  design?: ValidationTestEntry;
  product?: ValidationTestEntry;
  price?: ValidationTestEntry;
}

/** Строка в risks[]: произвольный риск. */
export interface RiskItem {
  text: string;
}

/** Элемент roadmap_tasks[]. */
export interface RoadmapTask {
  name: string;
  start_date?: string; // YYYY-MM-DD
  end_date?: string;
  status?: string;
  owner?: string;
}

/** Элемент approvers[]. */
export interface Approver {
  metric: string;
  name: string;
  source?: string;
}

/** Элемент nielsen_benchmarks[] (Phase 8.9). */
export interface NielsenBenchmark {
  channel: string;
  universe_outlets?: number | null;
  offtake?: number | null;
  nd_pct?: number | null;
  avg_price?: number | null;
  category_value_share?: number | null;
  note?: string | null;
}

/** Элемент supplier_quotes[] (Phase 8.10). */
export interface SupplierQuote {
  supplier: string;
  item: string;
  unit?: string | null;
  price_per_unit?: number | null;
  moq?: number | null;
  lead_time_days?: number | null;
  note?: string | null;
}

/**
 * Content-поля паспорта (Фаза 4.5). Все optional на уровне input'ов
 * (POST/PATCH), в ProjectRead переопределены как required-nullable
 * через `Required<ProjectContentFields>`, чтобы UI мог безопасно
 * обращаться к каждому полю без `undefined`-ветки.
 */
export interface ProjectContentFields {
  // 16 scalar
  description?: string | null;
  gate_stage?: GateStage | null;
  passport_date?: string | null; // ISO date
  project_owner?: string | null;
  project_goal?: string | null;
  innovation_type?: string | null;
  geography?: string | null;
  production_type?: string | null;
  growth_opportunity?: string | null;
  concept_text?: string | null;
  rationale?: string | null;
  idea_short?: string | null;
  target_audience?: string | null;
  replacement_target?: string | null;
  technology?: string | null;
  rnd_progress?: string | null;
  executive_summary?: string | null;
  // 5 JSONB. Backend хранит как dict/list Any — типизируем для UI.
  risks?: RiskItem[] | null;
  validation_tests?: ValidationTests | null;
  function_readiness?: FunctionReadinessMap | null;
  roadmap_tasks?: RoadmapTask[] | null;
  approvers?: Approver[] | null;
  // Phase 8.9: Nielsen benchmarks
  nielsen_benchmarks?: NielsenBenchmark[] | null;
  // Phase 8.10: КП на производство (детальные котировки копакеров)
  supplier_quotes?: SupplierQuote[] | null;
  // Phase 7.5: AI budget
  ai_budget_rub_monthly?: string | null;
  // Phase 7.x: AI cached commentaries (persisted in DB)
  ai_executive_summary?: string | null;
  ai_kpi_commentary?: Record<string, unknown> | null;
  ai_sensitivity_commentary?: Record<string, unknown> | null;
  // Phase 7.7: Marketing research JSONB
  marketing_research?: Record<string, unknown> | null;
}

export interface ProjectBase extends ProjectContentFields {
  name: string;
  start_date: string; // ISO date "YYYY-MM-DD"
  horizon_years: number;
  wacc: string; // Decimal as string
  tax_rate: string;
  wc_rate: string;
  vat_rate: string;
  /**
   * 4.1 (ст.283 НК РФ): перенос убытков прошлых лет в налоговом расчёте.
   * Default false сохраняет Excel-совместимость; true — точнее для
   * launch-проектов (налог Y3-Y5 меньше на 10-20%, NPV выше).
   */
  tax_loss_carryforward?: boolean;
  currency: string;
  inflation_profile_id: number | null;
}

export interface ProjectCreate extends ProjectBase {}

export interface ProjectUpdate extends ProjectContentFields {
  name?: string;
  start_date?: string;
  horizon_years?: number;
  wacc?: string;
  tax_rate?: string;
  wc_rate?: string;
  vat_rate?: string;
  tax_loss_carryforward?: boolean;
  currency?: string;
  inflation_profile_id?: number | null;
}

/**
 * ProjectRead: все content-поля — required-nullable (backend всегда
 * сериализует их, даже если значение null). Это позволяет UI обращаться
 * к ним без `?.` проверок. Используем type alias с intersection, потому
 * что interface extension с conflicting optionality (optional в
 * ProjectBase vs required в Required<>) не работает.
 */
export type ProjectRead = Omit<ProjectBase, keyof ProjectContentFields> &
  Required<ProjectContentFields> & {
    id: number;
    created_at: string;
    updated_at: string | null;
    created_by: number | null;
  };

export interface ProjectListItem extends ProjectRead {
  npv_y1y10: string | null;
  irr_y1y10: string | null;
  go_no_go: boolean | null;
}

// ============================================================
// SKU (глобальный справочник)
// ============================================================

export interface SKUBase {
  brand: string;
  name: string;
  format: string | null;
  volume_l: string | null; // Decimal as string
  package_type: string | null;
  segment: string | null;
}

export interface SKUCreate extends SKUBase {}

export interface SKURead extends SKUBase {
  id: number;
  created_at: string;
}

// ============================================================
// ProjectSKU (включение SKU в проект)
// ============================================================

// Q6 (2026-05-15): ca_m_rate и marketing_rate переехали с ProjectSKU
// на ProjectSKUChannel — см. ProjectSKUChannelRead ниже.

export interface ProjectSKUCreate {
  sku_id: number;
  include?: boolean;
  production_mode?: string;
  copacking_rate?: string;
  production_cost_rate?: string;
  /** Q1 (2026-05-15): годовой override режима. Ключи "1".."10". */
  production_mode_by_year?: Record<string, string>;
  package_image_id?: number | null;
}

export interface ProjectSKUUpdate {
  include?: boolean;
  production_mode?: string;
  copacking_rate?: string;
  production_cost_rate?: string;
  production_mode_by_year?: Record<string, string>;
  package_image_id?: number | null;
}

export interface ProjectSKURead {
  id: number;
  project_id: number;
  sku_id: number;
  sku: SKURead;
  include: boolean;
  production_mode: string;
  copacking_rate: string;
  production_cost_rate: string;
  production_mode_by_year: Record<string, string>;
  package_image_id: number | null;
  created_at: string;
}

export interface ProjectSKUDetail extends ProjectSKURead {
  cogs_per_unit_estimated: string | null;
}

// ============================================================
// BOM Item (Bill of Materials)
// ============================================================

export interface BOMItemCreate {
  ingredient_name: string;
  quantity_per_unit: string;
  loss_pct?: string;
  price_per_unit?: string;
  vat_rate?: string;
  /**
   * Привязка к Ingredient из каталога. Если указан — backend автозаполнит
   * ingredient_name и latest price из каталога (B-04 в bom_service).
   */
  ingredient_id?: number | null;
}

export interface BOMItemUpdate {
  ingredient_name?: string;
  quantity_per_unit?: string;
  loss_pct?: string;
  price_per_unit?: string;
  vat_rate?: string;
}

export interface BOMItemRead {
  id: number;
  project_sku_id: number;
  ingredient_name: string;
  quantity_per_unit: string;
  loss_pct: string;
  price_per_unit: string;
  vat_rate: string;
  ingredient_id?: number | null;
  ingredient_category?: string | null;
  created_at: string;
}

// ============================================================
// Channel (глобальный справочник, B-05: region + CRUD)
// ============================================================

export interface Channel {
  id: number;
  code: string;
  name: string;
  region: string | null;
  universe_outlets: number | null;
  created_at: string;
}

// ============================================================
// ProjectSKUChannel (PSC — параметры SKU в конкретном канале)
// ============================================================

export interface ProjectSKUChannelCreate {
  channel_id: number;
  launch_year?: number;
  launch_month?: number;
  nd_target?: string;
  nd_ramp_months?: number;
  offtake_target?: string;
  channel_margin?: string;
  promo_discount?: string;
  promo_share?: string;
  shelf_price_reg?: string;
  logistics_cost_per_kg?: string;
  /** Q6 (2026-05-15): CA&M per-channel (% от Net Revenue этого канала). */
  ca_m_rate?: string;
  /** Q6 (2026-05-15): Marketing per-channel (% от Net Revenue этого канала). */
  marketing_rate?: string;
  seasonality_profile_id?: number | null;
}

export interface ProjectSKUChannelUpdate {
  launch_year?: number;
  launch_month?: number;
  nd_target?: string;
  nd_ramp_months?: number;
  offtake_target?: string;
  channel_margin?: string;
  promo_discount?: string;
  promo_share?: string;
  shelf_price_reg?: string;
  logistics_cost_per_kg?: string;
  ca_m_rate?: string;
  marketing_rate?: string;
  seasonality_profile_id?: number | null;
}

export interface ProjectSKUChannelRead {
  id: number;
  project_sku_id: number;
  channel_id: number;
  channel: Channel;
  launch_year: number;
  launch_month: number;
  nd_target: string;
  nd_ramp_months: number;
  offtake_target: string;
  channel_margin: string;
  promo_discount: string;
  promo_share: string;
  shelf_price_reg: string;
  logistics_cost_per_kg: string;
  ca_m_rate: string;
  marketing_rate: string;
  seasonality_profile_id: number | null;
  created_at: string;
}

// ============================================================
// Reference
// ============================================================

export interface RefInflation {
  id: number;
  profile_name: string;
  month_coefficients: {
    monthly_deltas?: number[];
    yearly_growth?: number[];
  };
}

export interface RefSeasonality {
  id: number;
  profile_name: string;
  month_coefficients: Record<string, unknown>;
}

// ============================================================
// Period (справочник 43 периодов)
// ============================================================

export type PeriodType = "monthly" | "annual";

export interface Period {
  id: number;
  type: PeriodType;
  period_number: number; // 1..43, sequential
  model_year: number; // 1..10
  month_num: number | null; // 1..12 для monthly, null для yearly
  start_date: string; // ISO date
  end_date: string;
}

// ============================================================
// PeriodValue (трёхслойная модель: predict / finetuned / actual)
// ============================================================

export type SourceType = "predict" | "finetuned" | "actual";

export type ViewMode = "hybrid" | "fact_only" | "plan_only" | "compare";

/** Hybrid / fact_only / plan_only response item — один эффективный слой. */
export interface PeriodHybridItem {
  period_id: number;
  period_number: number;
  source_type: SourceType;
  values: Record<string, number | string | null>;
  is_overridden: boolean;
}

/** Compare view item — все три слоя одновременно. */
export interface PeriodCompareItem {
  period_id: number;
  period_number: number;
  predict: Record<string, number | string | null> | null;
  finetuned: Record<string, number | string | null> | null;
  actual: Record<string, number | string | null> | null;
}

export interface PatchPeriodValueResponse {
  period_id: number;
  scenario_id: number;
  psk_channel_id: number;
  source_type: SourceType;
  version_id: number;
  is_overridden: boolean;
  values: Record<string, number | string | null>;
}

export interface ResetOverrideResponse {
  deleted_versions: number;
}

// ============================================================
// Scenario
// ============================================================

export type ScenarioType = "base" | "conservative" | "aggressive";
export type PeriodScope = "y1y3" | "y1y5" | "y1y10";

export interface ScenarioRead {
  id: number;
  project_id: number;
  type: ScenarioType;
  delta_nd: string;
  delta_offtake: string;
  delta_opex: string;
  /**
   * 4.5 — project-wide дельты к цене/COGS/логистике (risk-сценарии
   * "сырьё +15%", "логистика +25%"). Мультипликативны, в долях
   * (0.10 = +10%). Default "0".
   */
  delta_shelf_price?: string;
  delta_bom_cost?: string;
  delta_logistics?: string;
  notes: string | null;
  created_at: string;
}

export interface ScenarioUpdate {
  delta_nd?: string;
  delta_offtake?: string;
  delta_opex?: string;
  delta_shelf_price?: string;
  delta_bom_cost?: string;
  delta_logistics?: string;
  notes?: string | null;
}

/** Per-channel delta override (B-06). */
export interface ChannelDeltaItem {
  psk_channel_id: number;
  delta_nd: string;
  delta_offtake: string;
}

export interface ChannelDeltaRequest {
  items: ChannelDeltaItem[];
}

export interface ScenarioResultRead {
  id: number;
  scenario_id: number;
  period_scope: PeriodScope;
  npv: string | null;
  irr: string | null;
  roi: string | null;
  payback_simple: string | null;
  payback_discounted: string | null;
  contribution_margin: string | null;
  ebitda_margin: string | null;
  go_no_go: boolean | null;

  // Per-unit metrics (Phase 8.3)
  nr_per_unit: string | null;
  gp_per_unit: string | null;
  cm_per_unit: string | null;
  ebitda_per_unit: string | null;
  nr_per_liter: string | null;
  gp_per_liter: string | null;
  cm_per_liter: string | null;
  ebitda_per_liter: string | null;
  nr_per_kg: string | null;
  gp_per_kg: string | null;
  cm_per_kg: string | null;
  ebitda_per_kg: string | null;

  calculated_at: string;
  /**
   * F-01/F-02: true — данные проекта менялись после последнего расчёта,
   * UI должен показать `<StalenessBadge>`. Сбрасывается автоматически
   * при recalculate.
   */
  is_stale: boolean;
}

// ============================================================
// Recalculate / Tasks (Celery async job status)
// ============================================================

export interface RecalculateResponse {
  task_id: string;
  project_id: number;
  status: string;
}

export type CeleryTaskStatus =
  | "PENDING"
  | "STARTED"
  | "SUCCESS"
  | "FAILURE"
  | "RETRY"
  | "REVOKED";

export interface TaskStatusResponse {
  task_id: string;
  status: CeleryTaskStatus;
  result?: unknown;
  error?: string;
  traceback?: string;
}

// ============================================================
// Sensitivity analysis (4.4 / E-09)
// ============================================================

export interface SensitivityCell {
  parameter: "nd" | "offtake" | "shelf_price" | "cogs";
  delta: number; // -0.20, -0.10, 0.0, 0.10, 0.20
  npv_y1y10: number | null;
  cm_ratio: number | null;
}

export interface SensitivityResponse {
  scope: string;
  base_npv_y1y10: number | null;
  base_cm_ratio: number | null;
  deltas: number[];
  params: ("nd" | "offtake" | "shelf_price" | "cogs")[];
  cells: SensitivityCell[];
}

// ============================================================
// Ingredient catalog (B-04)
// ============================================================

export interface IngredientRead {
  id: number;
  name: string;
  unit: string;
  category: string;
  latest_price: string | null;
  created_at: string;
}

export interface IngredientPriceRead {
  id: number;
  ingredient_id: number;
  price_per_unit: string;
  effective_date: string;
  notes: string | null;
  created_at: string;
}

// ============================================================
// ProjectFinancialPlan (CAPEX/OPEX по годам проекта)
// ============================================================

/** Статья OPEX в разбивке (B-19 + 8.8 category). */
export interface OpexItem {
  category: string; // Phase 8.8: OPEX_CATEGORIES, default "other"
  name: string;
  amount: string; // Decimal as string
}

/** Phase 8.8: маркетинговые категории OPEX. */
export const OPEX_CATEGORIES = [
  "digital",
  "ecom",
  "ooh",
  "pr",
  "smm",
  "design",
  "research",
  "posm",
  "creative",
  "special",
  "merch",
  "tv",
  "listings",
  "other",
] as const;
export type OpexCategory = (typeof OPEX_CATEGORIES)[number];

export const OPEX_CATEGORY_LABELS: Record<OpexCategory, string> = {
  digital: "Диджитал",
  ecom: "Электронная коммерция",
  ooh: "Наружная реклама",
  pr: "PR",
  smm: "SMM",
  design: "Дизайн",
  research: "Исследования",
  posm: "POSM",
  creative: "Креатив",
  special: "Спецпроекты",
  merch: "Мерч",
  tv: "ТВ",
  listings: "Листинги",
  other: "Другое",
};

// ============================================================
// Единые русские переводы enum-значений (L-01..L-06 из аудита 2026-04-14).
// Импортировать отсюда во всех компонентах — не объявлять локальные дубли.
// ============================================================

/** Сценарии проекта. Backend enum: base / conservative / aggressive. */
export const SCENARIO_LABELS: Record<string, string> = {
  base: "Базовый",
  conservative: "Консервативный",
  aggressive: "Агрессивный",
};

/** Горизонт расчёта KPI. Оставлены как есть — индустриальная аббревиатура. */
export const SCOPE_LABELS: Record<string, string> = {
  y1y3: "Y1-Y3",
  y1y5: "Y1-Y5",
  y1y10: "Y1-Y10",
};

/** Тип периода. */
export const PERIOD_TYPE_LABELS: Record<string, string> = {
  monthly: "Месяцы",
  annual: "Годы",
};

/** Ценовой сегмент SKU. */
export const PRICE_TIER_LABELS: Record<string, string> = {
  premium: "Премиум",
  mainstream: "Мейнстрим",
  value: "Эконом",
};

/** Формат упаковки. */
export const PACK_FORMAT_LABELS: Record<string, string> = {
  bottle: "Бутылка",
  can: "Банка",
  pack: "Пакет",
  box: "Коробка",
  other: "Другое",
};

/** Слой значения периода (Predict / Fine-tuned / Actual). */
export const SOURCE_LABELS: Record<string, string> = {
  predict: "Прогноз",
  finetuned: "Ручная правка",
  actual: "Факт",
};

/** Параметры sensitivity (Tornado chart). */
export const SENSITIVITY_PARAM_LABELS: Record<string, string> = {
  nd: "Числ. дистрибуция",
  offtake: "Отгрузка (offtake)",
  shelf_price: "Цена полки",
  cogs: "Себестоимость",
};

/** Режим P&L таблицы. */
export const PNL_VIEW_MODE_LABELS: Record<string, string> = {
  monthly: "Месяцы",
  quarterly: "Кварталы",
  annual: "Годы",
};

/** AI endpoint labels в history panel. */
export const AI_ENDPOINT_LABELS: Record<string, string> = {
  explain_kpi: "Объяснение KPI",
  sensitivity: "Анализ чувствительности",
  executive_summary: "Резюме для руководства",
  generate_content: "Генерация контента",
  marketing_research: "Маркет-исследование",
  mockup: "Генерация макета",
  chat: "Чат с AI",
};

export interface FinancialPlanItem {
  year: number; // 1..10
  capex: string; // Decimal as string
  opex: string;
  opex_items: OpexItem[];
}

export interface FinancialPlanRequest {
  items: FinancialPlanItem[];
}

// ============================================================
// MediaAsset (Фаза 4.5.2 — загруженные файлы проекта)
// ============================================================

export type MediaKind = "package_image" | "concept_design" | "other";

export interface MediaAssetRead {
  id: number;
  project_id: number;
  kind: MediaKind;
  filename: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
  uploaded_by: number | null;
}

// ============================================================
// AI (Фаза 7, Polza AI — ADR-16)
// ============================================================

/**
 * Уровни моделей Polza AI. Используется в tier_override при Standard/Deep
 * toggle в UI. Backend enum `AIModelTier` — stable string ids.
 */
export type AIModelTier =
  | "fast_cheap"
  | "balanced"
  | "heavy"
  | "research"
  | "image";

/** AI-фичи для агрегации в usage logs / AI Panel history. */
export type AIFeature =
  | "explain_kpi"
  | "explain_sensitivity"
  | "freeform_chat"
  | "executive_summary"
  | "content_field"
  | "marketing_research"
  | "package_mockup";

/** Request body для POST /api/projects/{id}/ai/explain-kpi. */
export interface AIKpiExplanationRequest {
  scenario_id: number;
  scope: PeriodScope;
  /** null / undefined = default BALANCED. "heavy" = Deep analysis (opus). */
  tier_override?: AIModelTier | null;
}

/**
 * Response от /ai/explain-kpi. `cost_rub` приходит как string (Pydantic
 * Decimal → JSON string), парсим через Number() при отображении.
 */
export interface AIKpiExplanationResponse {
  summary: string;
  key_drivers: string[];
  risks: string[];
  recommendation: "go" | "no-go" | "review";
  confidence: number;
  rationale: string;
  cost_rub: string;
  model: string;
  cached: boolean;
}

/** Request body для POST /api/projects/{id}/ai/explain-sensitivity. */
export interface AISensitivityExplanationRequest {
  scenario_id: number;
  tier_override?: AIModelTier | null;
}

/** Response от /ai/explain-sensitivity (Phase 7.3). */
export interface AISensitivityExplanationResponse {
  most_sensitive_param: string;
  most_sensitive_impact: string;
  least_sensitive_param: string;
  narrative: string;
  actionable_levers: string[];
  warning_flags: string[];
  cost_rub: string;
  model: string;
  cached: boolean;
}

/** Request body для POST /api/projects/{id}/ai/chat (Phase 7.3). */
export interface AIChatRequest {
  question: string;
  conversation_id?: string | null;
  tier_override?: AIModelTier | null;
}

/** SSE event types from /ai/chat stream. */
export type AIChatSSEEvent =
  | { type: "conversation_id"; id: string }
  | { type: "token"; content: string }
  | { type: "done"; cost_rub: string; model: string }
  | { type: "error"; message: string };

/**
 * Запись в AI usage history (для AI Panel). В Phase 7.2 — локальный
 * mock state, реальный endpoint `/ai/usage` добавится в 7.5.
 */
export interface AIUsageHistoryEntry {
  timestamp: string;
  feature: AIFeature;
  model: string;
  cost_rub: string;
  latency_ms: number;
  project_id: number;
  project_name: string;
  cached: boolean;
}

// ============================================================
// AI Usage + Budget (Phase 7.5)
// ============================================================

export interface AIUsageDailyEntry {
  date: string;
  spent_rub: string;
  calls: number;
}

export interface AIUsageRecentCall {
  id: number;
  timestamp: string;
  endpoint: string;
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  cost_rub: string | null;
  latency_ms: number;
  error: string | null;
  cached: boolean;
}

// Marketing Research (Phase 7.7)
export type ResearchTopic =
  | "competitive_analysis"
  | "market_size"
  | "consumer_trends"
  | "category_benchmarks"
  | "custom";

export interface AIMarketingResearchResponse {
  topic: string;
  research_text: string;
  sources: Array<{ url: string; title: string; snippet: string }>;
  key_findings: string[];
  confidence_notes: string;
  generated_at: string;
  cost_rub: string;
  model: string;
  web_sources_used: boolean;
}

// Package Mockup (Phase 7.8)
export interface AIPackageMockupResponse {
  id: number;
  media_asset_id: number;
  media_url: string;
  art_direction: string;
  prompt: string;
  cost_rub: string;
  model: string;
}

export interface AIGeneratedImageRead {
  id: number;
  project_sku_id: number;
  media_asset_id: number;
  media_url: string;
  reference_asset_id: number | null;
  prompt_text: string;
  art_direction: string;
  cost_rub: string | null;
  model: string;
  created_at: string;
}

// ============================================================
// AKB — distribution plan (B-12)
// ============================================================

export interface AKBRead {
  id: number;
  project_id: number;
  channel_id: number;
  channel: { id: number; code: string; name: string };
  universe_outlets: number | null;
  target_outlets: number | null;
  coverage_pct: string | null; // Decimal as string
  weighted_distribution: string | null;
  notes: string | null;
  created_at: string;
}

// ============================================================
// OBPPC — Price-Pack-Channel matrix (B-13)
// ============================================================

export type PriceTier = "premium" | "mainstream" | "value";

export interface OBPPCRead {
  id: number;
  project_id: number;
  sku_id: number;
  sku: { id: number; brand: string; name: string };
  channel_id: number;
  channel: { id: number; code: string; name: string };
  occasion: string | null;
  price_tier: PriceTier;
  pack_format: string;
  pack_size_ml: number | null;
  price_point: string | null; // Decimal as string
  is_active: boolean;
  notes: string | null;
  created_at: string;
}

// ============================================================
// AI Usage
// ============================================================

export interface AIUsageResponse {
  project_id: number;
  month_start: string;
  spent_rub: string;
  budget_rub: string | null;
  budget_remaining_rub: string | null;
  budget_percent_used: number;
  daily_history: AIUsageDailyEntry[];
  recent_calls: AIUsageRecentCall[];
  cache_hit_rate_24h: number;
}
