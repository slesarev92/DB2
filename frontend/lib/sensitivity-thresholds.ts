/**
 * C #20: пороги раскраски для таблицы чувствительности и tornado-bars.
 * Хранятся в localStorage (как C #27 PDF sections), не персистятся в DB.
 */

export interface SensitivityThresholds {
  /** Если delta NPV / |base| ≥ greenPct/100 → ячейка зелёная. */
  greenPct: number;
  /** Если delta NPV / |base| ≤ -redPct/100 → ячейка красная. */
  redPct: number;
}

export const DEFAULT_SENSITIVITY_THRESHOLDS: SensitivityThresholds = {
  greenPct: 5,
  redPct: 5,
};

const LS_KEY = "sensitivity-thresholds-v1";

function isValidPct(x: unknown): x is number {
  return typeof x === "number" && Number.isFinite(x) && x >= 0 && x <= 100;
}

export function loadSensitivityThresholds(): SensitivityThresholds {
  if (typeof window === "undefined")
    return { ...DEFAULT_SENSITIVITY_THRESHOLDS };
  try {
    const raw = window.localStorage.getItem(LS_KEY);
    if (!raw) return { ...DEFAULT_SENSITIVITY_THRESHOLDS };
    const parsed: unknown = JSON.parse(raw);
    if (
      parsed === null ||
      typeof parsed !== "object" ||
      !("greenPct" in parsed) ||
      !("redPct" in parsed)
    ) {
      return { ...DEFAULT_SENSITIVITY_THRESHOLDS };
    }
    const obj = parsed as Record<string, unknown>;
    if (!isValidPct(obj.greenPct) || !isValidPct(obj.redPct)) {
      return { ...DEFAULT_SENSITIVITY_THRESHOLDS };
    }
    return { greenPct: obj.greenPct, redPct: obj.redPct };
  } catch {
    return { ...DEFAULT_SENSITIVITY_THRESHOLDS };
  }
}

export function saveSensitivityThresholds(t: SensitivityThresholds): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(LS_KEY, JSON.stringify(t));
  } catch {
    // localStorage unavailable — ignore
  }
}

/**
 * Tailwind text-color класс для NPV-ячейки относительно base.
 * "" = нейтральный (между порогами или edge case).
 */
export function classifyNpv(
  value: number | null,
  base: number | null,
  thresholds: SensitivityThresholds,
): "" | "text-green-600" | "text-red-600" {
  if (value === null || base === null || base === 0) return "";
  const ratio = (value - base) / Math.abs(base);
  if (ratio >= thresholds.greenPct / 100) return "text-green-600";
  if (ratio <= -thresholds.redPct / 100) return "text-red-600";
  return "";
}

/** Hex-цвет для tornado-bar (серый = нейтральный). */
export function classifyNpvHex(
  value: number | null,
  base: number | null,
  thresholds: SensitivityThresholds,
): string {
  if (value === null || base === null || base === 0) return "#9ca3af";
  const ratio = (value - base) / Math.abs(base);
  if (ratio >= thresholds.greenPct / 100) return "#22c55e";
  if (ratio <= -thresholds.redPct / 100) return "#ef4444";
  return "#9ca3af";
}
