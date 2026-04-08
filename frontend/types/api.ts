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

export interface ProjectBase {
  name: string;
  start_date: string; // ISO date "YYYY-MM-DD"
  horizon_years: number;
  wacc: string; // Decimal as string
  tax_rate: string;
  wc_rate: string;
  vat_rate: string;
  currency: string;
  inflation_profile_id: number | null;
}

export interface ProjectCreate extends ProjectBase {}

export interface ProjectUpdate {
  name?: string;
  start_date?: string;
  horizon_years?: number;
  wacc?: string;
  tax_rate?: string;
  wc_rate?: string;
  vat_rate?: string;
  currency?: string;
  inflation_profile_id?: number | null;
}

export interface ProjectRead extends ProjectBase {
  id: number;
  created_at: string;
  updated_at: string | null;
  created_by: number | null;
}

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

export interface ProjectSKUCreate {
  sku_id: number;
  include?: boolean;
  production_cost_rate?: string;
  ca_m_rate?: string;
  marketing_rate?: string;
}

export interface ProjectSKUUpdate {
  include?: boolean;
  production_cost_rate?: string;
  ca_m_rate?: string;
  marketing_rate?: string;
}

export interface ProjectSKURead {
  id: number;
  project_id: number;
  sku_id: number;
  sku: SKURead;
  include: boolean;
  production_cost_rate: string;
  ca_m_rate: string;
  marketing_rate: string;
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
}

export interface BOMItemUpdate {
  ingredient_name?: string;
  quantity_per_unit?: string;
  loss_pct?: string;
  price_per_unit?: string;
}

export interface BOMItemRead {
  id: number;
  project_sku_id: number;
  ingredient_name: string;
  quantity_per_unit: string;
  loss_pct: string;
  price_per_unit: string;
  created_at: string;
}

// ============================================================
// Channel (глобальный справочник, read-only)
// ============================================================

export interface Channel {
  id: number;
  code: string;
  name: string;
  universe_outlets: number | null;
  created_at: string;
}

// ============================================================
// ProjectSKUChannel (PSC — параметры SKU в конкретном канале)
// ============================================================

export interface ProjectSKUChannelCreate {
  channel_id: number;
  nd_target?: string;
  nd_ramp_months?: number;
  offtake_target?: string;
  channel_margin?: string;
  promo_discount?: string;
  promo_share?: string;
  shelf_price_reg?: string;
  logistics_cost_per_kg?: string;
  seasonality_profile_id?: number | null;
}

export interface ProjectSKUChannelUpdate {
  nd_target?: string;
  nd_ramp_months?: number;
  offtake_target?: string;
  channel_margin?: string;
  promo_discount?: string;
  promo_share?: string;
  shelf_price_reg?: string;
  logistics_cost_per_kg?: string;
  seasonality_profile_id?: number | null;
}

export interface ProjectSKUChannelRead {
  id: number;
  project_sku_id: number;
  channel_id: number;
  channel: Channel;
  nd_target: string;
  nd_ramp_months: number;
  offtake_target: string;
  channel_margin: string;
  promo_discount: string;
  promo_share: string;
  shelf_price_reg: string;
  logistics_cost_per_kg: string;
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
  notes: string | null;
  created_at: string;
}

export interface ScenarioUpdate {
  delta_nd?: string;
  delta_offtake?: string;
  delta_opex?: string;
  notes?: string | null;
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
  calculated_at: string;
}
