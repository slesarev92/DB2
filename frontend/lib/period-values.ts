/**
 * API обёртки для PeriodValue — трёхслойная модель данных задачи 1.5.
 *
 * Backend endpoints:
 *   GET    /api/project-sku-channels/{id}/values?scenario_id=&view_mode=
 *   PATCH  /api/project-sku-channels/{id}/values/{period_id}?scenario_id=
 *   DELETE /api/project-sku-channels/{id}/values/{period_id}?scenario_id=
 *
 * View modes:
 *   hybrid     — приоритет actual > finetuned > predict (default)
 *   fact_only  — только actual
 *   plan_only  — finetuned (latest) или predict, исключает actual
 *   compare    — все три слоя в одной структуре
 *
 * PATCH создаёт **новую версию** finetuned (append-only). version_id
 * автоматически инкрементируется. Старые finetuned не удаляются.
 *
 * DELETE убирает все finetuned версии для (psc, scenario, period) —
 * "reset to predict". Возвращает количество удалённых строк.
 */

import { apiDelete, apiGet, apiPatch } from "./api";

import type {
  PatchPeriodValueResponse,
  PeriodCompareItem,
  PeriodHybridItem,
  ResetOverrideResponse,
  ViewMode,
} from "@/types/api";

export function listPeriodValuesHybrid(
  pskChannelId: number,
  scenarioId: number,
): Promise<PeriodHybridItem[]> {
  const params = new URLSearchParams({
    scenario_id: String(scenarioId),
    view_mode: "hybrid",
  });
  return apiGet<PeriodHybridItem[]>(
    `/api/project-sku-channels/${pskChannelId}/values?${params}`,
  );
}

export function listPeriodValues(
  pskChannelId: number,
  scenarioId: number,
  viewMode: ViewMode,
): Promise<PeriodHybridItem[] | PeriodCompareItem[]> {
  const params = new URLSearchParams({
    scenario_id: String(scenarioId),
    view_mode: viewMode,
  });
  return apiGet(
    `/api/project-sku-channels/${pskChannelId}/values?${params}`,
  );
}

export function patchPeriodValue(
  pskChannelId: number,
  periodId: number,
  scenarioId: number,
  values: Record<string, number | string | null>,
): Promise<PatchPeriodValueResponse> {
  const params = new URLSearchParams({ scenario_id: String(scenarioId) });
  return apiPatch<PatchPeriodValueResponse>(
    `/api/project-sku-channels/${pskChannelId}/values/${periodId}?${params}`,
    { values },
  );
}

export function resetPeriodOverride(
  pskChannelId: number,
  periodId: number,
  scenarioId: number,
): Promise<ResetOverrideResponse> {
  const params = new URLSearchParams({ scenario_id: String(scenarioId) });
  return apiDelete<ResetOverrideResponse>(
    `/api/project-sku-channels/${pskChannelId}/values/${periodId}?${params}`,
  );
}
