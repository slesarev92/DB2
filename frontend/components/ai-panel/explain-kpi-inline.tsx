"use client";

/**
 * Inline ✨ Explain KPI карточка (Phase 7.2).
 *
 * Размещается под Go/No-Go hero на ResultsTab. Flow:
 * 1. Пользователь видит кнопку "✨ Объяснить KPI (~3₽)"
 * 2. Клик → AbortController → POST /explain-kpi
 * 3. Во время запроса — inline loading с кнопкой "Отменить"
 * 4. Success → collapsible карточка: summary + drivers + risks +
 *    recommendation badge + confidence + rationale tooltip
 * 5. Error (503/429) → inline error message
 * 6. Tier toggle (Standard / Deep) — перед вторым вызовом можно
 *    переключиться на HEAVY (opus), чтобы получить глубже анализ
 *
 * Используется в ResultsTab.tsx при `selectedScenarioId !== null` и
 * наличии results для всех scope'ов.
 */

import { Sparkles, X } from "lucide-react";
import { useCallback, useRef, useState } from "react";

import { useAIPanel } from "./ai-panel-context";

import { ApiError } from "@/lib/api";
import {
  AI_FEATURE_COST_ESTIMATES_RUB,
  formatCostRub,
  requestExplainKpi,
} from "@/lib/ai";
import { cn } from "@/lib/utils";

import type {
  AIKpiExplanationResponse,
  AIModelTier,
  PeriodScope,
} from "@/types/api";

interface Props {
  projectId: number;
  projectName: string;
  scenarioId: number;
  scope: PeriodScope;
}

