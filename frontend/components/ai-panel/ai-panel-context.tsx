"use client";

/**
 * AIPanelProvider — React Context для правого AI Panel drawer'а.
 *
 * Phase 7.2: initial scaffolding с localStorage persistence.
 * Phase 7.5: real data из GET /api/projects/{id}/ai/usage.
 *
 * **Persistent state** — `isOpen` и `activeTab` сохраняются в localStorage.
 * **Budget + history** — fetched from backend при mount + refresh after calls.
 * **Ctrl+K** — toggle drawer shortcut.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { fetchAIUsage } from "@/lib/ai";
import type { AIUsageRecentCall, AIUsageHistoryEntry } from "@/types/api";

/** Вкладки AI Panel drawer'а. */
export type AIPanelTab =
  | "actions"
  | "history"
  | "chat"
  | "settings"
  | "prompt-lab";

interface AIPanelState {
  isOpen: boolean;
  activeTab: AIPanelTab;
  /** История вызовов AI (runtime + restored from backend). */
  history: AIUsageHistoryEntry[];
  /** Project budget usage за текущий месяц, ₽. Null = loading. */
  projectMonthSpentRub: number | null;
  /** Project monthly budget cap, ₽. Null = unlimited. */
  projectBudgetRub: number | null;
  /** Budget remaining ₽. */
  projectBudgetRemainingRub: number | null;
  /** 0..1 usage ratio. */
  budgetPercentUsed: number;
  /** Recent calls from backend. */
  recentCalls: AIUsageRecentCall[];
  /** Cache hit rate 24h. */
  cacheHitRate24h: number;
  /** Usage loading state. */
  usageLoading: boolean;
}

interface AIPanelContextValue extends AIPanelState {
  open: () => void;
  close: () => void;
  toggle: () => void;
  setActiveTab: (tab: AIPanelTab) => void;
  pushHistory: (entry: AIUsageHistoryEntry) => void;
  clearHistory: () => void;
  /** Project ID для которого загружены данные. */
  projectId: number | null;
  setProjectId: (id: number | null) => void;
  /** Перезагрузить usage stats (вызывается после AI calls). */
  refreshUsage: () => void;
}

const AIPanelContext = createContext<AIPanelContextValue | null>(null);

const STORAGE_KEY_OPEN = "db2.ai_panel.open";
const STORAGE_KEY_TAB = "db2.ai_panel.activeTab";

function readPersistedBool(key: string, defaultValue: boolean): boolean {
  if (typeof window === "undefined") return defaultValue;
  try {
    const raw = window.localStorage.getItem(key);
    if (raw === null) return defaultValue;
    return raw === "1";
  } catch {
    return defaultValue;
  }
}

function readPersistedString<T extends string>(
  key: string,
  allowed: readonly T[],
  defaultValue: T,
): T {
  if (typeof window === "undefined") return defaultValue;
  try {
    const raw = window.localStorage.getItem(key);
    if (raw === null) return defaultValue;
    if ((allowed as readonly string[]).includes(raw)) return raw as T;
    return defaultValue;
  } catch {
    return defaultValue;
  }
}

const ALL_TABS: readonly AIPanelTab[] = [
  "actions",
  "history",
  "chat",
  "settings",
  "prompt-lab",
];

