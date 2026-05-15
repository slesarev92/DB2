"use client";

import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

/**
 * Q1 (2026-05-15): редактор годового override режима производства.
 *
 * Пользователь может задать "Y1 копакинг, Y2 своё, Y3+ копакинг" —
 * по 10 годам проекта. Если override не задан (пустой объект) —
 * pipeline использует скаляр ProjectSKU.production_mode для всех
 * периодов.
 *
 * Чекбокс "Тюнинговать по годам":
 *  - выключен (default) → value = {} → save() очищает override
 *  - включён → заполняем все 10 годов скалярным дефолтом и показываем
 *    Select-сетку для каждого года
 */
const YEARS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10] as const;

const MODE_LABELS = {
  own: "Своё",
  copacking: "Копак.",
} as const;

interface Props {
  scalarMode: string;
  value: Record<string, string>;
  onChange: (next: Record<string, string>) => void;
  disabled?: boolean;
}

export function ProductionModeByYearEditor({
  scalarMode,
  value,
  onChange,
  disabled = false,
}: Props) {
  const isOverriding = Object.keys(value).length > 0;

  function toggleOverride(enabled: boolean) {
    if (enabled) {
      // Заполняем все 10 лет текущим скалярным значением
      const filled: Record<string, string> = {};
      for (const y of YEARS) {
        filled[String(y)] = scalarMode || "own";
      }
      onChange(filled);
    } else {
      onChange({});
    }
  }

  function updateYear(year: number, mode: string) {
    onChange({ ...value, [String(year)]: mode });
  }

  return (
    <div className="mt-3 rounded-md border border-dashed p-3">
      <label className="flex items-center gap-2 text-sm cursor-pointer">
        <input
          type="checkbox"
          checked={isOverriding}
          onChange={(e) => toggleOverride(e.target.checked)}
          disabled={disabled}
        />
        <span className="font-medium">Переключать режим по годам</span>
        <span className="text-xs text-muted-foreground">
          (пример: Y1=копак, Y2=своё, Y3+=копак)
        </span>
      </label>

      {isOverriding && (
        <div className="mt-3 grid grid-cols-5 gap-2 sm:grid-cols-10">
          {YEARS.map((y) => {
            const mode = value[String(y)] ?? scalarMode ?? "own";
            return (
              <div key={y} className="space-y-1">
                <Label className="text-xs text-muted-foreground">Y{y}</Label>
                <Select
                  value={mode}
                  onValueChange={(v) => {
                    if (v === null) return;
                    updateYear(y, v);
                  }}
                  disabled={disabled}
                  items={MODE_LABELS}
                >
                  <SelectTrigger className="h-8">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="own">{MODE_LABELS.own}</SelectItem>
                    <SelectItem value="copacking">
                      {MODE_LABELS.copacking}
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
