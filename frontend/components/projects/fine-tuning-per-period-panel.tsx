"use client";

/**
 * C #14 — Fine Tuning per-period orchestrator.
 *
 * Размещается во вкладке `fine-tuning` карточки проекта. 4 collapsible
 * секции:
 *  1. Copacking rate — per ProjectSKU (1 поле, 43 значения).
 *  2. Logistics ₽/кг — per ProjectSKUChannel.
 *  3. CA&M rate — per ProjectSKUChannel.
 *  4. Marketing rate — per ProjectSKUChannel.
 *
 * Все секции переиспользуют PeriodGrid + PeriodBulkFill из shared.
 */

import { CopackingSection } from "./fine-tuning-copacking-section";
import { ChannelSection } from "./fine-tuning-channel-section";

interface Props {
  projectId: number;
}

export function FineTuningPerPeriodPanel({ projectId }: Props) {
  return (
    <div className="space-y-8">
      <CopackingSection projectId={projectId} />
      <ChannelSection
        projectId={projectId}
        field="logistics_cost_per_kg"
        label="Логистика (₽/кг)"
      />
      <ChannelSection
        projectId={projectId}
        field="ca_m_rate"
        label="CA&M rate (доля Net Revenue)"
      />
      <ChannelSection
        projectId={projectId}
        field="marketing_rate"
        label="Marketing rate (доля Net Revenue)"
      />
    </div>
  );
}
