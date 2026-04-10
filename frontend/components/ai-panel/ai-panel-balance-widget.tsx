"use client";

/**
 * Balance widget (Phase 7.2 placeholder).
 *
 * Полноценная реализация — в 7.5 после проверки Polza `/api/v1/balance`
 * endpoint'а. Пока показывает статический placeholder с ссылкой на
 * dashboard Polza.
 */

import { ExternalLink } from "lucide-react";

export function AIPanelBalanceWidget() {
  return (
    <div className="flex items-center justify-between rounded-md bg-muted/50 p-2 text-xs">
      <div>
        <div className="text-muted-foreground">Polza баланс</div>
        <div className="text-sm font-medium">—</div>
      </div>
      <a
        href="https://polza.ai/dashboard"
        target="_blank"
        rel="noopener noreferrer"
        className="flex items-center gap-1 text-primary hover:underline"
      >
        Dashboard
        <ExternalLink className="h-3 w-3" />
      </a>
    </div>
  );
}
