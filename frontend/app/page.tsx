"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/components/auth-provider";

/**
 * Корневая страница / — редирект.
 *
 * Не защищённый layout (потому что находится в корне), но проверяет
 * auth state и перенаправляет:
 *   - залогинен → /projects
 *   - нет → /login
 */
export default function Home() {
  const router = useRouter();
  const { user, loading } = useAuth();

  useEffect(() => {
    if (loading) return;
    router.replace(user !== null ? "/projects" : "/login");
  }, [loading, user, router]);

  return (
    <div className="flex min-h-screen items-center justify-center">
      <p className="text-sm text-muted-foreground">Загрузка...</p>
    </div>
  );
}
