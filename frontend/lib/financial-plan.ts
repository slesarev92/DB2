/**
 * API обёртки для ProjectFinancialPlan — CAPEX/OPEX per-period.
 *
 * B.9b (2026-05-15): per-period контракт.
 * Backend endpoints:
 *   GET /api/projects/{id}/financial-plan → всегда 43 строки (period_number 1..43)
 *   PUT /api/projects/{id}/financial-plan — полная замена
 */

import { apiGet, apiPut } from "./api";

import type { FinancialPlanItem, FinancialPlanRequest } from "@/types/api";

export function getFinancialPlan(
  projectId: number,
): Promise<FinancialPlanItem[]> {
  return apiGet<FinancialPlanItem[]>(
    `/api/projects/${projectId}/financial-plan`,
  );
}

export function putFinancialPlan(
  projectId: number,
  body: FinancialPlanRequest,
): Promise<FinancialPlanItem[]> {
  return apiPut<FinancialPlanItem[]>(
    `/api/projects/${projectId}/financial-plan`,
    body,
  );
}