export function ExplainKpiInline({
  projectId,
  projectName,
  scenarioId,
  scope,
}: Props) {
  const { pushHistory } = useAIPanel();
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AIKpiExplanationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tier, setTier] = useState<AIModelTier>("balanced");
  const abortRef = useRef<AbortController | null>(null);

  const handleRun = useCallback(async () => {
    setError(null);
    setResult(null);
    setLoading(true);
    const controller = new AbortController();
    abortRef.current = controller;
    const startedAt = Date.now();
    try {
      const response = await requestExplainKpi(
        projectId,
        {
          scenario_id: scenarioId,
          scope,
          tier_override: tier === "balanced" ? null : tier,
        },
        { signal: controller.signal },
      );
      setResult(response);
      pushHistory({
        timestamp: new Date().toISOString(),
        feature: "explain_kpi",
        model: response.model,
        cost_rub: response.cost_rub,
        latency_ms: Date.now() - startedAt,
        project_id: projectId,
        project_name: projectName,
        cached: response.cached,
      });
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        setError("Отменено");
      } else if (err instanceof ApiError) {
        setError(err.detail ?? err.message);
      } else {
        setError("Неизвестная ошибка");
      }
    } finally {
      setLoading(false);
      abortRef.current = null;
    }
  }, [projectId, projectName, scenarioId, scope, tier, pushHistory]);

  const handleAbort = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const handleReset = useCallback(() => {
    setResult(null);
    setError(null);
  }, []);

  const estimatedCost = AI_FEATURE_COST_ESTIMATES_RUB.explain_kpi;

  return (
    <div className="rounded-lg border bg-card p-4">
      {/* Header с кнопкой запуска */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-primary" />
          <h3 className="text-sm font-semibold">AI-объяснение KPI</h3>
        </div>
        <div className="flex items-center gap-2 text-xs">
          {/* Tier toggle */}
          <div
            role="group"
            aria-label="Tier override"
            className="flex overflow-hidden rounded-md border"
          >
            <button
              type="button"
              onClick={() => setTier("balanced")}
              className={cn(
                "px-2 py-1",
                tier === "balanced"
                  ? "bg-primary text-primary-foreground"
                  : "hover:bg-muted",
              )}
            >
              Standard
            </button>
            <button
              type="button"
              onClick={() => setTier("heavy")}
              className={cn(
                "px-2 py-1",
                tier === "heavy"
                  ? "bg-primary text-primary-foreground"
                  : "hover:bg-muted",
              )}
              title="Глубокий анализ через opus — ~10₽"
            >
              Deep
            </button>
          </div>
          {/* Run / abort button */}
          {loading ? (
            <button
              type="button"
              onClick={handleAbort}
              className="flex items-center gap-1 rounded-md border border-red-300 bg-red-50 px-3 py-1.5 font-medium text-red-700 hover:bg-red-100"
            >
              <X className="h-3 w-3" />
              Отменить
            </button>
          ) : (
            <button
              type="button"
              onClick={handleRun}
              className="rounded-md bg-primary px-3 py-1.5 font-medium text-primary-foreground hover:opacity-90"
            >
              ✨ Объяснить KPI (~
              {tier === "heavy" ? 10 : estimatedCost}₽)
            </button>
          )}
        </div>
      </div>

      {/* Loading state */}
      {loading && (
        <p className="mt-3 text-xs text-muted-foreground">
          Генерируем объяснение... обычно занимает 3-6 секунд.
        </p>
      )}

      {/* Error state */}
      {error !== null && (
        <div className="mt-3 rounded-md border border-destructive bg-destructive/5 p-3 text-xs text-destructive">
          <div className="flex items-center justify-between">
            <span>{error}</span>
            <button
              type="button"
              onClick={handleReset}
              className="text-xs underline"
            >
              Закрыть
            </button>
          </div>
        </div>
      )}

      {/* Result state */}
      {result !== null && (
        <div className="mt-3 space-y-3 text-sm">
          {/* Recommendation badge + confidence */}
          <div className="flex items-center justify-between">
            <RecommendationBadge value={result.recommendation} />
            <span className="text-xs text-muted-foreground">
              уверенность{" "}
              <span className="font-semibold">
                {(result.confidence * 100).toFixed(0)}%
              </span>
            </span>
          </div>

          {/* Summary */}
          <p className="font-medium">{result.summary}</p>

          {/* Key drivers */}
          <div>
            <h4 className="text-xs font-semibold uppercase text-muted-foreground">
              Ключевые драйверы
            </h4>
            <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs">
              {result.key_drivers.map((d, idx) => (
                <li key={idx}>{d}</li>
              ))}
            </ul>
          </div>

          {/* Risks */}
          <div>
            <h4 className="text-xs font-semibold uppercase text-red-600">
              Риски
            </h4>
            <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs">
              {result.risks.map((r, idx) => (
                <li key={idx}>{r}</li>
              ))}
            </ul>
          </div>

          {/* Rationale */}
          <p className="rounded-md bg-muted/50 p-2 text-xs text-muted-foreground">
            <span className="font-semibold">Обоснование: </span>
            {result.rationale}
          </p>

          {/* Meta footer */}
          <div className="flex items-center justify-between border-t pt-2 text-[10px] text-muted-foreground">
            <span>
              {result.model}
              {result.cached ? " · cached" : ""}
            </span>
            <span>{formatCostRub(result.cost_rub)}</span>
            <button
              type="button"
              onClick={handleReset}
              className="underline"
            >
              Закрыть
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function RecommendationBadge({
  value,
}: {
  value: "go" | "no-go" | "review";
}) {
  const styles =
    value === "go"
      ? "bg-green-100 text-green-800 border-green-300"
      : value === "no-go"
        ? "bg-red-100 text-red-800 border-red-300"
        : "bg-yellow-100 text-yellow-800 border-yellow-300";
  const label =
    value === "go" ? "🟢 GO" : value === "no-go" ? "🔴 NO-GO" : "🟡 REVIEW";
  return (
    <span
      className={cn(
        "inline-flex rounded-md border px-2 py-0.5 text-xs font-semibold",
        styles,
      )}
    >
      AI: {label}
    </span>
  );
}
