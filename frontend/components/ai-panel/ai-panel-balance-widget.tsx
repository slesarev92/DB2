"use client";

/**
 * Balance widget (Phase 7.5).
 *
 * Polza глобальный баланс — ссылка на dashboard (endpoint не
 * верифицирован, fallback по плану). Project budget — из backend.
 */

import { ExternalLink, RefreshCw } from "lucide-react";
import { useAIPanel } from "./ai-panel-context";
import { AIPanelBudgetProgress } from "./ai-panel-budget-progress";

export function AIPanelBalanceWidget() {
  const { refreshUsage, usageLoading, cacheHitRate24h } = useAIPanel();

  return (
    <div className="space-y-2 rounded-md border p-2">
      {/* Polza global balance — fallback: link to dashboard */}
      <div className="flex items-center justify-between text-xs">
        <div>
          <span className="text-muted-foreground">Polza баланс: </span>
          <a
            href="https://polza.ai/dashboard"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-primary hover:underline"
          >
            Dashboard
            <ExternalLink className="h-3 w-3" />
          </a>
        </div>
        <button
          type="button"
          className="rounded p-0.5 text-muted-foreground hover:text-foreground disabled:opacity-50"
          onClick={refreshUsage}
          disabled={usageLoading}
          title="Обновить статистику"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${usageLoading ? "animate-spin" : ""}`} />
        </button>
      </div>

      {/* Project budget progress */}
      <AIPanelBudgetProgress />

      {/* Cache hit rate */}
      {cacheHitRate24h > 0 && (
        <div className="text-[10px] text-muted-foreground">
          Cache hit rate (24h): {(cacheHitRate24h * 100).toFixed(0)}%
        </div>
      )}
    </div>
  );
}
