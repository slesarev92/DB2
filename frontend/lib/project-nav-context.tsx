"use client";

/**
 * ProjectNavContext — registry-based context for project sidebar navigation.
 *
 * Architecture: Provider wraps layout (sidebar + main). Project detail page
 * **registers** its data on mount; sidebar **reads** it. When user navigates
 * away from project, page unregisters and sidebar reverts to global nav.
 *
 * Same pattern as AIPanelContext.setProjectId().
 */

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
} from "react";

/* ── Tab & group constants ── */

export const TAB_ORDER = [
  "overview",
  "content",
  "financial-plan",
  "skus",
  "ingredients",
  "channels",
  "akb",
  "obppc",
  "periods",
  "scenarios",
  "results",
  "sensitivity",
  "pricing",
  "value-chain",
  "pnl",
] as const;

export type TabValue = (typeof TAB_ORDER)[number];

export const SECTION_LABELS: Record<TabValue, string> = {
  overview: "Параметры",
  content: "Содержание",
  "financial-plan": "Фин. план",
  skus: "SKU и BOM",
  ingredients: "Ингредиенты",
  channels: "Каналы",
  akb: "АКБ",
  obppc: "OBPPC",
  periods: "Fine tuning",
  scenarios: "Сценарии",
  results: "Результаты",
  sensitivity: "Чувствительность",
  pricing: "Цены",
  "value-chain": "Unit-экономика",
  pnl: "P&L",
};

export interface SectionGroup {
  key: string;
  label: string;
  number: string; // ①②③④⑤
  tabs: readonly TabValue[];
}

export const SECTION_GROUPS: readonly SectionGroup[] = [
  { key: "basics", label: "Основа", number: "①", tabs: ["overview", "content", "financial-plan"] },
  { key: "product", label: "Продукт", number: "②", tabs: ["skus", "ingredients"] },
  { key: "distribution", label: "Дистрибуция", number: "③", tabs: ["channels", "akb", "obppc"] },
  { key: "modeling", label: "Моделирование", number: "④", tabs: ["periods", "scenarios"] },
  { key: "analysis", label: "Анализ", number: "⑤", tabs: ["results", "sensitivity", "pricing", "value-chain", "pnl"] },
];

/* ── Progress types ── */

export interface GroupProgress {
  group: SectionGroup;
  sections: { key: TabValue; label: string; filled: boolean }[];
  filledCount: number;
  totalCount: number;
}

/* ── Context ── */

export interface ProjectNavData {
  projectId: number;
  projectName: string;
  activeTab: TabValue;
  setActiveTab: (tab: TabValue) => void;
  groups: GroupProgress[];
  progressLoading: boolean;
}

interface ProjectNavContextValue {
  data: ProjectNavData | null;
  register: (data: ProjectNavData) => void;
  unregister: () => void;
}

const ProjectNavContext = createContext<ProjectNavContextValue | null>(null);

export function ProjectNavProvider({ children }: { children: React.ReactNode }) {
  const [data, setData] = useState<ProjectNavData | null>(null);

  const register = useCallback((d: ProjectNavData) => setData(d), []);
  const unregister = useCallback(() => setData(null), []);

  const value = useMemo(
    () => ({ data, register, unregister }),
    [data, register, unregister],
  );

  return (
    <ProjectNavContext.Provider value={value}>
      {children}
    </ProjectNavContext.Provider>
  );
}

/** Returns project nav data or null (when not inside a project page). */
export function useProjectNav(): ProjectNavData | null {
  const ctx = useContext(ProjectNavContext);
  return ctx?.data ?? null;
}

/** Returns the register/unregister functions. Used by project detail page. */
export function useProjectNavRegistry() {
  const ctx = useContext(ProjectNavContext);
  if (!ctx) throw new Error("useProjectNavRegistry must be inside ProjectNavProvider");
  return { register: ctx.register, unregister: ctx.unregister };
}
