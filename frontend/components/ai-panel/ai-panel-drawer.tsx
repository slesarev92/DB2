"use client";

/**
 * AI Panel drawer — правый slide-in (Phase 7.2).
 *
 * Реализация плоским Tailwind translate-x без библиотек (radix/cmdk),
 * чтобы не добавлять зависимостей. Toggle через `useAIPanel().toggle()`
 * или глобальный Ctrl+K из context'а.
 *
 * В 7.2 вкладки: actions (работает), history (mock), chat (заглушка),
 * settings (заглушка), prompt-lab (dev-only). 7.3 добавит chat streaming,
 * 7.5 — real balance/history endpoints.
 */

import { Sparkles, X } from "lucide-react";

import { AIPanelBalanceWidget } from "./ai-panel-balance-widget";
import { AIPanelBudgetProgress } from "./ai-panel-budget-progress";
import { AIPanelChat } from "./ai-panel-chat";
import { useAIPanel } from "./ai-panel-context";
import { AIPanelHistory } from "./ai-panel-history";
import { AIPanelPromptLab } from "./ai-panel-prompt-lab";
import { AIPanelQuickActions } from "./ai-panel-quick-actions";
import { AIPanelSettings } from "./ai-panel-settings";

import { cn } from "@/lib/utils";

const IS_DEV = process.env.NODE_ENV === "development";

export function AIPanelDrawer() {
  const { isOpen, close, activeTab, setActiveTab } = useAIPanel();

  return (
    <>
      {/* Backdrop — клик закрывает drawer */}
      <div
        aria-hidden="true"
        className={cn(
          "fixed inset-0 z-40 bg-black/20 transition-opacity",
          isOpen
            ? "pointer-events-auto opacity-100"
            : "pointer-events-none opacity-0",
        )}
        onClick={close}
      />

      {/* Drawer */}
      <aside
        aria-label="AI Panel"
        aria-hidden={!isOpen}
        className={cn(
          "fixed right-0 top-0 z-50 flex h-full w-96 flex-col border-l bg-background shadow-xl transition-transform",
          isOpen ? "translate-x-0" : "translate-x-full",
        )}
      >
        <header className="flex items-center justify-between border-b px-4 py-3">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary" />
            <h2 className="text-sm font-semibold">AI Assistant</h2>
          </div>
          <button
            type="button"
            onClick={close}
            className="rounded p-1 hover:bg-muted"
            aria-label="Закрыть AI Panel"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        {/* Balance + budget — всегда сверху */}
        <div className="space-y-3 border-b px-4 py-3">
          <AIPanelBalanceWidget />
          <AIPanelBudgetProgress />
        </div>

        {/* Tabs navigation */}
        <nav className="flex border-b text-xs" role="tablist">
          <TabButton
            current={activeTab}
            value="actions"
            label="Действия"
            onClick={setActiveTab}
          />
          <TabButton
            current={activeTab}
            value="history"
            label="История"
            onClick={setActiveTab}
          />
          <TabButton
            current={activeTab}
            value="chat"
            label="Чат"
            onClick={setActiveTab}
          />
          <TabButton
            current={activeTab}
            value="settings"
            label="⚙"
            onClick={setActiveTab}
          />
          {IS_DEV && (
            <TabButton
              current={activeTab}
              value="prompt-lab"
              label="🧪 Lab"
              onClick={setActiveTab}
            />
          )}
        </nav>

        {/* Tab content */}
        <div className="flex-1 overflow-y-auto p-4">
          {activeTab === "actions" && <AIPanelQuickActions />}
          {activeTab === "history" && <AIPanelHistory />}
          {activeTab === "chat" && <AIPanelChat />}
          {activeTab === "settings" && <AIPanelSettings />}
          {activeTab === "prompt-lab" && IS_DEV && <AIPanelPromptLab />}
        </div>

        {/* Footer с Ctrl+K hint */}
        <footer className="border-t px-4 py-2 text-[10px] text-muted-foreground">
          Ctrl+K — открыть/закрыть панель
        </footer>
      </aside>
    </>
  );
}

function TabButton({
  current,
  value,
  label,
  onClick,
}: {
  current: string;
  value: "actions" | "history" | "chat" | "settings" | "prompt-lab";
  label: string;
  onClick: (
    tab: "actions" | "history" | "chat" | "settings" | "prompt-lab",
  ) => void;
}) {
  const isActive = current === value;
  return (
    <button
      type="button"
      role="tab"
      aria-selected={isActive}
      onClick={() => onClick(value)}
      className={cn(
        "flex-1 border-b-2 px-2 py-2 transition-colors",
        isActive
          ? "border-primary font-semibold text-foreground"
          : "border-transparent text-muted-foreground hover:text-foreground",
      )}
    >
      {label}
    </button>
  );
}
