/**
 * Стабильные section ID для каждого таба группы «Анализ».
 *
 * Используются как ключи в localStorage (см. lib/use-collapse-state.ts).
 * НЕ переименовывать без бампа `schema_version` в STORAGE_KEY — иначе
 * пользовательские collapse-state потеряются (что не катастрофа, но
 * нежелательно).
 *
 * См. spec §4 — карта секций по табам.
 */

export const RESULTS_SECTIONS = [
  "go-no-go",
  "ai-explain",
  "ai-exec-summary",
  "npv",
  "irr",
  "roi",
  "payback",
  "margins",
  "per-unit",
  "color-legend",
] as const;

export const SENSITIVITY_SECTIONS = [
  "base-values",
  "ai-interpretation",
  "tornado",
  "matrix",
] as const;

export const PRICING_SECTIONS = [
  "shelf-price",
  "ex-factory",
  "costs-margins",
] as const;

export const VALUE_CHAIN_SECTIONS = ["waterfall", "unit-economy"] as const;

export const PNL_SECTIONS = ["pnl"] as const;
