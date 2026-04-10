/**
 * AI endpoint клиент (Фаза 7.2).
 *
 * POST /api/projects/{id}/ai/explain-kpi — объяснение KPI сценария
 * через Polza AI. Поддерживает AbortController для отмены долгого
 * запроса кнопкой в UI.
 *
 * Graceful degradation: при 503 (Polza недоступен) endpoint возвращает
 * placeholder detail; при 429 — превышен лимит; при 404 — данные не
 * найдены. Все эти случаи ловим через ApiError в вызывающем компоненте.
 */

import { apiPost } from "./api";

import type {
  AIKpiExplanationRequest,
  AIKpiExplanationResponse,
} from "@/types/api";

export async function requestExplainKpi(
  projectId: number,
  body: AIKpiExplanationRequest,
  options?: { signal?: AbortSignal },
): Promise<AIKpiExplanationResponse> {
  return apiPost<AIKpiExplanationResponse>(
    `/api/projects/${projectId}/ai/explain-kpi`,
    body,
    { signal: options?.signal },
  );
}

/**
 * Грубая оценка стоимости для pre-flight label в кнопке.
 *
 * Значения синхронизированы с `backend/app/services/ai_usage.py`
 * `estimate_cost_for_feature`. Эти эмпирические, не точные.
 *
 * Для точного cost после вызова — `response.cost_rub` из ответа.
 */
export const AI_FEATURE_COST_ESTIMATES_RUB: Record<string, number> = {
  explain_kpi: 3,
  explain_sensitivity: 2,
  freeform_chat: 5,
  executive_summary: 10,
  content_field: 0.5,
  marketing_research: 20,
  package_mockup: 8,
};

export function formatCostRub(cost: string | number): string {
  const num = typeof cost === "string" ? parseFloat(cost) : cost;
  if (Number.isNaN(num)) return "— ₽";
  if (num < 0.01) return "< 0.01 ₽";
  return `${num.toFixed(2)} ₽`;
}
