/**
 * Token storage helpers — localStorage обёртка для access/refresh JWT.
 *
 * SSR-safe: на сервере (где нет window) функции возвращают null / no-op,
 * чтобы не падать при server components / middleware. Все компоненты,
 * читающие токены, должны быть Client Components ("use client").
 *
 * MVP: храним в localStorage. Для prod можно мигрировать на httpOnly
 * cookie через Next.js Server Actions / route handlers — но это
 * меняет API клиента (нужны server-side fetch'ы).
 */

const ACCESS_KEY = "dp_access_token";
const REFRESH_KEY = "dp_refresh_token";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(ACCESS_KEY);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(REFRESH_KEY);
}

export function setTokens(access: string, refresh: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(ACCESS_KEY, access);
  window.localStorage.setItem(REFRESH_KEY, refresh);
}

export function setAccessToken(access: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(ACCESS_KEY, access);
}

export function clearTokens(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(ACCESS_KEY);
  window.localStorage.removeItem(REFRESH_KEY);
}

export function hasTokens(): boolean {
  return getAccessToken() !== null;
}
