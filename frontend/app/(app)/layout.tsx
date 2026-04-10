"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { AIPanelProvider } from "@/components/ai-panel/ai-panel-context";
import { AIPanelDrawer } from "@/components/ai-panel/ai-panel-drawer";
import { useAuth } from "@/components/auth-provider";
import { Sidebar } from "@/components/sidebar";

/**
 * Layout для защищённых маршрутов (/projects/*, /skus/*, /channels/*).
 *
 * Защита: при отсутствии user после загрузки → редирект на /login.
 * Server-side middleware не используется потому что токены живут
 * в localStorage (недоступен на server).
 *
 * Пока auth восстанавливается (loading=true) — показываем спиннер,
 * чтобы избежать flash защищённого контента до проверки.
 */
export default function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const { user, loading } = useAuth();

  useEffect(() => {
    if (!loading && user === null) {
      router.replace("/login");
    }
  }, [loading, user, router]);

  if (loading || user === null) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-muted-foreground">Загрузка...</p>
      </div>
    );
  }

  return (
    <AIPanelProvider>
      <div className="flex min-h-screen">
        <Sidebar />
        <main className="flex-1 overflow-auto p-6">{children}</main>
        <AIPanelDrawer />
      </div>
    </AIPanelProvider>
  );
}
