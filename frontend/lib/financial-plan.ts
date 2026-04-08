/**
 * API обёртки для ProjectFinancialPlan — CAPEX/OPEX по годам.
 *
 * Backend endpoints:
 *   GET /api/projects/{id}/financial-plan → всегда 10 строк Y1..Y10
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
