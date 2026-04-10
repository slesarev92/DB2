"use client";

/**
 * Inline ✨ для SensitivityTab — интерпретация матрицы (Phase 7.3).
 */

import { Sparkles, X } from "lucide-react";
import { useCallback, useRef, useState } from "react";

import { useAIPanel } from "./ai-panel-context";

import { ApiError } from "@/lib/api";
import {
  AI_FEATURE_COST_ESTIMATES_RUB,
  formatCostRub,
  requestExplainSensitivity,
} from "@/lib/ai";
import { cn } from "@/lib/utils";

import type { AISensitivityExplanationResponse } from "@/types/api";

interface Props {
  projectId: number;
  projectName: string;
  scenarioId: number;
}

export function ExplainSensitivityInline({
  projectId,
  projectName,
  scenarioId,
}: Props) {
  const { pushHistory } = useAIPanel();
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AISensitivityExplanationResponse | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const handleRun = useCallback(async () => {
    setError(null);
    setResult(null);
    setLoading(true);
    const controller = new AbortController();
    abortRef.current = controller;
    const startedAt = Date.now();
    try {
      const response = await requestExplainSensitivity(
        projectId,
        { scenario_id: scenarioId },
        { signal: controller.signal },
      );
      setResult(response);
      pushHistory({
        timestamp: new Date().toISOString(),
        feature: "explain_sensitivity",
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
  }, [projectId, projectName, scenarioId, pushHistory]);

  const cost = AI_FEATURE_COST_ESTIMATES_RUB.explain_sensitivity;

  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-primary" />
          <h3 className="text-sm font-semibold">AI-интерпретация чувствительности</h3>
        </div>
        {loading ? (
          <button
            type="button"
            onClick={() => abortRef.current?.abort()}
            className="flex items-center gap-1 rounded-md border border-red-300 bg-red-50 px-3 py-1.5 text-xs font-medium text-red-700"
          >
            <X className="h-3 w-3" /> Отменить
          </button>
        ) : (
          <button
            type="button"
            onClick={handleRun}
            className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground"
          >
            ✨ Интерпретировать (~{cost}₽)
          </button>
        )}
      </div>

      {loading && (
        <p className="mt-3 text-xs text-muted-foreground">
          Анализируем матрицу чувствительности...
        </p>
      )}

      {error !== null && (
        <div className="mt-3 rounded-md border border-destructive bg-destructive/5 p-3 text-xs text-destructive">
          {error}
          <button
            type="button"
            onClick={() => { setError(null); setResult(null); }}
            className="ml-2 underline"
          >
            Закрыть
          </button>
        </div>
      )}

      {result !== null && (
        <div className="mt-3 space-y-3 text-sm">
          <div className="flex items-center gap-4 rounded-md bg-muted/50 p-2 text-xs">
            <span>
              <span className="font-semibold text-green-700">Самый чувствительный:</span>{" "}
              {result.most_sensitive_param} — {result.most_sensitive_impact}
            </span>
            <span>
              <span className="font-semibold text-blue-700">Наименее:</span>{" "}
              {result.least_sensitive_param}
            </span>
          </div>

          <p>{result.narrative}</p>

          {result.actionable_levers.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold uppercase text-muted-foreground">
                Рычаги управления
              </h4>
              <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs">
                {result.actionable_levers.map((l, i) => (
                  <li key={i}>{l}</li>
                ))}
              </ul>
            </div>
          )}

          {result.warning_flags.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold uppercase text-red-600">
                Warning flags
              </h4>
              <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs text-red-700">
                {result.warning_flags.map((f, i) => (
                  <li key={i}>{f}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="flex items-center justify-between border-t pt-2 text-[10px] text-muted-foreground">
            <span>
              {result.model}{result.cached ? " · cached" : ""}
            </span>
            <span>{formatCostRub(result.cost_rub)}</span>
            <button
              type="button"
              onClick={() => { setResult(null); setError(null); }}
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