export function AIPanelProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const [activeTab, setActiveTabState] = useState<AIPanelTab>("actions");
  const [history, setHistory] = useState<AIUsageHistoryEntry[]>([]);

  // Phase 7.5: real budget data from backend
  const [projectId, setProjectId] = useState<number | null>(null);
  const [projectMonthSpentRub, setProjectMonthSpentRub] = useState<number | null>(null);
  const [projectBudgetRub, setProjectBudgetRub] = useState<number | null>(500);
  const [projectBudgetRemainingRub, setProjectBudgetRemainingRub] = useState<number | null>(500);
  const [budgetPercentUsed, setBudgetPercentUsed] = useState(0);
  const [recentCalls, setRecentCalls] = useState<AIUsageRecentCall[]>([]);
  const [cacheHitRate24h, setCacheHitRate24h] = useState(0);
  const [usageLoading, setUsageLoading] = useState(false);

  // Fetch usage data from backend
  const refreshUsage = useCallback(() => {
    if (!projectId) return;
    setUsageLoading(true);
    fetchAIUsage(projectId)
      .then((data) => {
        setProjectMonthSpentRub(parseFloat(data.spent_rub));
        setProjectBudgetRub(
          data.budget_rub !== null ? parseFloat(data.budget_rub) : null,
        );
        setProjectBudgetRemainingRub(
          data.budget_remaining_rub !== null
            ? parseFloat(data.budget_remaining_rub)
            : null,
        );
        setBudgetPercentUsed(data.budget_percent_used);
        setRecentCalls(data.recent_calls);
        setCacheHitRate24h(data.cache_hit_rate_24h);
      })
      .catch(() => {
        // Silently fail — usage stats non-critical
      })
      .finally(() => setUsageLoading(false));
  }, [projectId]);

  // Auto-fetch when projectId changes
  useEffect(() => {
    if (projectId) refreshUsage();
  }, [projectId, refreshUsage]);

  // Восстановление persistent state из localStorage при монтировании.
  useEffect(() => {
    setIsOpen(readPersistedBool(STORAGE_KEY_OPEN, false));
    setActiveTabState(
      readPersistedString(STORAGE_KEY_TAB, ALL_TABS, "actions"),
    );
  }, []);

  // Ctrl+K toggle + Escape close global shortcuts
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setIsOpen((prev) => {
          const next = !prev;
          try {
            window.localStorage.setItem(STORAGE_KEY_OPEN, next ? "1" : "0");
          } catch {
            /* noop */
          }
          return next;
        });
        return;
      }
      if (e.key === "Escape") {
        setIsOpen((prev) => {
          if (!prev) return prev; // already closed — don't interfere
          try {
            window.localStorage.setItem(STORAGE_KEY_OPEN, "0");
          } catch {
            /* noop */
          }
          return false;
        });
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const open = useCallback(() => {
    setIsOpen(true);
    try {
      window.localStorage.setItem(STORAGE_KEY_OPEN, "1");
    } catch {
      /* noop */
    }
  }, []);

  const close = useCallback(() => {
    setIsOpen(false);
    try {
      window.localStorage.setItem(STORAGE_KEY_OPEN, "0");
    } catch {
      /* noop */
    }
  }, []);

  const toggle = useCallback(() => {
    setIsOpen((prev) => {
      const next = !prev;
      try {
        window.localStorage.setItem(STORAGE_KEY_OPEN, next ? "1" : "0");
      } catch {
        /* noop */
      }
      return next;
    });
  }, []);

  const setActiveTab = useCallback((tab: AIPanelTab) => {
    setActiveTabState(tab);
    try {
      window.localStorage.setItem(STORAGE_KEY_TAB, tab);
    } catch {
      /* noop */
    }
  }, []);

  const pushHistory = useCallback((entry: AIUsageHistoryEntry) => {
    setHistory((prev) => [entry, ...prev].slice(0, 10));
  }, []);

  const clearHistory = useCallback(() => setHistory([]), []);

  const value = useMemo<AIPanelContextValue>(
    () => ({
      isOpen,
      activeTab,
      history,
      projectMonthSpentRub,
      projectBudgetRub,
      projectBudgetRemainingRub,
      budgetPercentUsed,
      recentCalls,
      cacheHitRate24h,
      usageLoading,
      projectId,
      setProjectId,
      open,
      close,
      toggle,
      setActiveTab,
      pushHistory,
      clearHistory,
      refreshUsage,
    }),
    [
      isOpen,
      activeTab,
      history,
      projectMonthSpentRub,
      projectBudgetRub,
      projectBudgetRemainingRub,
      budgetPercentUsed,
      recentCalls,
      cacheHitRate24h,
      usageLoading,
      projectId,
      open,
      close,
      toggle,
      setActiveTab,
      pushHistory,
      clearHistory,
      refreshUsage,
    ],
  );

  return (
    <AIPanelContext.Provider value={value}>{children}</AIPanelContext.Provider>
  );
}

export function useAIPanel(): AIPanelContextValue {
  const ctx = useContext(AIPanelContext);
  if (ctx === null) {
    throw new Error("useAIPanel must be used inside <AIPanelProvider>");
  }
  return ctx;
}
