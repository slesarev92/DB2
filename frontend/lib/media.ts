/**
 * Media API wrappers (Фаза 4.5.2).
 *
 * POST /api/projects/{id}/media — multipart/form-data upload.
 * GET  /api/media/{id}          — binary download (Blob URL для <img>).
 * DELETE /api/media/{id}        — удалить asset + файл.
 *
 * Upload делается через `fetch` напрямую (не apiPost), потому что
 * apiPost форсит `Content-Type: application/json`. Для multipart нужно
 * позволить браузеру самому выставить `Content-Type: multipart/form-data;
 * boundary=...`. Auth-токен добавляется вручную (та же логика что в
 * api.ts, но упрощённо — без auto-refresh, endpoint 401 даст понятный
 * redirect через AuthProvider).
 */

import { apiDelete, apiGet, apiGetBlob } from "./api";
import { getAccessToken } from "./auth";

import type { MediaAssetRead, MediaKind } from "@/types/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function uploadMedia(
  projectId: number,
  file: File,
  kind: MediaKind,
): Promise<MediaAssetRead> {
  const token = getAccessToken();
  const formData = new FormData();
  formData.append("file", file);
  formData.append("kind", kind);

  const resp = await fetch(
    `${API_URL}/api/projects/${projectId}/media`,
    {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: formData,
    },
  );

  if (!resp.ok) {
    let detail = `${resp.status} ${resp.statusText}`;
    try {
      const body = await resp.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // keep default
    }
    throw new Error(detail);
  }

  return (await resp.json()) as MediaAssetRead;
}

export function listProjectMedia(
  projectId: number,
): Promise<MediaAssetRead[]> {
  return apiGet<MediaAssetRead[]>(`/api/projects/${projectId}/media`);
}

export function deleteMedia(mediaId: number): Promise<void> {
  return apiDelete<void>(`/api/media/${mediaId}`);
}

/**
 * Получить Blob URL для отображения в `<img src>`. Возвращённый URL
 * нужно освободить через `URL.revokeObjectURL()` в cleanup эффекта,
 * иначе blob-ы копятся в памяти.
 */
export async function getMediaBlobUrl(mediaId: number): Promise<string> {
  const blob = await apiGetBlob(`/api/media/${mediaId}`);
  return URL.createObjectURL(blob);
}
