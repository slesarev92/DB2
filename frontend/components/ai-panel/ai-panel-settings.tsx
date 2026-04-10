"use client";

/**
 * Settings tab — per-feature tier override (Phase 7.2 placeholder).
 *
 * В 7.2: показывает структуру — какие фичи на каких tier'ах сейчас.
 * В 7.5: добавим реальный save в localStorage + передачу tier_override
 * в каждый AI вызов.
 */

const FEATURES = [
  { id: "explain_kpi", label: "Explain KPI", default_tier: "balanced" },
  { id: "explain_sensitivity", label: "Explain Sensitivity", default_tier: "balanced" },
  { id: "executive_summary", label: "Executive Summary", default_tier: "heavy" },
  { id: "content_field", label: "Content Fields", default_tier: "fast_cheap" },
  { id: "freeform_chat", label: "Freeform Chat", default_tier: "balanced" },
];

const TIER_LABELS: Record<string, string> = {
  fast_cheap: "Fast / Cheap",
  balanced: "Balanced (default)",
  heavy: "Heavy / Deep",
  research: "Research + Web",
  image: "Image gen",
};

export function AIPanelSettings() {
  return (
    <div className="space-y-3 text-xs">
      <p className="text-muted-foreground">
        Текущие tier'ы для каждой фичи. Override per-feature будет в 7.5.
      </p>
      <ul className="space-y-1">
        {FEATURES.map((f) => (
          <li
            key={f.id}
            className="flex items-center justify-between rounded-md border px-2 py-1.5"
          >
            <span className="font-medium">{f.label}</span>
            <span className="text-muted-foreground">
              {TIER_LABELS[f.default_tier]}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
