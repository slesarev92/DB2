"use client";

/**
 * History widget — последние 10 AI вызовов (Phase 7.2 local + 7.5 real).
 *
 * В 7.2: читает из `useAIPanel().history` — runtime-only state, заполняется
 * через `pushHistory` из inline-карточек. При refresh страницы история
 * теряется (это OK для MVP, persistent history = 7.5).
 *
 * В 7.5: real endpoint `GET /api/projects/{id}/ai/usage` + restore при
 * mount AI panel'а.
 */

import { formatCostRub } from "@/lib/ai";
import { useAIPanel } from "./ai-panel-context";

const FEATURE_LABELS: Record<string, string> = {
  explain_kpi: "Explain KPI",
  explain_sensitivity: "Sensitivity",
  freeform_chat: "Chat",
  executive_summary: "Executive Summary",
  content_field: "Content field",
  marketing_research: "Market research",
  package_mockup: "Package mockup",
};

export function AIPanelHistory() {
  const { history } = useAIPanel();

  if (history.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        История пустая. Вызовите любую AI-функцию — она появится здесь.
      </p>
    );
  }

  return (
    <ol className="space-y-2 text-xs">
      {history.map((entry, idx) => (
        <li
          key={`${entry.timestamp}-${idx}`}
          className="rounded-md border p-2"
        >
          <div className="flex items-center justify-between">
            <span className="font-medium">
              {FEATURE_LABELS[entry.feature] ?? entry.feature}
            </span>
            <span className="text-muted-foreground">
              {formatCostRub(entry.cost_rub)}
              {entry.cached ? " · cached" : ""}
            </span>
          </div>
          <div className="mt-1 truncate text-muted-foreground">
            {entry.model} · {entry.latency_ms}ms · {entry.project_name}
          </div>
        </li>
      ))}
    </ol>
  );
}
