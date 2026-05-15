/**
 * Pure helpers для редактора финплана (B.9b).
 *
 * Распределение, диапазоны и определение legacy-данных. Никакого state.
 */

import type { FinancialPlanItem } from "@/types/api";

/**
 * period_number → отображаемая метка.
 *   1..36 → "M1".."M36"
 *   37..43 → "Y4".."Y10"
 */
export function periodLabel(periodNumber: number): string {
  if (periodNumber >= 1 && periodNumber <= 36) return `M${periodNumber}`;
  if (periodNumber >= 37 && periodNumber <= 43)
    return `Y${periodNumber - 33}`; // 37→Y4, 43→Y10
  return `?${periodNumber}`;
}

/** period_number → model_year (1..10). */
export function modelYearOf(periodNumber: number): number {
  if (periodNumber >= 1 && periodNumber <= 12) return 1;
  if (periodNumber >= 13 && periodNumber <= 24) return 2;
  if (periodNumber >= 25 && periodNumber <= 36) return 3;
  return periodNumber - 33; // 37→4, 43→10
}

/** Все period_number принадлежащие конкретному model_year. */
export function periodsInYear(modelYear: number): number[] {
  if (modelYear === 1) return Array.from({ length: 12 }, (_, i) => i + 1);
  if (modelYear === 2) return Array.from({ length: 12 }, (_, i) => i + 13);
  if (modelYear === 3) return Array.from({ length: 12 }, (_, i) => i + 25);
  return [modelYear + 33]; // Y4..Y10
}

/**
 * Распределить сумму total на 12 месяцев заданного года.
 * Округление до 2 знаков; невязка идёт в последний месяц.
 * Возвращает [period_number, amount][].
 *
 * Применимо только для year ∈ {1,2,3} — для Y4..Y10 раскидывать нечего.
 */
export function distributeYear(
  modelYear: number,
  total: number,
): Array<[number, string]> {
  if (modelYear < 1 || modelYear > 3) {
    throw new Error(`distributeYear: modelYear must be 1..3, got ${modelYear}`);
  }
  const periods = periodsInYear(modelYear); // 12 элементов
  const per = Math.round((total / 12) * 100) / 100;
  const result: Array<[number, string]> = [];
  let allocated = 0;
  for (let i = 0; i < 11; i++) {
    result.push([periods[i], String(per)]);
    allocated += per;
  }
  const last = Math.round((total - allocated) * 100) / 100;
  result.push([periods[11], String(last)]);
  return result;
}

/**
 * Заполнить диапазон period_number [from..to] значением value.
 * Возвращает [period_number, value][].
 */
export function fillRange(
  from: number,
  to: number,
  value: string,
): Array<[number, string]> {
  if (from < 1 || to > 43 || from > to) {
    throw new Error(`fillRange: invalid range ${from}..${to}`);
  }
  const result: Array<[number, string]> = [];
  for (let pn = from; pn <= to; pn++) {
    result.push([pn, value]);
  }
  return result;
}

/**
 * Признак "legacy-данных": все ненулевые значения сосредоточены в
 * first-period-of-year (1, 13, 25, 37..43). Используется чтобы показать
 * пользователю banner с подсказкой про "Распределить год".
 */
export function isLegacyData(items: FinancialPlanItem[]): boolean {
  const firstOfYear = new Set([1, 13, 25, 37, 38, 39, 40, 41, 42, 43]);
  let hasAnyNonZero = false;
  for (const item of items) {
    const total = Number(item.capex || 0) + Number(item.opex || 0);
    const itemsTotal =
      item.capex_items.reduce((s, x) => s + Number(x.amount || 0), 0) +
      item.opex_items.reduce((s, x) => s + Number(x.amount || 0), 0);
    if (total > 0 || itemsTotal > 0) {
      hasAnyNonZero = true;
      if (!firstOfYear.has(item.period_number)) return false;
    }
  }
  return hasAnyNonZero;
}
