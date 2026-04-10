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
import { getAccessToken } from "./auth";

import type {
  AIChatSSEEvent,
  AIKpiExplanationRequest,
  AIKpiExplanationResponse,
  AISensitivityExplanationRequest,
  AISensitivityExplanationResponse,
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

export async function requestExplainSensitivity(
  projectId: number,
  body: AISensitivityExplanationRequest,
  options?: { signal?: AbortSignal },
): Promise<AISensitivityExplanationResponse> {
  return apiPost<AISensitivityExplanationResponse>(
    `/api/projects/${projectId}/ai/explain-sensitivity`,
    body,
    { signal: options?.signal },
  );
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * SSE streaming chat с Polza AI.
 *
 * Использует fetch + ReadableStream вместо EventSource, потому что
 * EventSource не поддерживает POST body и custom headers (Authorization).
 */
export async function streamChat(
  projectId: number,
  body: { question: string; conversation_id?: string | null; tier_override?: string | null },
  onEvent: (event: AIChatSSEEvent) => void,
  options?: { signal?: AbortSignal },
): Promise<void> {
  const token = getAccessToken();
  const resp = await fetch(
    `${API_URL}/api/projects/${projectId}/ai/chat`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
      signal: options?.signal,
    },
  );

  if (!resp.ok) {
    const detail = await resp.text();
    throw new Error(`Chat error ${resp.status}: ${detail}`);
  }

  const reader = resp.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        try {
          const event = JSON.parse(line.slice(6)) as AIChatSSEEvent;
          onEvent(event);
        } catch {
          // Corrupt SSE line — skip
        }
      }
    }
  }
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
