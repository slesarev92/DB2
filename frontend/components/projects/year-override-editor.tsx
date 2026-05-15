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
 * Generic-редактор годового override для дискретных Select-параметров.
 *
 * Используется для (как минимум):
 *  - Q1: production_mode_by_year (own | copacking)
 *  - Q5: bom_cost_level_by_year (max | normal | optimal)
 *
 * Пользователь включает чекбокс "Тюнинговать по годам" — заполняем
 * Y1..Y10 текущим скалярным значением и показываем Select-сетку.
 * Снятие чекбокса очищает объект (override выключен).
 */
const YEARS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10] as const;

interface Props {
  /** Заголовок чекбокса (например "Переключать режим по годам"). */
  title: string;
  /** Hint под заголовком (например пример "Y1=копак, Y2=своё..."). */
  hint?: string;
  /** Скалярное значение из родителя — fallback на каждый год, если override пустой. */
  scalarValue: string;
  /** Текущий объект override. Пустой объект = override выключен. */
  value: Record<string, string>;
  /** options: value → label, передаются в Select. */
  options: Record<string, string>;
  onChange: (next: Record<string, string>) => void;
  disabled?: boolean;
}

export function YearOverrideEditor({
  title,
  hint,
  scalarValue,
  value,
  options,
  onChange,
  disabled = false,
}: Props) {
  const isOverriding = Object.keys(value).length > 0;
  const optionKeys = Object.keys(options);
  const fallback = scalarValue || optionKeys[0] || "";

  function toggleOverride(enabled: boolean) {
    if (enabled) {
      const filled: Record<string, string> = {};
      for (const y of YEARS) {
        filled[String(y)] = fallback;
      }
      onChange(filled);
    } else {
      onChange({});
    }
  }

  function updateYear(year: number, next: string) {
    onChange({ ...value, [String(year)]: next });
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
        <span className="font-medium">{title}</span>
        {hint && (
          <span className="text-xs text-muted-foreground">{hint}</span>
        )}
      </label>

      {isOverriding && (
        <div className="mt-3 grid grid-cols-5 gap-2 sm:grid-cols-10">
          {YEARS.map((y) => {
            const current = value[String(y)] ?? fallback;
            return (
              <div key={y} className="space-y-1">
                <Label className="text-xs text-muted-foreground">Y{y}</Label>
                <Select
                  value={current}
                  onValueChange={(v) => {
                    if (v === null) return;
                    updateYear(y, v);
                  }}
                  disabled={disabled}
                  items={options}
                >
                  <SelectTrigger className="h-8">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {optionKeys.map((opt) => (
                      <SelectItem key={opt} value={opt}>
                        {options[opt]}
                      </SelectItem>
                    ))}
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
