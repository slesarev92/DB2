"use client";

/**
 * AuthProvider — React Context с auth state приложения.
 *
 * Хранит current user (из GET /api/auth/me) и предоставляет login/logout
 * методы. Используется через `useAuth()` хук в любом client component.
 *
 * При монтировании пытается восстановить сессию: если есть access token
 * в localStorage — делает /api/auth/me, при успехе сохраняет user.
 *
 * Защита роутов реализована не через middleware (нет доступа к
 * localStorage на сервере), а через client-side useEffect в защищённых
 * layout'ах: если не loading и user === null → router.push("/login").
 */

import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";

import {
  apiGet,
  ApiError,
  loginRequest,
  type UserMe,
} from "@/lib/api";
import { clearTokens, hasTokens, setTokens } from "@/lib/auth";

interface AuthContextValue {
  user: UserMe | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<UserMe | null>(null);
  const [loading, setLoading] = useState(true);

  // Восстановление сессии при первом монтировании
  useEffect(() => {
    let cancelled = false;

    async function restore() {
      if (!hasTokens()) {
        if (!cancelled) setLoading(false);
        return;
      }
      try {
        const me = await apiGet<UserMe>("/api/auth/me");
        if (!cancelled) setUser(me);
      } catch (err) {
        // 401/network — стираем токены, остаёмся anonymous
        if (err instanceof ApiError && err.status === 401) {
          clearTokens();
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    restore();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const tokens = await loginRequest(email, password);
      setTokens(tokens.access_token, tokens.refresh_token);
      const me = await apiGet<UserMe>("/api/auth/me");
      setUser(me);
      router.push("/projects");
    },
    [router],
  );

  const logout = useCallback(() => {
    clearTokens();
    setUser(null);
    router.push("/login");
  }, [router]);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (ctx === null) {
    throw new Error("useAuth must be used inside <AuthProvider>");
  }
  return ctx;
}
