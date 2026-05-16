/**
 * C #14 Fine Tuning per-period — shared helpers для CopackingSection
 * и ChannelSection.
 */

/** Пустой input → null override; иначе trim. */
export function normalizeInput(raw: string | null): string | null {
  if (raw === null) return null;
  const trimmed = raw.trim();
  if (trimmed === "") return null;
  return trimmed;
}

/**
 * Сравнение override-значений по числу, не по string-equality. JSONB
 * round-trip может изменить precision ("99.5" → "99.50000000000001").
 */
export function sameOverride(a: string | null, b: string | null): boolean {
  if (a === null && b === null) return true;
  if (a === null || b === null) return false;
  return Number(a) === Number(b);
}

/** Tailwind classes для override input cells (dirty / override / default). */
export function cellClasses(isOverride: boolean, isDirty: boolean): string {
  const base = "h-7 w-full bg-transparent text-right text-xs px-1";
  if (isDirty) {
    return `${base} ring-2 ring-amber-400 rounded`;
  }
  if (isOverride) {
    return `${base} ring-1 ring-blue-400 rounded`;
  }
  return base;
}
