"use client";

/**
 * Budget progress bar (Phase 7.5 — real data from backend).
 *
 * Цветовая шкала:
 * - <60% — green
 * - 60-80% — yellow
 * - >80% — red
 *
 * null budget = unlimited (показываем только spent, без бара).
 */

import { useAIPanel } from "./ai-panel-context";
import { cn } from "@/lib/utils";

export function AIPanelBudgetProgress() {
  const {
    projectMonthSpentRub,
    projectBudgetRub,
    budgetPercentUsed,
    usageLoading,
  } = useAIPanel();

  const spent = projectMonthSpentRub ?? 0;
  const percent = Math.min(100, budgetPercentUsed * 100);

  const colorClass =
    percent < 60
      ? "bg-green-500"
      : percent < 80
        ? "bg-yellow-500"
        : "bg-red-500";

  const budgetLabel =
    projectBudgetRub === null
      ? "∞"
      : projectBudgetRub.toFixed(0);

  return (
    <div className="text-xs">
      <div className="flex items-center justify-between">
        <span className="text-muted-foreground">Бюджет проекта (месяц)</span>
        <span className="font-medium">
          {usageLoading ? (
            <span className="text-muted-foreground">загрузка…</span>
          ) : projectMonthSpentRub === null ? (
            <span className="text-muted-foreground">—</span>
          ) : (
            `${spent.toFixed(0)} / ${budgetLabel} ₽`
          )}
        </span>
      </div>
      {projectBudgetRub !== null && (
        <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-muted">
          <div
            className={cn("h-full transition-all", colorClass)}
            style={{ width: `${percent}%` }}
          />
        </div>
      )}
      {percent >= 80 && projectBudgetRub !== null && (
        <p className="mt-1 text-red-500">
          {percent >= 100
            ? "Бюджет исчерпан — AI-функции заблокированы"
            : `Внимание: ${percent.toFixed(0)}% бюджета использовано`}
        </p>
      )}
    </div>
  );
}
