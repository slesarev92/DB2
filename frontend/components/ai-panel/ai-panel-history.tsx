"use client";

/**
 * History widget — AI вызовы из backend (Phase 7.5).
 *
 * Читает recent_calls из useAIPanel() context, который fetched
 * из GET /api/projects/{id}/ai/usage при mount + refreshUsage.
 * Также показывает runtime-only history для текущей сессии.
 */

import { formatCostRub } from "@/lib/ai";
import { useAIPanel } from "./ai-panel-context";

const ENDPOINT_LABELS: Record<string, string> = {
  explain_kpi: "Explain KPI",
  explain_kpi_cache: "Explain KPI (cache)",
  explain_kpi_dedupe: "Explain KPI (dedupe)",
  explain_sensitivity: "Sensitivity",
  explain_sensitivity_cache: "Sensitivity (cache)",
  freeform_chat: "Chat",
  executive_summary: "Executive Summary",
  executive_summary_cache: "Exec Summary (cache)",
  content_field: "Content field",
  marketing_research: "Market research",
  package_mockup: "Package mockup",
};

export function AIPanelHistory() {
  const { recentCalls, usageLoading } = useAIPanel();

  if (usageLoading) {
    return (
      <p className="text-xs text-muted-foreground">Загрузка истории…</p>
    );
  }

  if (recentCalls.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        История пустая. Вызовите любую AI-функцию — она появится здесь.
      </p>
    );
  }

  return (
    <ol className="space-y-2 text-xs">
      {recentCalls.map((call) => (
        <li
          key={call.id}
          className="rounded-md border p-2"
        >
          <div className="flex items-center justify-between">
            <span className="font-medium">
              {ENDPOINT_LABELS[call.endpoint] ?? call.endpoint}
            </span>
            <span className="text-muted-foreground">
              {call.cost_rub !== null ? formatCostRub(call.cost_rub) : "—"}
              {call.cached ? " · cached" : ""}
            </span>
          </div>
          <div className="mt-1 flex items-center justify-between text-muted-foreground">
            <span className="truncate">{call.model}</span>
            <span>
              {call.latency_ms > 0 ? `${call.latency_ms}ms` : ""}
              {" · "}
              {new Date(call.timestamp).toLocaleTimeString("ru-RU", {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
          </div>
          {call.error && (
            <div className="mt-1 truncate text-red-500">{call.error}</div>
          )}
        </li>
      ))}
    </ol>
  );
}
