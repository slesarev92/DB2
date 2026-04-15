"use client";

import { AlertTriangle } from "lucide-react";

import { Button } from "@/components/ui/button";

interface StalenessBadgeProps {
  /**
   * Любой объект с `is_stale` полем (ScenarioResult или любой другой
   * объект у которого есть stale-флаг). Если null/undefined/False — badge
   * не рендерится.
   */
  isStale: boolean | null | undefined;
  /** CTA-кнопка "Пересчитать". Если не передана — только текст без кнопки. */
  onRecalculate?: () => void;
  /** Идёт recalculate — disable кнопку + показать "Пересчитываю…". */
  recalculating?: boolean;
  /**
   * Кастомное сообщение. По умолчанию — "Параметры проекта изменились
   * после последнего расчёта. Данные могут быть неактуальны."
   */
  message?: string;
  /** Дополнительные классы на root. */
  className?: string;
}

/**
 * F-01/F-02: badge "Расчёт устарел" с CTA "Пересчитать".
 *
 * Показывается в results-tab, scenarios-tab, pnl-tab, value-chain-tab.
 * Backend помечает `ScenarioResult.is_stale=True` во всех PATCH/POST/
 * DELETE endpoint'ах, меняющих pipeline input (см. invalidation_service).
 *
 * После успешного recalculate — новые ScenarioResult создаются со
 * server_default=false, флаг автоматически сбрасывается.
 */
export function StalenessBadge({
  isStale,
  onRecalculate,
  recalculating = false,
  message,
  className,
}: StalenessBadgeProps) {
  if (!isStale) return null;

  return (
    <div
      role="alert"
      className={`flex items-center justify-between gap-3 rounded-md border border-yellow-500/40 bg-yellow-50 px-4 py-3 text-sm text-yellow-900 dark:bg-yellow-950/40 dark:text-yellow-100 ${className ?? ""}`}
    >
      <div className="flex items-start gap-2">
        <AlertTriangle
          className="mt-0.5 h-4 w-4 shrink-0 text-yellow-600"
          strokeWidth={2.5}
        />
        <div>
          <div className="font-medium">Расчёт устарел</div>
          <div className="text-xs text-yellow-800 dark:text-yellow-200">
            {message ??
              "Параметры проекта изменились после последнего расчёта. Данные могут быть неактуальны."}
          </div>
        </div>
      </div>
      {onRecalculate !== undefined && (
        <Button
          size="sm"
          onClick={onRecalculate}
          disabled={recalculating}
          className="shrink-0"
        >
          {recalculating ? "Пересчитываю…" : "Пересчитать"}
        </Button>
      )}
    </div>
  );
}
