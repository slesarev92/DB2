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
