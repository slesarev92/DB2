"use client";

import { ChevronLeft, ChevronRight, FolderKanban, LogOut, Sparkles } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";

import { useAIPanel } from "@/components/ai-panel/ai-panel-context";
import { useAuth } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
  icon: typeof FolderKanban;
}

const NAV: NavItem[] = [
  { href: "/projects", label: "Проекты", icon: FolderKanban },
];

const STORAGE_KEY = "sidebar-collapsed";

export function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const { toggle: toggleAIPanel } = useAIPanel();
  const [collapsed, setCollapsed] = useState(false);

  // Restore from localStorage on mount
  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "true") setCollapsed(true);
  }, []);

  function toggleCollapsed() {
    setCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem(STORAGE_KEY, String(next));
      return next;
    });
  }

  // Ctrl+B keyboard shortcut
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key === "b") {
        e.preventDefault();
        toggleCollapsed();
      }
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, []);

  return (
    <aside
      className={cn(
        "flex h-screen flex-col border-r bg-sidebar text-sidebar-foreground transition-all duration-200",
        collapsed ? "w-16" : "w-60",
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b px-3 py-4">
        {!collapsed && (
          <div className="min-w-0">
            <h1 className="truncate text-base font-semibold leading-tight">
              Цифровой паспорт
            </h1>
            <p className="text-xs text-muted-foreground">проекта</p>
          </div>
        )}
        <Button
          variant="ghost"
          size="sm"
          onClick={toggleCollapsed}
          className="shrink-0 h-7 w-7 p-0"
          title="Свернуть/развернуть (Ctrl+B)"
        >
          {collapsed ? (
            <ChevronRight className="h-4 w-4" />
          ) : (
            <ChevronLeft className="h-4 w-4" />
          )}
        </Button>
      </div>

      {/* Nav */}
      <nav className="flex-1 space-y-1 px-2 py-4">
        {NAV.map((item) => {
          const active =
            pathname === item.href || pathname.startsWith(`${item.href}/`);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              title={collapsed ? item.label : undefined}
              className={cn(
                "flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
                collapsed && "justify-center px-0",
                active
                  ? "bg-sidebar-accent text-sidebar-accent-foreground"
                  : "hover:bg-sidebar-accent/50",
              )}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {!collapsed && <span>{item.label}</span>}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="border-t px-3 py-3">
        <Button
          variant="outline"
          size="sm"
          onClick={toggleAIPanel}
          className={cn(
            "mb-2 w-full gap-2",
            collapsed ? "justify-center px-0" : "justify-start",
          )}
          title="AI Assistant (Ctrl+K)"
        >
          <Sparkles className="h-4 w-4 shrink-0" />
          {!collapsed && (
            <>
              <span>AI</span>
              <kbd className="ml-auto rounded border px-1 text-[10px] text-muted-foreground">
                Ctrl+K
              </kbd>
            </>
          )}
        </Button>
        {!collapsed && (
          <p className="truncate text-xs text-muted-foreground" title={user?.email}>
            {user?.email ?? "—"}
          </p>
        )}
        <Button
          variant="outline"
          size="sm"
          onClick={logout}
          className={cn(
            "mt-2 w-full",
            collapsed ? "justify-center px-0" : "",
          )}
          title={collapsed ? "Выйти" : undefined}
        >
          {collapsed ? (
            <LogOut className="h-4 w-4" />
          ) : (
            "Выйти"
          )}
        </Button>
      </div>
    </aside>
  );
}
