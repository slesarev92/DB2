/**
 * API клиент: fetch wrapper с auto-attach Authorization, авто-refresh
 * access token при 401, понятные ошибки.
 *
 * Использование:
 *   const projects = await apiGet<Project[]>("/api/projects");
 *   await apiPost("/api/projects", { name: "X", start_date: "2025-01-01" });
 *   await apiPatch(`/api/projects/${id}`, { name: "Y" });
 *   await apiDelete(`/api/projects/${id}`);
 *
 * Для login используется отдельный `loginRequest` (не attach existing token).
 */

import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setAccessToken,
} from "./auth";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  detail: string | null;

  constructor(status: number, message: string, detail: string | null = null) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

async function _parseError(resp: Response): Promise<ApiError> {
  let detail: string | null = null;
  try {
    const body = await resp.json();
    detail =
      typeof body?.detail === "string"
        ? body.detail
        : JSON.stringify(body?.detail ?? body);
  } catch {
    detail = null;
  }
  return new ApiError(
    resp.status,
    `${resp.status} ${resp.statusText}`,
    detail,
  );
}

/** Низкоуровневый refresh: POST /api/auth/refresh с refresh_token. */
async function _tryRefresh(): Promise<boolean> {
  const refresh = getRefreshToken();
  if (!refresh) return false;
  try {
    const resp = await fetch(`${API_URL}/api/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
    });
    if (!resp.ok) return false;
    const data = (await resp.json()) as { access_token: string };
    setAccessToken(data.access_token);
    return true;
  } catch {
    return false;
  }
}

/** Основной fetch: добавляет Bearer, ретраит после refresh при 401. */
async function _fetchWithAuth(
  path: string,
  init: RequestInit,
  retried = false,
): Promise<Response> {
  const token = getAccessToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const resp = await fetch(`${API_URL}${path}`, { ...init, headers });

  if (resp.status === 401 && !retried) {
    const refreshed = await _tryRefresh();
    if (refreshed) {
      return _fetchWithAuth(path, init, true);
    }
    // Refresh не сработал — токены невалидны, чистим. AuthProvider
    // увидит отсутствие токенов и редиректнет на /login.
    clearTokens();
  }

  return resp;
}

async function _request<T>(
  path: string,
  init: RequestInit,
): Promise<T> {
  const resp = await _fetchWithAuth(path, init);
  if (!resp.ok) {
    throw await _parseError(resp);
  }
  if (resp.status === 204) {
    return undefined as T;
  }
  return (await resp.json()) as T;
}

export function apiGet<T>(path: string): Promise<T> {
  return _request<T>(path, { method: "GET" });
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return _request<T>(path, {
    method: "POST",
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

export function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return _request<T>(path, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function apiPut<T>(path: string, body: unknown): Promise<T> {
  return _request<T>(path, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export function apiDelete<T>(path: string): Promise<T> {
  return _request<T>(path, { method: "DELETE" });
}

/**
 * GET binary file (для XLSX/PDF/PPT экспорта). Возвращает Blob с auth
 * через _fetchWithAuth (поддерживает refresh при 401).
 *
 * Использование:
 *   const blob = await apiGetBlob("/api/projects/1/export/xlsx");
 *   const url = URL.createObjectURL(blob);
 *   // → trigger <a href={url} download="..."/> click
 */
export async function apiGetBlob(path: string): Promise<Blob> {
  const resp = await _fetchWithAuth(path, { method: "GET" });
  if (!resp.ok) {
    throw await _parseError(resp);
  }
  return await resp.blob();
}

// ============================================================
// Auth-specific (не используют existing token)
// ============================================================

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface UserMe {
  id: number;
  email: string;
  role: string;
}

/**
 * Логин через OAuth2 password flow. Backend ожидает x-www-form-urlencoded
 * (FastAPI OAuth2PasswordRequestForm), не JSON.
 */
export async function loginRequest(
  email: string,
  password: string,
): Promise<LoginResponse> {
  const formData = new URLSearchParams();
  formData.set("username", email);
  formData.set("password", password);

  const resp = await fetch(`${API_URL}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: formData.toString(),
  });

  if (!resp.ok) {
    throw await _parseError(resp);
  }
  return (await resp.json()) as LoginResponse;
}
