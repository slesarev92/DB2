/**
 * Форматтеры для отображения чисел / дат.
 *
 * Backend возвращает Decimal как строку (Pydantic v2 + Numeric колонки),
 * поэтому везде ожидаем `string | null`.
 */

const numberFmt = new Intl.NumberFormat("ru-RU", {
  maximumFractionDigits: 0,
});

const dateFmt = new Intl.DateTimeFormat("ru-RU", {
  year: "numeric",
  month: "short",
  day: "numeric",
});

/** Денежная сумма в рублях с разделителями. "—" если null. */
export function formatMoney(value: string | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const num = Number(value);
  if (Number.isNaN(num)) return "—";
  return `${numberFmt.format(num)} ₽`;
}

/** Процент с одним знаком после запятой. "—" если null. */
export function formatPercent(value: string | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const num = Number(value);
  if (Number.isNaN(num)) return "—";
  return `${(num * 100).toFixed(1)}%`;
}

/** Дата ISO YYYY-MM-DD → "8 апр. 2025". */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return dateFmt.format(d);
}
