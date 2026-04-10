"use client";

/**
 * Quick actions таб — кнопки быстрого вызова AI-фич (Phase 7.2).
 *
 * В 7.2 активна только "Explain KPI" — и то только при условии что
 * пользователь находится в контексте проекта с выбранными scenario+scope.
 * Остальные кнопки — disabled placeholder'ы до 7.3..7.8.
 *
 * Замечание: этот таб — дублёр inline ✨ кнопок на ResultsTab /
 * SensitivityTab. Оба UX паттерна приняты (Phase 7 решение #3):
 * inline для естественного контекста, panel для "отдельный воркфлоу".
 */

import { AI_FEATURE_COST_ESTIMATES_RUB } from "@/lib/ai";

export function AIPanelQuickActions() {
  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">
        Быстрый доступ к AI-функциям. Для контекстных вызовов используйте
        кнопки ✨ на вкладках проекта.
      </p>
      <ul className="space-y-2">
        <QuickActionItem
          label="Explain KPI"
          description="Объяснение NPV / IRR / Payback фокусного сценария"
          cost={AI_FEATURE_COST_ESTIMATES_RUB.explain_kpi}
          disabled
          disabledReason="Откройте проект → Результаты → ✨"
        />
        <QuickActionItem
          label="Executive Summary"
          description="Готовый текст для слайда паспорта"
          cost={AI_FEATURE_COST_ESTIMATES_RUB.executive_summary}
          disabled
          disabledReason="Доступно в Phase 7.4"
        />
        <QuickActionItem
          label="Audit params"
          description="Проверка параметров проекта"
          cost={AI_FEATURE_COST_ESTIMATES_RUB.explain_kpi}
          disabled
          disabledReason="Доступно в Phase 7.5"
        />
      </ul>
    </div>
  );
}

function QuickActionItem({
  label,
  description,
  cost,
  disabled = false,
  disabledReason,
}: {
  label: string;
  description: string;
  cost: number;
  disabled?: boolean;
  disabledReason?: string;
}) {
  return (
    <li className="rounded-md border p-3 text-xs">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">{label}</span>
        <span className="text-muted-foreground">~{cost}₽</span>
      </div>
      <p className="mt-1 text-muted-foreground">{description}</p>
      {disabled && (
        <p className="mt-1 text-[10px] text-muted-foreground/80">
          {disabledReason}
        </p>
      )}
    </li>
  );
}
