"use client";

import { Sparkles } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { useAIPanel } from "@/components/ai-panel/ai-panel-context";
import { useAuth } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
}

const NAV: NavItem[] = [
  { href: "/projects", label: "Проекты" },
  // Справочники, импорт данных и т.д. — добавятся в задачах 3.2-3.4 / Phase 4
];

export function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const { toggle: toggleAIPanel } = useAIPanel();

  return (
    <aside className="flex h-screen w-60 flex-col border-r bg-sidebar text-sidebar-foreground">
      <div className="border-b px-4 py-4">
        <h1 className="text-base font-semibold leading-tight">
          Цифровой паспорт
        </h1>
        <p className="text-xs text-muted-foreground">проекта</p>
      </div>

      <nav className="flex-1 space-y-1 px-2 py-4">
        {NAV.map((item) => {
          const active =
            pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "block rounded-md px-3 py-2 text-sm transition-colors",
                active
                  ? "bg-sidebar-accent text-sidebar-accent-foreground"
                  : "hover:bg-sidebar-accent/50",
              )}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="border-t px-4 py-3">
        <Button
          variant="outline"
          size="sm"
          onClick={toggleAIPanel}
          className="mb-2 w-full justify-start gap-2"
          title="AI Assistant (Ctrl+K)"
        >
          <Sparkles className="h-4 w-4" />
          <span>AI Assistant</span>
          <kbd className="ml-auto rounded border px-1 text-[10px] text-muted-foreground">
            Ctrl+K
          </kbd>
        </Button>
        <p className="truncate text-xs text-muted-foreground" title={user?.email}>
          {user?.email ?? "—"}
        </p>
        <Button
          variant="outline"
          size="sm"
          onClick={logout}
          className="mt-2 w-full"
        >
          Выйти
        </Button>
      </div>
    </aside>
  );
}
