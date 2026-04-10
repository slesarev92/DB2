"use client";

/**
 * AIPanelProvider — React Context для правого AI Panel drawer'а (Phase 7.2).
 *
 * По образцу `auth-provider.tsx` — держим state в useState, exposit'им через
 * `useAIPanel()` хук. Почему Context, а не Zustand: консистентно с auth,
 * ноль новых зависимостей, достаточно для нашего объёма state.
 *
 * **Persistent state** — `isOpen` и `activeTab` сохраняются в localStorage
 * чтобы переключение табов внутри проекта не теряло drawer state.
 * History и balance — runtime-only (restore при монтировании через API
 * в 7.5, пока mock).
 *
 * **Ctrl+K** — keyboard listener на window в отдельном useEffect. Без
 * cmdk, плоский handler. Работает в любом защищённом layout'е, потому
 * что Provider монтируется один раз в `(app)/layout.tsx`.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import type { AIUsageHistoryEntry } from "@/types/api";

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
  /** История вызовов AI (runtime; real restore в 7.5). */
  history: AIUsageHistoryEntry[];
  /**
   * Project budget usage за текущий месяц, ₽. Null = ещё не загружен
   * (7.5 добавит real endpoint `/api/projects/{id}/ai/usage`).
   */
  projectMonthSpentRub: number | null;
  /**
   * Project monthly budget cap, ₽. Дефолт 500 по Phase 7 решению #6.
   * В 7.5 читается из `Project.ai_budget_rub_monthly`.
   */
  projectBudgetRub: number;
}

interface AIPanelContextValue extends AIPanelState {
  open: () => void;
  close: () => void;
  toggle: () => void;
  setActiveTab: (tab: AIPanelTab) => void;
  pushHistory: (entry: AIUsageHistoryEntry) => void;
  clearHistory: () => void;
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
  const [projectMonthSpentRub] = useState<number | null>(null);

  // Project budget — mock в 7.2, real в 7.5 (Project.ai_budget_rub_monthly).
  const projectBudgetRub = 500;

  // Восстановление persistent state из localStorage при монтировании.
  // Делается в useEffect (не в useState initializer) чтобы не ломать
  // SSR hydration — сервер не знает localStorage.
  useEffect(() => {
    setIsOpen(readPersistedBool(STORAGE_KEY_OPEN, false));
    setActiveTabState(
      readPersistedString(STORAGE_KEY_TAB, ALL_TABS, "actions"),
    );
  }, []);

  // Ctrl+K global shortcut — toggle drawer + фокус на chat input (7.3).
  // В 7.2 просто toggle'им, фокус добавим когда chat tab будет живым.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      // Ctrl+K на Windows/Linux, Cmd+K на Mac
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
      open,
      close,
      toggle,
      setActiveTab,
      pushHistory,
      clearHistory,
    }),
    [
      isOpen,
      activeTab,
      history,
      projectMonthSpentRub,
      projectBudgetRub,
      open,
      close,
      toggle,
      setActiveTab,
      pushHistory,
      clearHistory,
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
