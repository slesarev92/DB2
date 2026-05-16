/**
 * C #27: PDF section catalog mirror. Source of truth enum —
 * backend `app/export/pdf_sections.py`.
 */

export type PdfSectionId =
  | "title"
  | "general"
  | "concept"
  | "tech"
  | "validation"
  | "product_mix"
  | "macro"
  | "kpi"
  | "pnl"
  | "sensitivity"
  | "pricing"
  | "unit_econ"
  | "cost_stack"
  | "risks"
  | "roadmap"
  | "market"
  | "executive_summary";

export const PDF_SECTION_ORDER: PdfSectionId[] = [
  "title",
  "general",
  "concept",
  "tech",
  "validation",
  "product_mix",
  "macro",
  "kpi",
  "pnl",
  "sensitivity",
  "pricing",
  "unit_econ",
  "cost_stack",
  "risks",
  "roadmap",
  "market",
  "executive_summary",
];

export const PDF_SECTION_LABELS: Record<PdfSectionId, string> = {
  title: "Титульный лист",
  general: "1. Общая информация",
  concept: "2. Концепция продукта",
  tech: "3. Технология и обоснование",
  validation: "4. Результаты валидации",
  product_mix: "5. Продуктовый микс",
  macro: "6. Макро-факторы",
  kpi: "7. Ключевые KPI",
  pnl: "8. PnL по годам",
  sensitivity: "Анализ чувствительности",
  pricing: "Цены: полка/ex-factory/COGS",
  unit_econ: "Стакан: per-unit экономика",
  cost_stack: "9. Стакан себестоимости + фин-план",
  risks: "10. Риски и готовность функций",
  roadmap: "11. Дорожная карта",
  market: "Рынок и поставки",
  executive_summary: "12. Executive Summary",
};

const LS_KEY = "pdf-export-sections-v1";

export function loadSavedSections(): PdfSectionId[] {
  if (typeof window === "undefined") return [...PDF_SECTION_ORDER];
  try {
    const raw = window.localStorage.getItem(LS_KEY);
    if (!raw) return [...PDF_SECTION_ORDER];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [...PDF_SECTION_ORDER];
    const valid = (parsed as unknown[]).filter(
      (x): x is PdfSectionId =>
        typeof x === "string" &&
        (PDF_SECTION_ORDER as string[]).includes(x),
    );
    return valid.length > 0 ? valid : [...PDF_SECTION_ORDER];
  } catch {
    return [...PDF_SECTION_ORDER];
  }
}

export function saveSections(sections: PdfSectionId[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(LS_KEY, JSON.stringify(sections));
  } catch {
    // localStorage unavailable — ignore
  }
}
