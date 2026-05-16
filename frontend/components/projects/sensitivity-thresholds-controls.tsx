"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  DEFAULT_SENSITIVITY_THRESHOLDS,
  type SensitivityThresholds,
} from "@/lib/sensitivity-thresholds";

interface Props {
  value: SensitivityThresholds;
  onChange: (next: SensitivityThresholds) => void;
}

function clampPct(raw: string): number {
  const n = Number(raw);
  if (!Number.isFinite(n)) return 0;
  if (n < 0) return 0;
  if (n > 100) return 100;
  return n;
}

/**
 * Контролы порогов раскраски чувствительности (C #20).
 * Изменения сохраняются в localStorage через onChange родителя.
 */
export function SensitivityThresholdsControls({ value, onChange }: Props) {
  return (
    <div className="flex items-end gap-3 text-xs">
      <div className="space-y-1">
        <Label
          htmlFor="sens-green-pct"
          className="text-xs text-muted-foreground"
        >
          Зелёный ≥ %
        </Label>
        <Input
          id="sens-green-pct"
          type="number"
          min={0}
          max={100}
          step={1}
          value={value.greenPct}
          onChange={(e) =>
            onChange({ ...value, greenPct: clampPct(e.target.value) })
          }
          className="h-8 w-20"
        />
      </div>
      <div className="space-y-1">
        <Label
          htmlFor="sens-red-pct"
          className="text-xs text-muted-foreground"
        >
          Красный ≤ −%
        </Label>
        <Input
          id="sens-red-pct"
          type="number"
          min={0}
          max={100}
          step={1}
          value={value.redPct}
          onChange={(e) =>
            onChange({ ...value, redPct: clampPct(e.target.value) })
          }
          className="h-8 w-20"
        />
      </div>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="h-8 text-xs"
        onClick={() => onChange({ ...DEFAULT_SENSITIVITY_THRESHOLDS })}
        title="Сбросить пороги к значениям по умолчанию (5% / 5%)"
      >
        Сбросить
      </Button>
    </div>
  );
}
