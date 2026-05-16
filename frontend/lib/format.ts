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

const moneyPerUnitFmt = new Intl.NumberFormat("ru-RU", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
});

/** Денежная сумма per-unit с 2 знаками. "—" если null. */
export function formatMoneyPerUnit(value: string | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const num = Number(value);
  if (Number.isNaN(num)) return "—";
  return `${moneyPerUnitFmt.format(num)} ₽`;
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

// ──────────────────────────────────────────────────────
// C #23: Единицы измерения объёма/массы SKU
// ──────────────────────────────────────────────────────

const volumeFmt = new Intl.NumberFormat("ru-RU", {
  minimumFractionDigits: 0,
  maximumFractionDigits: 4,
});

/**
 * C #23: Объём / масса SKU с единицей.
 * formatVolume("1.5", "л")  → "1,5 л"
 * formatVolume("0.5", "кг") → "0,5 кг"
 * formatVolume(null)         → "—"
 */
export function formatVolume(
  value: string | number | null | undefined,
  unit: "л" | "кг" = "л",
): string {
  if (value === null || value === undefined || value === "") return "—";
  const num = Number(value);
  if (Number.isNaN(num)) return "—";
  return `${volumeFmt.format(num)} ${unit}`;
}

/**
 * C #23: Деньги per-unit с единицей из контекста SKU.
 * formatPerUnit("52.30", "л")  → "52,30 ₽/л"
 * formatPerUnit("120", "кг")   → "120,00 ₽/кг"
 * formatPerUnit(null)           → "—"
 */
export function formatPerUnit(
  value: string | number | null | undefined,
  unit: "л" | "кг" = "л",
): string {
  if (value === null || value === undefined || value === "") return "—";
  const num = Number(value);
  if (Number.isNaN(num)) return "—";
  return `${moneyPerUnitFmt.format(num)} ₽/${unit}`;
}

/**
 * C #23: Штучные значения.
 * formatPieces(1500) → "1 500 шт"
 * formatPieces(null)  → "—"
 */
export function formatPieces(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const num = Number(value);
  if (Number.isNaN(num)) return "—";
  return `${numberFmt.format(num)} шт`;
}

/**
 * Русская плюрализация: 1 → one, 2-4 → few, 5+ → many.
 * Пример: pluralizeRu(1, "канал", "канала", "каналов") → "канал"
 *         pluralizeRu(3, "канал", "канала", "каналов") → "канала"
 *         pluralizeRu(5, "канал", "канала", "каналов") → "каналов"
 */
export function pluralizeRu(
  n: number,
  one: string,
  few: string,
  many: string,
): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return few;
  return many;
}
