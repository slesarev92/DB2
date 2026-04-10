"use client";

/**
 * Budget progress bar (Phase 7.2 mock + 7.5 real data).
 *
 * Цветовая шкала по Phase 7 решению #6 + #8:
 * - <60% — green
 * - 60-80% — yellow
 * - >80% — red (confirmation dialog при клике на AI-кнопку)
 *
 * В 7.2: читает `projectMonthSpentRub` из context'а (null = loading / mock).
 * В 7.5: real endpoint + live update после каждого AI вызова.
 */

import { useAIPanel } from "./ai-panel-context";
import { cn } from "@/lib/utils";

export function AIPanelBudgetProgress() {
  const { projectMonthSpentRub, projectBudgetRub } = useAIPanel();

  const spent = projectMonthSpentRub ?? 0;
  const percent =
    projectBudgetRub > 0 ? Math.min(100, (spent / projectBudgetRub) * 100) : 0;

  const colorClass =
    percent < 60
      ? "bg-green-500"
      : percent < 80
        ? "bg-yellow-500"
        : "bg-red-500";

  return (
    <div className="text-xs">
      <div className="flex items-center justify-between">
        <span className="text-muted-foreground">Бюджет проекта (месяц)</span>
        <span className="font-medium">
          {projectMonthSpentRub === null ? (
            <span className="text-muted-foreground">—</span>
          ) : (
            `${spent.toFixed(0)} / ${projectBudgetRub} ₽`
          )}
        </span>
      </div>
      <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          className={cn("h-full transition-all", colorClass)}
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}
